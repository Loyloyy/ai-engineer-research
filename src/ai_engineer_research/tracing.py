"""Optional LLM-observability via self-hosted Langfuse — a tolerated-absent tracing seam.

deepagents is a LangGraph graph, and LangChain callbacks propagate through the whole run tree, so a
single Langfuse `CallbackHandler` attached at the top-level `agent.invoke` traces EVERYTHING beneath it:
the lead's LLM calls, every tool call, and every subagent — each with prompts, outputs, token counts and
latency. Per-call failures (timeouts, API errors, exceptions in a subagent or extraction) surface
automatically as ERRORED spans, pinpointing the exact failing node.

Mirrors the `checkpoint.py` discipline: env-gated (`AER_TRACING`, OFF by default), lazy-imported, and
tolerated-absent — if the dep is missing or disabled, every function is a safe no-op and nothing crashes.
Self-hosted only (the egress allowlist blocks Langfuse cloud): creds point at an in-network instance via
`LANGFUSE_HOST`/`_PUBLIC_KEY`/`_SECRET_KEY`. NO secrets/model/host literals live here — env-driven only.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def tracing_enabled() -> bool:
    return os.environ.get("AER_TRACING", "").strip().lower() in ("1", "true", "yes")


def build_tracer():
    """Return a Langfuse LangChain CallbackHandler, or None if disabled / dep absent / misconfigured."""
    if not tracing_enabled():
        return None
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        logger.info("AER_TRACING set but `langfuse` not installed (pip install '.[obs]'); tracing off")
        return None
    try:
        return CallbackHandler()  # creds read from LANGFUSE_HOST/_PUBLIC_KEY/_SECRET_KEY env
    except Exception as e:  # noqa: BLE001 — never let tracing init crash a run
        logger.warning("could not initialise Langfuse tracer (%s); tracing off", e)
        return None


def trace_metadata(run_id: str, tags: list[str], user_id: str = "aer") -> dict:
    """Langfuse trace attributes passed via the LangChain invoke `config["metadata"]`.

    `langfuse_session_id` groups every trace of one research run (lead loop + the extraction pass) under
    the run id; tags carry the mode (lean/multi-agent) and resume/attempt markers for UI filtering.
    """
    return {
        "langfuse_session_id": run_id,
        "langfuse_tags": tags,
        "langfuse_user_id": user_id,
    }


def flush_tracer() -> None:
    """Flush queued spans before the (ephemeral `docker compose run`) process exits. Safe no-op if off."""
    if not tracing_enabled():
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as e:  # noqa: BLE001 — best-effort; never crash on shutdown
        logger.debug("tracer flush skipped: %s", e)
