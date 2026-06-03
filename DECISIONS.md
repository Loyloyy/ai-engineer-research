# DECISIONS

Running log of non-trivial choices and rationale for **ai-engineer-research** (Stage 2 of the
3-part GenAI-scout system). Newest entries appended over time. Keep this file GENERIC — no
server IPs, hostnames, or served-model ids (those live only in the gitignored `.env`).

Predecessor: the GPT-Researcher prototype (`deep-researcher` repo) is superseded for Stage 2 and
kept as the validated reference + source of reusable layers. Its `DECISIONS.md` holds the full
"migrate GPT Researcher → deepagents" rationale.

---
**CURRENT STATUS (2026-06-04).** Stage 2 is built & validated end-to-end on the on-prem model. M0
(tool-calling) ✅ · M1 (lean agentic loop → cited report + artifact) ✅ · M2 (multi-agent: code-scout/
landscape/maturity + structured GitHub/HF/PyPI tools + `code/**`; opt-in `AER_MULTI_AGENT=1`) ✅ · M3
(Stage-3 contract doc + extraction hardening) ✅ · robustness (timing + salvage-on-error + tuned
timeouts) ✅ · subagent transparency (`notes/<name>.md`) ✅. **Only remaining: wire Context7 MCP once
the egress appeal is granted (not yet filed).** Quickstart in `README.md`; gotchas in `DEV_NOTES.md`;
handoff contract in `docs/STAGE3_CONTRACT.md`. The entries below are the chronological rationale log.

---

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

## M1 Slice 1 — browserless extraction (2026-06-03)

`web_search` (SearXNG/httpx) validated on the server first try. `fetch_url` initially used
Crawl4AI + Playwright chromium (ported from the GPTR repo) but the browser **could not be installed**
in the image: the Playwright browser-download CDN isn't on the server egress allowlist, so the build's
`playwright install` failed (silently, via `|| echo`) and `fetch_url` had no browser at runtime.

**Decision: dual-backend `fetch_url`, selected by `AER_FETCH_BACKEND` (auto|http|browser).** The
DEFAULT path is **browserless** — httpx (egress-friendly, follows redirects) + trafilatura (clean
boilerplate-stripped markdown) — because research sources (GitHub, docs, blogs, arxiv abstracts, raw
files) are static HTML and need no browser. The **browser** path (Crawl4AI + Playwright chromium, JS
rendering) is selectable for when it's needed, but requires the chromium binary, which requires the
Playwright download CDN to be on the server egress allowlist. Install path: `playwright install
--dry-run chromium` prints the CDN host(s) → appeal them → rebuild (`WITH_BROWSER=1`, default) → set
`AER_FETCH_BACKEND=browser` (or `auto`). `auto` uses the browser only if a chromium binary is present
and falls back to http on an empty result. Graceful degradation holds throughout (blocked/empty →
informative note or http fallback, never a crash). (Earlier same-day note said "drop the browser from
M1"; superseded — it's now optional-and-selectable rather than removed.)

## Egress map — what's actually reachable (2026-06-03, measured via scripts/egress_probe.py)

Probed 122 research/code domains from inside the container. **28 reachable, 94 TLS-reset.** The
allowlist is ML-infra-shaped: pull-models/containers/packages is open, general web is not.

**Reachable substrate (rely on these):**
- **GitHub** — github.com, raw.githubusercontent.com, api.github.com, codeload, objects.*, user-images.*
  (only `gist.githubusercontent.com` is blocked). `*.github.io` works (langchain-ai.github.io, etc.).
- **Hugging Face** — huggingface.co (+ /api, /papers, /docs, /blog), hf.co, discuss.huggingface.co.
- **PyPI** — pypi.org + files.pythonhosted.org (no npm/crates/maven/conda/rubygems/nuget).
- **Container registries** — hub.docker.com, registry-1.docker.io, ghcr.io, quay.io, NGC; developer.nvidia.com.
- **Select docs** — docs.python.org, kubernetes.io, docs.docker.com.
- **Search** — google.com, bing.com (so SearXNG discovery works; duckduckgo/brave/scholar blocked).

**Blocked & notable:** arxiv (+ ar5iv/export/semanticscholar/openreview/aclanthology/PMLR/CVF), nearly all
project docs (pytorch, sklearn, numpy, pandas, fastapi, vllm, pydantic, gradio, langchain docs, all
vector-DB docs, MDN), StackOverflow, Wikipedia, all blogs (incl. openai/anthropic/langchain/pytorch),
npm/crates/maven/conda. **No escape hatch:** web.archive.org, archive.org, r.jina.ai, and all CDNs
(jsdelivr/unpkg/cloudflare) reset — so there is no proxy/Wayback workaround. Browser CDN
(cdn.playwright.dev) also blocked → the Playwright browser path stays unavailable unless appealed.

**Consequence.** Stage 2's CODE mandate is viable NOW (GitHub + HF + PyPI + github.io docs + Google/Bing
search). The gaps are papers / 3rd-party tool docs / StackOverflow / blogs. The agent must (a) prefer the
reachable set, (b) not waste turns on hosts that reset, and (c) be honest about grounding when a key
source is unreachable (never backfill from parametric memory). Reachable-domain preference is kept as
env/config (env-overridable) so appealed domains expand it with zero code change.

