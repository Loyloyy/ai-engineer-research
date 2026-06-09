"""UIEventHandler — a LangChain callback handler that emits UI event dicts.

This is the seam the FastAPI layer supplies via `run_research(..., event_callbacks=[handler])`. Because
LangChain callbacks propagate through the whole deepagents/LangGraph tree, ONE handler at the top sees
every tool call, LLM call, and subagent `task` delegation beneath the lead (mirrors how `tracing.py`'s
Langfuse handler traces everything). We translate those raw callbacks into the small, presentation-
agnostic event vocabulary the frontend renders (see `EVENT_TYPES`).

Design rules:
- NEVER raise. A callback that throws would crash the run mid-flight, so every method is wrapped — a bad
  event is dropped, not fatal. (Robustness > completeness here.)
- Emit via an injected `emit(event: dict)` callable (the runner passes one that enqueues onto a thread-
  safe queue; tests pass `list.append`). Keeps this class decoupled from transport.
- This handler interprets the graph; the frontend stays dumb. The `url`/`coverage`/`report`/`files`/
  `stage(lean)` events are added by the SSE layer from the ledger + run-folder files — NOT here — since
  those are polled, not callback-driven.

`event` dicts always carry a `"type"`; the rest of the keys depend on the type.
"""
from __future__ import annotations

import logging
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# The event types this handler emits (the SSE layer adds: stage(lean), url, coverage, report, files,
# heartbeat, done, error). Kept here as the single source of truth for the backend↔frontend contract.
EVENT_TYPES = ("tool", "llm", "delegate", "stage", "status")

# Tool name → friendly status verb for the high-level ticker.
_STATUS_VERB = {
    "web_search": "Searching",
    "fetch_url": "Reading",
    "task": "Delegating",
}


