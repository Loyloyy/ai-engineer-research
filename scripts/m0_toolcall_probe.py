#!/usr/bin/env python3
"""MILESTONE 0 — validate that the on-prem model reliably drives a multi-step deepagents loop.

deepagents is tool-call-heavy: planning (write_todos), the filesystem, and subagent
delegation (task) are ALL tool calls. Before building the 5-subagent topology we must prove
the chosen LEAD model (a) plans, (b) calls tools, (c) uses the results, and (d) finishes —
against the real OpenAI-compatible endpoint (vLLM on the server, or a frontier endpoint).

This builds a trivial 2-tool deep agent and gives it a task whose answer is UNGUESSABLE
without calling the tools (canned values), then inspects the message trace.

Run (on the server, inside the app container):
    docker compose run --rm app python scripts/m0_toolcall_probe.py
    docker compose run --rm app python scripts/m0_toolcall_probe.py --role smart   # compare a role

Exit code 0 = PASS (safe to build topology). Non-zero = FAIL (route LEAD to a stronger
caller, e.g. a frontier model, and keep on-prem for summarize/extract).
"""
from __future__ import annotations

import argparse
import os
import sys

# Canned, arbitrary values — the model CANNOT guess these; it must call the tool.
_POP = {"tokyo": 1234, "paris": 5678}
_EXPECTED_TOTAL = sum(_POP.values())  # 6912


def lookup_population(city: str) -> int:
    """Return the (fictional) registered population of a city. Use this for any population question."""
    return _POP.get(city.strip().lower(), -1)


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return int(a) + int(b)


def _iter_tool_calls(messages) -> list[str]:
    """Names of every tool the agent invoked, across the message trace."""
    names: list[str] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name:
                names.append(name)
    return names


def _final_text(messages) -> str:
    for m in reversed(messages):
        if getattr(m, "type", None) == "ai" or m.__class__.__name__ == "AIMessage":
            content = getattr(m, "content", "")
            if isinstance(content, list):  # some providers return content blocks
                content = " ".join(
                    b.get("text", "") if isinstance(b, dict) else str(b) for b in content
                )
            if content and not (getattr(m, "tool_calls", None)):
                return str(content)
    # fallback: last message content
    return str(getattr(messages[-1], "content", "")) if messages else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="M0 deepagents tool-calling probe")
    ap.add_argument(
        "--role",
        default=os.environ.get("LEAD_ROLE", "strategic"),
        help="role to drive (strategic|smart|fast|judge). Default: $LEAD_ROLE or strategic.",
    )
    args = ap.parse_args()

    from ai_engineer_research.config import load_env
    from ai_engineer_research.models import build_chat_model

    load_env()
    model = build_chat_model(args.role)
    # Print endpoint + served id (NOT the key) so the run is self-documenting on the server.
    print(f"[M0] role={args.role}  base_url={model.openai_api_base}  model={model.model_name}")

    from deepagents import create_deep_agent

    agent = create_deep_agent(
        model=model,
        tools=[lookup_population, add],
        system_prompt=(
            "You are a careful assistant. For population questions you MUST call the "
            "lookup_population tool — never guess. Plan your steps, call the tools you need, "
            "then state the final total as a single number."
        ),
    )

    task = (
        "What is the combined population of Tokyo and Paris? "
        "Look up each city, then add them. Give the final total as a single number."
    )
    print(f"[M0] task: {task}\n[M0] invoking agent...\n")

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"recursion_limit": 50},
        )
    except Exception as e:  # noqa: BLE001 — M0 wants the raw failure surfaced
        print(f"[M0] FAIL — agent.invoke raised: {type(e).__name__}: {e}")
        return 2

    messages = result.get("messages", []) if isinstance(result, dict) else []
    tool_calls = _iter_tool_calls(messages)
    final = _final_text(messages)

    pop_calls = tool_calls.count("lookup_population")
    planned = "write_todos" in tool_calls
    added = "add" in tool_calls
    synthesized = str(_EXPECTED_TOTAL) in final.replace(",", "")

    print("[M0] ---- trace summary ----")
    print(f"[M0] tool calls in order : {tool_calls}")
    print(f"[M0] lookup_population x  : {pop_calls}  (need >= 2)")
    print(f"[M0] planned (write_todos): {planned}  (bonus)")
    print(f"[M0] used add tool        : {added}  (bonus)")
    print(f"[M0] final answer         : {final[:300]!r}")
    print(f"[M0] correct total {_EXPECTED_TOTAL}    : {synthesized}")

    # PASS = the load-bearing signals: it called the tool for BOTH cities and synthesized
    # the unguessable result. Planning / using `add` are reported as bonus capability signals.
    passed = pop_calls >= 2 and synthesized
    print(f"\n[M0] {'PASS — model drives the deepagents loop; safe to build topology.' if passed else 'FAIL — weak/unreliable tool caller; route LEAD to a stronger model.'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