## Whitelist appeal (final) + locked M1/M2 scope line (with planning chat, 2026-06-03)

**Appeal list submitted** (framed "documentation / papers / reference & community data sources"; tiers
are severable — infra can grant/cut each line):
- **Tier 1 (docs + papers):** `context7.com` + `mcp.context7.com` (version-specific docs aggregator,
  consumed via its MCP server — one appeal replaces dozens of doc-domain appeals); `arxiv.org` +
  `export.arxiv.org` (full-text papers; HF/papers = abstracts only, not a substitute); `*.readthedocs.io`
  (wildcard — vendor-independent docs fallback so we're not single-pointed on Context7).
- **Tier 2 (background + technical discussion):** `en.wikipedia.org` + `upload.wikimedia.org`;
  `hn.algolia.com` (Hacker News full-text search API — clean JSON, no scraping; chosen over the HN site
  and over the Firebase API which is item-by-id only).
- **Tier 3 (practitioner experience; severable, ordered by ease):** `stackoverflow.com` +
  `api.stackexchange.com`; then `medium.com` + `*.substack.com`.
- **Reddit DROPPED from this appeal.** A domain grant ≠ access (free API dead; `oauth.reddit.com` needs a
  registered app + token + rate-limit handling). Rely on search snippets now; appeal + build the OAuth
  integration together in round-2 only if the miss-log shows missing signal concentrates on reddit.
- **Already open — exploit, don't appeal:** full GitHub, HF (incl. `discuss.huggingface.co`, a reachable
  practitioner forum → make first-class), PyPI, container registries, Google/Bing.
- **Don't appeal:** more 3rd-party MCP doc servers (Context7 is the one; wrap GitHub/HF/PyPI REST as our
  own local tools); Wayback/archive.org/r.jina.ai/CDNs (confirmed reset, no proxy — fast-fail, don't build
  retry logic); npm/crates/maven/conda (Python-only scope).

