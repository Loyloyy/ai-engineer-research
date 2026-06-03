# DECISIONS

Running log of non-trivial choices and rationale for **ai-engineer-research** (Stage 2 of the
3-part GenAI-scout system). Newest entries appended over time. Keep this file GENERIC — no
server IPs, hostnames, or served-model ids (those live only in the gitignored `.env`).

Predecessor: the GPT-Researcher prototype (`deep-researcher` repo) is superseded for Stage 2 and
kept as the validated reference + source of reusable layers. Its `DECISIONS.md` holds the full
"migrate GPT Researcher → deepagents" rationale.

## Stage 2 rebuild on LangChain `deepagents` — repo bootstrap (2026-06-03)

**Why deepagents (not GPTR).** The Stage-2 mandate is a multi-agent + filesystem job (specialized
researchers for code / limitations / alternatives / comparison / production-readiness; gather real
code; write a run folder). deepagents gives natively: subagents in isolated context (`task`),
a filesystem primitive, planning (`write_todos`), summarization, HITL interrupts, LangGraph
checkpointing — and removes GPTR's three fragile monkeypatch seams.

**Stable contract (keep it).** `run_research(...) -> (report_markdown, DeepResearchArtifact)`.
Headless core; any UI is presentation only. (Exact signature reconciled in M1 — see below.)

**Models — NO LiteLLM. In-process role→ChatModel factory.** deepagents/LangChain bind
`base_url`+`api_key`+`model` per `BaseChatModel`, so the proxy that GPTR needed (single global
`OPENAI_BASE_URL`) is gone. `build_chat_model(role)` reads `.env` triples
(`STRATEGIC_/SMART_/FAST_/JUDGE_` × `_MODEL/_API_BASE/_API_KEY`) → `ChatOpenAI` (OpenAI-compatible:
vLLM + frontier). No concrete model name in app code (rule #1). Roles: strategic=planner/lead ·
smart=writer/extraction · fast=summarize/sub-tasks · judge=eval (different family).

**Repo / package name.** `ai-engineer-research` / `ai_engineer_research` (confirmed with user).
Ported `deep_researcher` modules get their imports rewritten.

**Build locally, validate on the H200 server (containerized).** Code is authored in this workspace
and pushed via GitHub; the server pulls and runs everything in Docker (no host venv/uv). Therefore:
tracked files are generic with placeholders; the real `.env` + `docker-compose.override.yml` are
created on the server by the user. No local Python execution of the agent here (3.10 box; deepagents
needs ≥3.11 anyway).

**deepagents API confirmed (v0.6.7, beta — pinned).** `create_deep_agent(model: str | BaseChatModel,
tools: Sequence[BaseTool | Callable | dict], *, system_prompt, subagents, ...) -> CompiledStateGraph`.
Confirmed: `model` accepts a pre-initialized `BaseChatModel` (our `ChatOpenAI`); tools accept plain
callables; subagents are declarative `{name, description, system_prompt, ...}`; the return is a
LangGraph → invoked with `.invoke({"messages": [...]})`. Supply-chain vigilance now tracks
deepagents / langgraph / langchain (the LiteLLM pin burden is gone).

## Milestone plan

- **M0 (current): validate on-prem tool-calling.** `build_chat_model` + a trivial 2-tool deep agent
  (`scripts/m0_toolcall_probe.py`) → prove the LEAD model plans, calls tools, uses results, finishes,
  against the live OpenAI-compatible endpoint. If it's a weak caller, route LEAD to a frontier model
  and keep on-prem for summarize/extract. **Do NOT build the 5-subagent topology on an unvalidated model.**
- **M1: single lead agent + SearXNG + Crawl4AI tools → parity** (a cited report via `run_research`).
  Reconcile the contract signature here (handover lists `run_research(topic, brief, seed_pages,
  parent_id)`; the GPTR core used `(topic, brief, config, parent_id)` — likely add `seed_pages` for the
  Stage-1 wiki seed and keep `config` optional).
- **M2: add subagents + GitHub code-gathering + composite filesystem artifact folder**
  (`artifacts/<id>/`: report.md · comparison.md · code/** · notes/**). Refine the subagent roster here
  (proposed: code-scout / limitations / alternatives / comparison / prod-readiness) — sanity-check the
  final roster with the planning chat at this boundary.
- **M3: artifact extraction + Stage-3 contract.** Port artifact/{schema,store,validate,extract}; run
  extraction over the deepagents output; document the artifact schema + run-folder layout + a short
  "how Stage 3 consumes this" note. DO NOT build Stage 3.

## Carried over from the GPTR repo (port + adapt)
Artifact schema/store/validate/extract (the Stage 2→3 contract); SearXNG search, Crawl4AI extract,
cross-encoder rerank — now first-class **LangChain tools**, not GPTR injections; cache; eval golden-set
+ judge. Wiki (Stage 1) integration is filesystem-native + READ-ONLY (duplicated copy, composite
backend: read-only `wiki/` + writable `artifacts/<id>/`; `index.md` entry point; ~80–370 small files →
grep suffices). BM25 vault + MCP server kept as the semantic upgrade path + Stage-3 sharing mechanism.

## Egress (server)
Hard allowlist (search engines work; most sites TLS-reset). Appeal-to-unblock for code gathering:
`github.com`, `raw.githubusercontent.com`, `api.github.com`, `codeload.github.com`; plus `pypi.org`,
`files.pythonhosted.org`, `huggingface.co`, `arxiv.org`, key docs domains. Tools MUST degrade
gracefully (log + skip) on a blocked domain — never crash a run on a TLS reset.

## Verify-on-server seams (can't be checked from the local 3.10 box)
- M0 probe end-to-end against the live vLLM endpoint (and that the model is served with tool-calling
  enabled — e.g. vLLM `--enable-auto-tool-choice` + a `--tool-call-parser`).
- The served model id may carry a LEADING SLASH — set `<ROLE>_MODEL` to exactly `GET /v1/models` →
  `data[0].id`.
