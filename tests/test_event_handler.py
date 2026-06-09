"""UIEventHandler: synthetic LangChain callbacks → the UI event vocabulary.

Runs anywhere — the handler falls back to `object` as its base when langchain_core is absent, so no
heavy deps are needed to verify the mapping (the part that matters for the frontend contract).
"""
from ai_engineer_research.webui.events import UIEventHandler


def _collect():
    events: list[dict] = []
    return events, UIEventHandler(events.append)


def _types(events):
    return [e["type"] for e in events]


def test_web_search_emits_tool_and_status():
    events, h = _collect()
    h.on_tool_start({"name": "web_search"}, "", inputs={"query": "self-hosted RAG"})
    assert "tool" in _types(events)
    tool = next(e for e in events if e["type"] == "tool")
    assert tool["name"] == "web_search" and tool["phase"] == "start"
    assert "self-hosted RAG" in tool["args_summary"]
    status = next(e for e in events if e["type"] == "status")
    assert status["text"].startswith("Searching:")


def test_fetch_url_status_uses_host():
    events, h = _collect()
    h.on_tool_start({"name": "fetch_url"}, "", inputs={"url": "https://github.com/owner/repo"})
    status = next(e for e in events if e["type"] == "status")
    assert "github.com" in status["text"]


def test_task_emits_delegate_and_stage():
    events, h = _collect()
    h.on_tool_start(
        {"name": "task"}, "", inputs={"subagent_type": "code-scout", "description": "find the best repos"}
    )
    delegate = next(e for e in events if e["type"] == "delegate")
    assert delegate["subagent"] == "code-scout"
    assert "best repos" in delegate["instruction"]
    stage = next(e for e in events if e["type"] == "stage")
    assert stage["mode"] == "multi-agent" and stage["node"] == "code-scout" and stage["active"]


def test_task_lifecycle_activates_then_deactivates_by_run_id():
    events, h = _collect()
    # Two subagents delegated (distinct run_ids), then they finish in a different order.
    h.on_tool_start({"name": "task"}, "", inputs={"subagent_type": "code-scout"}, run_id="r1")
    h.on_tool_start({"name": "task"}, "", inputs={"subagent_type": "landscape"}, run_id="r2")
    stages = [e for e in events if e["type"] == "stage"]
    assert {("code-scout", True), ("landscape", True)} <= {(e["node"], e["active"]) for e in stages}

    events.clear()
    h.on_tool_end("done", run_id="r1")  # code-scout returns → must deactivate code-scout specifically
    off = next(e for e in events if e["type"] == "stage")
    assert off["node"] == "code-scout" and off["active"] is False


def test_llm_end_accumulates_tokens():
    events, h = _collect()

    class Resp:  # minimal LLMResult-shaped object
        llm_output = {"token_usage": {"prompt_tokens": 120, "completion_tokens": 45}}

    h.on_llm_end(Resp())
    end = next(e for e in events if e["type"] == "llm" and e["phase"] == "end")
    assert end["prompt_tokens"] == 120 and end["completion_tokens"] == 45


def test_handler_never_raises_on_bad_input():
    events, h = _collect()
    # Missing serialized / weird inputs must not raise (a throwing callback would crash the run).
    h.on_tool_start(None, None)  # type: ignore[arg-type]
    h.on_llm_end(object())
    h.on_tool_end(None)
    # It simply emits best-effort events (or none) without throwing.
    assert isinstance(events, list)
