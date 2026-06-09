"""Read-only views over `artifacts/<id>/` for the history browser + run-detail panels.

Pure presentation: reuses `artifact.store` (list/load/latest_version) + `manage.list_unfinished` +
the run-folder files the pipeline already writes (report.md, comparison.md, coverage.json, evidence.json,
ledger.json, notes/, code/, vNN.json, 00_INDEX.md). No pipeline logic, no network.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ..artifact.store import ARTIFACTS_ROOT, latest_version, list_artifacts, load

logger = logging.getLogger(__name__)

# Run-folder files we let the technical view read (everything else 404s). Directories (notes/, code/)
# are walked separately via the file listing.
_SERVE_SUFFIXES = (".md", ".json", ".txt", ".py", ".yaml", ".yml", ".toml", ".cfg", ".ini")


def _run_dir(run_id: str) -> Path:
    return ARTIFACTS_ROOT / run_id


def _resumable_ids() -> set[str]:
    try:
        from ..manage import list_unfinished

        return {r["id"] for r in list_unfinished()}
    except Exception as e:  # noqa: BLE001 — checkpoint DB absent/unreadable → no resumable flag
        logger.debug("list_unfinished failed: %s", e)
        return set()


def list_runs() -> list[dict]:
    """History list: every artifact dir + its latest version, topic, mode tag, and resumable flag.

    Sorted newest-first (the id is a sortable UTC-timestamp prefix, so reverse-name order == reverse time).
    """
    resumable = _resumable_ids()
    rows = []
    for a in list_artifacts():
        rid = a["id"]
        rows.append(
            {
                "id": rid,
                "topic": a.get("topic", ""),
                "latest_version": a.get("latest_version"),
                "mode": "multi-agent" if rid.endswith("-m") else "lean" if rid.endswith("-l") else None,
                "resumable": rid in resumable,
            }
        )
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _list_files(run_dir: Path) -> list[dict]:
    """Relative file inventory under a run dir (for the technical file browser)."""
    out: list[dict] = []
    if not run_dir.is_dir():
        return out
    for p in sorted(run_dir.rglob("*")):
        if p.is_file():
            try:
                rel = p.relative_to(run_dir).as_posix()
                out.append({"name": rel, "bytes": p.stat().st_size})
            except OSError:
                continue
    return out


def run_detail(run_id: str) -> dict | None:
    """Detail for one run: artifact + coverage + evidence + file inventory + Langfuse pointer.

    Returns None if neither a saved artifact nor a run folder exists for the id.
    """
    run_dir = _run_dir(run_id)
    has_artifact = latest_version(run_id) is not None
    if not has_artifact and not run_dir.is_dir():
        return None

    artifact = None
    if has_artifact:
        try:
            artifact = load(run_id).model_dump()
        except Exception as e:  # noqa: BLE001
            logger.warning("could not load artifact %s: %s", run_id, e)

    langfuse_host = (os.environ.get("LANGFUSE_HOST") or "").strip() or None
    return {
        "id": run_id,
        "mode": "multi-agent" if run_id.endswith("-m") else "lean" if run_id.endswith("-l") else None,
        "artifact": artifact,
        "coverage": _read_json(run_dir / "coverage.json"),
        "evidence": _read_json(run_dir / "evidence.json"),
        "files": _list_files(run_dir),
        # The frontend builds the deep link; we only surface the host + sessionId (== run_id).
        "langfuse_host": langfuse_host,
        "langfuse_session_id": run_id if langfuse_host else None,
    }


def resolve_run_file(run_id: str, name: str) -> Path | None:
    """Resolve a run-folder file path, confined to the run dir. None if missing/escaping/disallowed."""
    run_dir = _run_dir(run_id).resolve()
    if not run_dir.is_dir():
        return None
    target = (run_dir / name).resolve()
    try:
        target.relative_to(run_dir)  # reject path traversal (../, abs paths)
    except ValueError:
        return None
    if not target.is_file():
        return None
    if target.suffix.lower() not in _SERVE_SUFFIXES:
        return None
    return target
