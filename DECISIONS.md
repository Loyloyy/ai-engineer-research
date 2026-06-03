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

## Models in use + the multi-model capability (2026-06-03)
- **For now ALL roles point at the same on-prem model** (set every `.env` triple to it). The goal is
  not multi-model yet — it's the *capability* to swap/mix models with no code change.
- **Swap any role to a frontier (or any OpenAI-compatible) endpoint** = edit that role's `.env` triple.
  No proxy, no code change.
- **Run multiple models simultaneously** = native, not custom-baked: `build_chat_model` binds per role,
  and deepagents subagents each accept their own `model` (the subagent dict's `model` field). So at M2
  the lead can run on the on-prem model while a chosen subagent runs on a different/frontier model, just
  by binding a different role. No bespoke router needed (and per the user: if it had to be custom-baked,
  we wouldn't — it doesn't).

## Milestone plan

- **M0 (current): validate on-prem tool-calling.** `build_chat_model` + a trivial 2-tool deep agent
  (`scripts/m0_toolcall_probe.py`) → prove the LEAD model plans, calls tools, uses results, finishes,
  against the live OpenAI-compatible endpoint. If it's a weak caller, route LEAD to a frontier model
  and keep on-prem for summarize/extract. **Do NOT build the 5-subagent topology on an unvalidated model.**
- **M1: single agentic lead loop + SearXNG + Crawl4AI tools → cited report + artifact.**
  See the "M1 research-loop design" entry below (settled with the planning chat).
- **M2: add subagents + GitHub code-gathering + composite filesystem artifact folder**
  (`artifacts/<id>/`: report.md · comparison.md · code/** · notes/**). Refine the subagent roster here
  (proposed: code-scout / limitations / alternatives / comparison / prod-readiness) — sanity-check the
  final roster with the planning chat at this boundary.
- **M3: artifact extraction + Stage-3 contract.** Port artifact/{schema,store,validate,extract}; run
  extraction over the deepagents output; document the artifact schema + run-folder layout + a short
  "how Stage 3 consumes this" note. DO NOT build Stage 3.

## M1 research-loop design — settled with the planning chat (2026-06-03)

The line between "agentic researcher" and "deepagents-wrapped GPTR": **the loop is driven by what it
learns, not a fixed pipeline.** The model decides the next action from current findings + open gaps,
reflects, and stops on quality. If M1 doesn't do that, it's the linear port the user warned against.

- **A. M1 = agentic SINGLE-agent loop** (plan → gather → reflect → stop). NOT a minimal linear M1.
  agentic ≠ subagents: M1 is ONE lead agent; the specialized fan-out
  (code-scout/limitations/alternatives/comparison/prod-readiness) + code-gathering is **M2**. Internal
  build order is fine: wire one agent + search/scrape tools to produce *something* first, then layer the
  scope/reflection discipline on top. (Integration de-risk is M0's job, not a reason for a linear M1.)
- **B. Scope artifact, optionally human-gated** (not "ask N questions"). The agent ALWAYS produces an
  explicit research scope as step 1 (sharp question + success criteria + assumptions). Modes differ only
  in WHO gates it:
  - *Headless* (default; the automated Stage-1→2 trigger): NEVER blocks. Scope auto-derived from the
    seed, logged, run proceeds. Hard requirement — the trigger can't answer questions.
  - *Interactive* (UI/human-initiated): scope surfaced for approval/edit via deepagents `interrupt_on`;
    may raise 1–3 clarifying questions. One scope artifact, one optional gate — not two code paths.
- **C. Reflection is IN M1, non-negotiable** — the single feature that makes M1 agentic. After each
  gather round: review findings vs open questions + success criteria, flag gaps + contradictions with
  the seed's attributed `## Opinions`, issue targeted follow-ups. Treat the seed's Opinions as
  **hypotheses to verify or refute, not facts to parrot** (the "challenge the seed" behavior; lean on
  the wiki's `[CONTRADICTION: …]` convention). Scales to reflecting over subagent outputs in M2.
- **D. Emit a cited `report.md` + `DeepResearchArtifact` in M1** — a complete vertical slice (thin but
  end-to-end, evaluable against the golden set). The artifact's `evidence_ids` need a report to extract
  from. M2 adds depth, not completeness. (⇒ artifact extraction is pulled forward into M1; M3 becomes
  refine-extraction + the Stage-3 contract doc.)
- **E. Locked contract signature** (optionals are keyword-only to prevent call-site mix-ups):
  ```python
  run_research(
      topic: str,
      brief: str = "",
      *,
      seed_pages: list[str] | None = None,   # wiki page ids; seed-builder expands → scope/brief
      parent_id: str | None = None,          # refinement lineage
      config: RunConfig | None = None,
      interactive: bool = False,             # False = headless, never blocks (decision B)
  ) -> tuple[str, DeepResearchArtifact]
  ```

**Comprehensiveness vs the concise seed.** The Stage-1 wiki is intentionally terse; Stage-2 output is
the opposite goal — as DETAILED and COMPREHENSIVE as a good analyst would write, WITHOUT token-wasting
(no padding/filler, no restating the seed; every claim earns its tokens). The seed is a floor, not a
ceiling. This is enforced in three places: (1) the seed brief's "How to use this seed" framing
(`seed.build_brief`), (2) the lead agent's system prompt (M1), and (3) the report-writing + artifact
extraction prompts (M1). Depth comes from real code + multiple independent sources + the
limitations/alternatives/comparison/prod-readiness analysis, not from verbosity.

**M0 gates M1 quality.** Planning + reflection are the hardest things to do well via tool-calling. If
the on-prem probe is marginal, route the LEAD (scope + plan + reflect) to a frontier model and keep
on-prem for high-volume gather/summarize — config-only via per-role/per-subagent binding. Don't force a
weak caller through the reflection loop and conclude "agentic doesn't work."

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
