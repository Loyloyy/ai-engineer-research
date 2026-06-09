"""Role -> ChatModel factory.

Replaces the LiteLLM proxy (see DECISIONS: "migrate GPT Researcher -> deepagents").
deepagents/LangChain bind base_url + api_key + model PER BaseChatModel, so we no longer
need a router to fan out to N endpoints. Each role reads its own `.env` triple and returns
a `ChatOpenAI` (OpenAI-compatible — covers on-prem vLLM AND any frontier endpoint).

Rule #1/#8: NO concrete model name ever appears in app code — it is `.env`-driven.

    from ai_engineer_research.models import build_chat_model
    lead = build_chat_model("strategic")          # -> ChatOpenAI bound to the planner endpoint
    agent = create_deep_agent(model=lead, tools=[...])
"""
from __future__ import annotations

import logging
import os

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

ROLES = ("strategic", "smart", "fast", "judge")

# Per-role default sampling. Tool-calling is most reliable near-deterministic, so the
# tool-driving roles default to temperature 0. Override via build_chat_model(..., temperature=).
_ROLE_DEFAULTS: dict[str, dict] = {
    "strategic": {"temperature": 0.0},
    "smart": {"temperature": 0.2},
    "fast": {"temperature": 0.0},
    "judge": {"temperature": 0.0},
}


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing env var {name}. Copy .env.example -> .env and set the role triples "
            f"(<ROLE>_MODEL / <ROLE>_API_BASE / <ROLE>_API_KEY)."
        )
    return val


def _resolve_prefix(role: str) -> str:
    """Env prefix to use for a role: its own (<ROLE>_MODEL set) or a fallback default role.

    Lets a single-model setup fill ONLY the default role's triple (default `strategic`, override with
    AER_DEFAULT_ROLE) and leave the others blank — unset roles transparently reuse that endpoint. Returns
    the role's own prefix when truly unset so `_require` raises a clear error (rather than hiding it).
    """
    prefix = role.upper()
    if os.environ.get(f"{prefix}_MODEL", "").strip():
        return prefix
    default_role = (os.environ.get("AER_DEFAULT_ROLE", "strategic").strip().lower() or "strategic")
    if default_role in ROLES and default_role != role and os.environ.get(f"{default_role.upper()}_MODEL", "").strip():
        logger.warning("role %r has no %s_MODEL set; falling back to the %r endpoint", role, prefix, default_role)
        return default_role.upper()
    return prefix


def build_chat_model(role: str, **overrides) -> ChatOpenAI:
    """Build the ChatOpenAI for a role from its `.env` triple.

    role: one of strategic | smart | fast | judge.
    overrides: passed straight to ChatOpenAI (e.g. temperature=, timeout=, max_tokens=).

    Notes for vLLM (carry-over learnings):
      - The served model id may have a LEADING SLASH — set <ROLE>_MODEL to EXACTLY the id
        returned by GET <API_BASE>/models (data[0].id).
      - <ROLE>_API_KEY can be any non-empty string for vLLM (we default to "not-needed").
      - The model must be served with tool-calling enabled (e.g. vLLM
        --enable-auto-tool-choice + a --tool-call-parser). M0 verifies this end-to-end.
    """
    role = role.lower()
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}; expected one of {ROLES}.")

    # Resolve the endpoint prefix (own triple, or the AER_DEFAULT_ROLE fallback). Sampling defaults
    # below stay keyed on the ORIGINAL role — the task shapes temperature, the endpoint may be shared.
    prefix = _resolve_prefix(role)
    # Long multi-agent runs make big generations on long contexts → a single call can exceed 120s,
    # and a timeout aborts the whole run. Default generously; tune via env without code change.
    timeout_s = float(os.environ.get("AER_LLM_TIMEOUT_S", "300"))
    max_retries = int(os.environ.get("AER_LLM_MAX_RETRIES", "3"))
    params: dict = {
        "model": _require(f"{prefix}_MODEL"),
        "base_url": _require(f"{prefix}_API_BASE"),
        # vLLM accepts any non-empty key; allow the .env to omit it.
        "api_key": os.environ.get(f"{prefix}_API_KEY", "").strip() or "not-needed",
        "max_retries": max_retries,
        "timeout": timeout_s,
    }
    params.update(_ROLE_DEFAULTS.get(role, {}))
    params.update(overrides)
    return ChatOpenAI(**params)