**The M1/M2 line (locked).** Principle: *intelligence lives in the LOOP (M1), not the tool count (M2).*
- **M1 — lean agentic loop (prove the LOOP, not the substrate).**
  Tools: `web_search` (SearXNG) + `fetch_url` (httpx+trafilatura, HTML only — already reaches open hosts
  like GitHub raw/README, HF pages, readthedocs-if-granted, as fetchable pages, not APIs).
  Discipline (all cheap, all M1): known-blocked-host fast-skip; **per-run miss-log** (blocked-domain
  telemetry = round-2 appeal evidence); snippet confidence-tagging; coverage-manifest scaffold in the artifact.
  Behavior: scope → plan (`write_todos`) → gather (evidence_ids) → reflect/gap-check (incl. contradictions
  vs the seed's attributed Opinions) → quality-driven stop. Single lead agent; headless non-blocking default,
  interactive optional scope gate. Deliver: cited `report.md` + `DeepResearchArtifact`.
- **M2 — rich substrate + multi-agent (DEPTH).**
  Tools: structured APIs as first-class tools — GitHub (code-search / repo metadata / releases / issues /
  dependents / awesome-lists / LICENSE), HF API, PyPI JSON, arxiv API; Context7 MCP (docs). `fetch_url`
  gains the PDF→PyMuPDF branch (lands with arxiv; PyMuPDF is known from the old repo's Crawl4AI adapter).
  Agents: code-scout / limitations / alternatives / comparison / prod-readiness (isolated context via `task`).
  Output: gathered code in `code/**`; coverage manifest + confidence-tiering fully wired (existence/maturity
  = HIGH from primary artifacts; real-world limitations/comparison = MED/LOW from forums/snippets).

**Source-resolution tiers (architecture):** (a) structured tools (APIs + Context7 MCP) — preferred, clean,
attributable [M2]; (b) direct `fetch_url` — raw files / readthedocs / arxiv PDFs / HF pages; (c) search
snippets — signal-only, LOWER-confidence, never sole grounding. Coverage disclosure + confidence-by-evidence
-type in the artifact tells downstream which half of the mandate is well-grounded.

## M1 COMPLETE (2026-06-03)

The lean agentic loop is validated end-to-end on the on-prem model via `run_research(...)`:
- Slices: 1 tools (web_search + browserless fetch_url) · 2 bare gather · 3 scope/reflect/grounding +
  domain-steering + miss-log + coverage · 4 extraction · 5 wire-up (core.run_research + CLI).
- Verified run produced: `scope.md` (sharp Q + sub-questions + success criteria), `reflection.md`
  (HIGH/MED/LOW confidence tiers + explicit confirm/contradict verdict on the seed's opinion),
  `report.md` (cited, comprehensive), `coverage.json`, and `vNN.json` — a `DeepResearchArtifact` with
  15 findings whose `evidence_ids` all resolve to fetched sources (citation validation working),
  tech_stack/reference_repos/implementation_steps/open_questions, sources grounded in actually-fetched
  URLs, and the coverage manifest embedded. The on-prem model's `with_structured_output` (nested
  pydantic) worked — no JSON-mode fallback needed.
- Run folders are timestamped+sortable (`dra-YYYYMMDD-HHMMSS-rand`). Files land NFS-squashed
  (nobody:nogroup, 0644) — readable; manage via the 777 parent.

## M2 design — subagent roster (settled with planning chat, 2026-06-03)

**Decompose by INVESTIGATION (distinct sources + skill), not by report section.** The handover's 5
(code-scout/limitations/alternatives/comparison/prod-readiness) were organized by output section and
over-fragment. Final roster:
- **3 fixed default subagents** (each genuinely distinct + context-heavy enough to justify isolation):
  - **code-scout** — find + gather real implementations (GitHub code-search/repos/READMEs/examples/
    releases); pulls actual code into `code/**`.
  - **landscape** — alternatives **+** comparison investigation ("what else exists & how it compares").
    Outputs structured per-alternative attributes (does NOT own the matrix — see below).
  - **maturity** — limitations **+** production-readiness ("is this real and safe for prod": failure
    modes, gotchas, issues, who runs it in prod, license, cost, maturity signals).
- **+ dynamic spawning:** the lead spawns a focused ad-hoc subagent during its reflect step when a topic
  demands it (deep limitations pass, security pass, a **benchmarks/eval** pass for benchmark-centric
  topics). Don't hardcode beyond the 3; use deepagents' dynamic `task` spawn.
- **Lead owns synthesis + `comparison.md`.** Comparison is cross-cutting (needs subject attributes from
  maturity/code-scout + alternative attributes from landscape); the lead already receives all three
  subagents' *distilled summaries* and builds the matrix from those (works from summaries, not raw
  context, so it doesn't bloat). Fallback if lead context gets heavy: landscape drafts the alternative
  axes, lead folds in the subject row.
- **No dedicated papers/benchmarks agent** — papers (arxiv/HF-papers) is a SOURCE serving all three →
  make it a shared tool, not a pass. ("Benchmarks/eval" as an *investigation* is a dynamic-spawn candidate.)
- **Bake in:** (1) the URL cache + run ledger are module-level singletons → already SHARED across
  in-process subagent runs (dedups fetches; coverage spans the whole run) — keep it that way, not
  per-agent. (2) **Lead owns cross-subagent contradiction reconciliation** — e.g. code-scout "README says
  X" vs maturity "issues say X is broken in prod" → reconcile via confidence-tiering (primary-artifact
  HIGH vs forum/snippet MED-LOW) and flag genuine disagreement with the wiki's `[CONTRADICTION: …]`
  convention. That tension IS the mandate (honest limitations vs marketing), a feature not noise.

**M2 build order:** structured-API tools (GitHub → HF → PyPI; the code-scout substrate, appeal-independent)
→ Context7 MCP (when appealed) → the 3 subagents + dynamic spawn + lead synthesis + `code/**` output.

**M2 multi-agent VALIDATED (2026-06-03).** Structured tools (GitHub/HF/PyPI) built + GitHub live-tested.
Subagent topology built (`subagents.py`: code-scout/landscape/maturity + focused-investigator; lead
holds full toolset, subagents inherit it incl. filesystem since deepagents `tools=` REPLACES inherited)
and opt-in via `AER_MULTI_AGENT=1` (lean M1 stays default). Validated run produced: `code/**` with 7
real source files (code-scout's write_file works), an analyst-grade `comparison.md` matrix (9 frameworks
+ pairwise deep-dives + decision matrix, lead-synthesized from subagent summaries), report.md, and the
artifact. The on-prem model drove the delegation loop with no recursion error. **Remaining M2:** Context7
MCP (waits on the egress appeal, not yet filed).

**Subagent transparency:** each subagent now also writes its full findings to `notes/<name>.md`
(code-scout/landscape/maturity + focused-<slug>) before returning its summary — inspectable per run,
for debugging/trust. Lead still synthesizes from the returned summaries (not the notes).

**Grounding spot-check PASSED (2026-06-03).** Verified the multi-agent run's artifact: issue #573 is
real and correctly cited; 23 sources are all genuinely-fetched URLs (raw source files + GitHub issue
pages the agent actually fetch_url'd + the NVIDIA AI-Q production blog); 22 findings all cite resolving
sources with confidence, and the "production-ready" hypothesis is refuted citing 4 specific issues. No
prompt fix needed — the maturity→extraction path grounds issues with URLs as designed.

## M3 — Stage-3 contract documented (2026-06-04)

- **`docs/STAGE3_CONTRACT.md`** written: run-folder layout, full `DeepResearchArtifact` field reference,
  loading API, `model_versions` (roles + coverage) semantics, field→PoC-generation mapping, and
  stability guarantees (stable: the `run_research` signature, artifact field names/types, run-folder
  filenames, the evidence_id→Source citation invariant; advisory: prose structure, subagent roster).
  Per the mandate this is the contract ONLY — **Stage 3 is not built here**.
- **Light extraction hardening:** `extract_artifact` now gives the structured-output pass one stricter
  retry before falling back to a content-light artifact (the report is always preserved). Grounding
  quality was already verified strong (see the M2 spot-check), so no deeper extraction rework was needed.
- **Milestones M0–M3 complete.** Remaining open work is appeal-gated only: wire **Context7 MCP** once
  `context7.com` is unblocked (the one outstanding M2 item).

## Run robustness + timing (2026-06-04)

A multi-agent run (topic "kubernetes") worked impressively — dozens of real fetches (kubernetes.io
docs/CVE-feed/case-studies, raw K8s source files, every alternative repo) — but **crashed** on a single
`openai.APITimeoutError`: one vLLM call exceeded the 120s timeout (long synthesis and/or concurrent
subagent calls loading the single endpoint), and that one failure aborted the entire expensive run.

Fixes: (1) **timing** — `run_gather` records wall-clock `elapsed_s` (in the run log, `coverage.json`,
and CLI summary). (2) **resilience** — `agent.invoke` is wrapped; a mid-run error marks the run
`truncated`, salvages whatever reached disk (scope/notes/code/partial report), still writes coverage,
and returns a (content-light if needed) artifact rather than crashing. (3) **timeout** — per-call LLM
timeout 120→**300s** + retries 2→**3**, env-tunable (`AER_LLM_TIMEOUT_S` / `AER_LLM_MAX_RETRIES`).
Deferred: enforced wall-clock cap + LangGraph checkpointer (resume across runs) if long runs remain flaky.

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
