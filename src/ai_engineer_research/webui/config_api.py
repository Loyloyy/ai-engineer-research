"""Phase 2 config-editing routes: prompt overrides (config/prompts/<name>.md) + pipeline knobs
(config/pipeline.yaml). NEVER touches `.env` (secrets/model endpoints stay server-side).

Prompt editing writes only the overridable BODY; the code-kept "always appended" parts (mission /
citation / grounding / required outputs / injected knobs) are read-only previews assembled from the
single source of truth in `agent.py` / `subagents.py` / `clarify.py`. Param editing validates against an
allow-list so nothing resembling a secret can be injected into pipeline.yaml.
"""
from __future__ import annotations

import logging

import yaml

from ..config import ROOT, load_config
from ..prompts import PROMPT_NAMES, load_prompt, prompts_dir

logger = logging.getLogger(__name__)

# Non-secret pipeline.yaml knobs the UI may edit, with their expected types. Anything not here is
# rejected (so a secret/model endpoint can never be smuggled into the tracked yaml).
_ALLOWED_PARAMS = {
    "research": {
        "lead_role": str,
        "thoroughness": str,
        "max_investigators": int,
        "code_max_repos": int,
        "code_files_per_repo": int,
        "clarify": bool,
        "multi_agent": bool,
        "checkpoint_enabled": bool,
    },
    "artifact": {
        "enabled": bool,
        "model": str,
    },
}
_THOROUGHNESS_LEVELS = {"light", "standard", "deep"}

_PIPELINE_YAML = ROOT / "config" / "pipeline.yaml"


def _has_override(name: str) -> bool:
    p = prompts_dir() / f"{name}.md"
    try:
        return p.is_file() and bool(p.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _default_body(name: str) -> str:
    from .. import clarify
    from ..agent import lead_default_body
    from ..subagents import subagent_default_body

    if name == "lead_lean":
        return lead_default_body(False)
    if name == "lead_multi":
        return lead_default_body(True)
    if name == "clarify":
        return clarify._DEFAULT_CLARIFY_PROMPT
    return subagent_default_body(name)


def _appended_preview(name: str) -> str:
    from .. import clarify
    from ..agent import lead_appended_preview
    from ..subagents import subagent_appended_preview

    cfg = load_config()
    if name == "lead_lean":
        return lead_appended_preview(False, cfg)
    if name == "lead_multi":
        return lead_appended_preview(True, cfg)
    if name == "clarify":
        return clarify.clarify_appended_note()
    return subagent_appended_preview(
        name,
        thoroughness=cfg.thoroughness,
        code_max_repos=cfg.code_max_repos,
        code_files_per_repo=cfg.code_files_per_repo,
    )


def _read_pipeline() -> dict:
    if _PIPELINE_YAML.is_file():
        return yaml.safe_load(_PIPELINE_YAML.read_text(encoding="utf-8")) or {}
    return {}


def _editable_params() -> dict:
    """Current pipeline.yaml filtered to just the editable (allow-listed) knobs."""
    data = _read_pipeline()
    out: dict = {}
    for section, keys in _ALLOWED_PARAMS.items():
        present = {k: data[section][k] for k in keys if isinstance(data.get(section), dict) and k in data[section]}
        if present:
            out[section] = present
    return out


def _validate_and_merge(incoming: dict) -> dict:
    """Validate incoming params against the allow-list + types; merge onto the existing yaml. Raises
    ValueError on any disallowed key / bad type (→ HTTP 400)."""
    if not isinstance(incoming, dict):
        raise ValueError("params must be an object")
    merged = _read_pipeline()
    for section, values in incoming.items():
        if section not in _ALLOWED_PARAMS:
            raise ValueError(f"unknown section '{section}' (allowed: {sorted(_ALLOWED_PARAMS)})")
        if not isinstance(values, dict):
            raise ValueError(f"section '{section}' must be an object")
        allowed = _ALLOWED_PARAMS[section]
        for key, val in values.items():
            if key not in allowed:
                raise ValueError(f"unknown key '{section}.{key}' (allowed: {sorted(allowed)})")
            expected = allowed[key]
            if expected is bool and not isinstance(val, bool):
                raise ValueError(f"'{section}.{key}' must be a boolean")
            if expected is int and (isinstance(val, bool) or not isinstance(val, int)):
                raise ValueError(f"'{section}.{key}' must be an integer")
            if expected is str and not isinstance(val, str):
                raise ValueError(f"'{section}.{key}' must be a string")
            if key == "thoroughness" and val not in _THOROUGHNESS_LEVELS:
                raise ValueError(f"thoroughness must be one of {sorted(_THOROUGHNESS_LEVELS)}")
        merged.setdefault(section, {})
        if not isinstance(merged[section], dict):
            merged[section] = {}
        merged[section].update(values)
    return merged


def register_config_routes(app) -> None:
    from fastapi import HTTPException
    from pydantic import BaseModel

    class PromptBody(BaseModel):
        body: str

    class ParamsBody(BaseModel):
        params: dict

    @app.get("/api/prompts")
    def list_prompts() -> dict:
        return {"prompts": [{"name": n, "has_override": _has_override(n)} for n in PROMPT_NAMES]}

    @app.get("/api/prompts/{name}")
    def get_prompt(name: str) -> dict:
        if name not in PROMPT_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown prompt '{name}'")
        return {
            "name": name,
            "body": load_prompt(name, _default_body(name)),  # current override, else the default
            "has_override": _has_override(name),
            "appended_readonly": _appended_preview(name),
        }

    @app.put("/api/prompts/{name}")
    def put_prompt(name: str, payload: PromptBody) -> dict:
        if name not in PROMPT_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown prompt '{name}'")
        d = prompts_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.md").write_text(payload.body, encoding="utf-8")
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"could not write override: {e}") from e
        return {"ok": True, "has_override": _has_override(name)}

    @app.get("/api/params")
    def get_params() -> dict:
        return {"params": _editable_params(), "thoroughness_levels": sorted(_THOROUGHNESS_LEVELS)}

    @app.put("/api/params")
    def put_params(payload: ParamsBody) -> dict:
        try:
            merged = _validate_and_merge(payload.params)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            _PIPELINE_YAML.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"could not write pipeline.yaml: {e}") from e
        return {"ok": True, "params": _editable_params()}