def _safe(fn: Callable) -> Callable:
    """Wrap a handler method so an exception inside it can never crash the run."""

    def wrapper(self: "UIEventHandler", *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:  # noqa: BLE001 — a callback must never break the research loop
            logger.debug("UIEventHandler.%s swallowed %s: %s", fn.__name__, type(e).__name__, e)

    return wrapper


def _tool_name(serialized: dict | None, kwargs: dict) -> str:
    if isinstance(serialized, dict) and serialized.get("name"):
        return str(serialized["name"])
    return str(kwargs.get("name") or "tool")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _first(d: dict, *keys: str):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def _build_base_callback_handler():
    """Import BaseCallbackHandler lazily; fall back to `object` so this module imports without langchain.

    langchain_core is a core dependency in the container, but keeping the import lazy lets the event
    vocabulary + helpers be imported (and unit-tested) anywhere.
    """
    try:
        from langchain_core.callbacks import BaseCallbackHandler

        return BaseCallbackHandler
    except Exception:  # noqa: BLE001
        return object


_Base = _build_base_callback_handler()


class UIEventHandler(_Base):  # type: ignore[misc, valid-type]
    """Translate run callbacks → UI event dicts via an injected emit callable."""

    # We want LLM + tool + delegation events. Let chain (graph-node) noise through silently — the `task`
    # tool is the clean delegation signal, so we don't subscribe to the flood of on_chain_* events.
    ignore_chain = True
    raise_error = False  # belt-and-suspenders with _safe: tell LangChain not to propagate our errors

    def __init__(self, emit: Callable[[dict], None]) -> None:
        self._emit = emit
        # run_id (of a `task` tool call) -> subagent name, so on_tool_end can deactivate the right node.
        # A subagent is "active" (blue) only between its task's start and end; multiple may run at once.
        self._task_runs: dict[str, str] = {}

    # --- tools (web_search / fetch_url / github_*/hf_*/pypi_* / write_file / the `task` delegation) ---
    @_safe
    def on_tool_start(
        self,
        serialized: dict | None,
        input_str: str,
        *,
        inputs: dict | None = None,
        **kwargs: Any,
    ) -> None:
        name = _tool_name(serialized, kwargs)
        args = inputs if isinstance(inputs, dict) else {"input": input_str}
        summary = self._summarize_args(name, args, input_str)
        self._emit({"type": "tool", "name": name, "phase": "start", "args_summary": summary})

        if name == "task":
            subagent = str(_first(args, "subagent_type", "subagent", "agent", "name") or "subagent")
            instruction = str(_first(args, "description", "task", "instruction", "input") or input_str or "")
            run_id = kwargs.get("run_id")
            if run_id is not None:
                self._task_runs[str(run_id)] = subagent
            self._emit({"type": "delegate", "subagent": subagent, "instruction": instruction[:600]})
            # Light up the delegated node (active=True now; on_tool_end clears it when the subagent returns).
            self._emit({"type": "stage", "mode": "multi-agent", "node": subagent, "active": True})
            self._emit({"type": "status", "text": f"Delegating to {subagent}…"})
            return

        self._emit({"type": "status", "text": self._status_text(name, args)})

    @_safe
    def on_tool_end(self, output: Any, *, name: str | None = None, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        subagent = self._task_runs.pop(str(run_id), None) if run_id is not None else None
        if subagent:
            # The subagent's task returned → flip its node from active (blue) back to engaged (green).
            self._emit({"type": "stage", "mode": "multi-agent", "node": subagent, "active": False})
            self._emit({"type": "status", "text": f"{subagent} finished"})
        self._emit({"type": "tool", "name": str(name or "tool"), "phase": "end"})

    # --- LLM / chat-model calls (model + token usage for the technical feed) ---
    @_safe
    def on_chat_model_start(self, serialized: dict | None, messages: Any, **kwargs: Any) -> None:
        self._emit({"type": "llm", "phase": "start", "model": _tool_name(serialized, kwargs)})

    @_safe
    def on_llm_start(self, serialized: dict | None, prompts: Any, **kwargs: Any) -> None:
        self._emit({"type": "llm", "phase": "start", "model": _tool_name(serialized, kwargs)})

    @_safe
    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage = self._token_usage(response)
        self._emit({"type": "llm", "phase": "end", **usage})

    # --- helpers --------------------------------------------------------------------------------
    def _summarize_args(self, name: str, args: dict, input_str: str) -> str:
        if name == "web_search":
            return str(_first(args, "query") or input_str or "")[:200]
        if name == "fetch_url":
            return str(_first(args, "url") or input_str or "")[:300]
        if name in ("write_file", "edit_file"):
            return str(_first(args, "file_path", "path", "file") or "")[:200]
        # structured-API / other tools: a compact key=val join
        if args:
            return ", ".join(f"{k}={str(v)[:60]}" for k, v in list(args.items())[:4])
        return str(input_str or "")[:200]

    def _status_text(self, name: str, args: dict) -> str:
        verb = _STATUS_VERB.get(name)
        if name == "web_search":
            q = str(_first(args, "query") or "")
            return f"Searching: {q}"[:140]
        if name == "fetch_url":
            url = str(_first(args, "url") or "")
            host = _host(url)
            return f"Reading {host or url}…"[:140]
        if name in ("write_file", "edit_file"):
            path = str(_first(args, "file_path", "path", "file") or "")
            return f"Writing {path}…"[:140]
        if verb:
            return f"{verb}…"
        return f"Running {name}…"

    @staticmethod
    def _token_usage(response: Any) -> dict:
        """Best-effort token counts from an LLMResult across provider shapes."""
        out: dict = {}
        try:
            llm_output = getattr(response, "llm_output", None) or {}
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if not usage:
                # newer langchain: usage_metadata on the generation message
                gens = getattr(response, "generations", None) or []
                for batch in gens:
                    for g in batch:
                        msg = getattr(g, "message", None)
                        um = getattr(msg, "usage_metadata", None)
                        if um:
                            usage = um
                            break
                    if usage:
                        break
            if usage:
                pt = usage.get("prompt_tokens") or usage.get("input_tokens")
                ct = usage.get("completion_tokens") or usage.get("output_tokens")
                if pt is not None:
                    out["prompt_tokens"] = pt
                if ct is not None:
                    out["completion_tokens"] = ct
        except Exception:  # noqa: BLE001
            pass
        return out
