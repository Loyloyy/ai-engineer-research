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
timeouts) ✅ · subagent transparency (`notes/<name>.md`) ✅. **Only remaining: wire Context7 MCP if/when
`context7.com` becomes reachable from the deploy environment.** Quickstart in `README.md`; gotchas in `DEV_NOTES.md`;
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

**Build locally, validate on the on-prem GPU server (containerized).** Code is authored in this workspace
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
in the image: the Playwright browser-download CDN isn't reachable from the deploy environment, so the build's
`playwright install` failed (silently, via `|| echo`) and `fetch_url` had no browser at runtime.

**Decision: dual-backend `fetch_url`, selected by `AER_FETCH_BACKEND` (auto|http|browser).** The
DEFAULT path is **browserless** — httpx (lightweight, follows redirects) + trafilatura (clean
boilerplate-stripped markdown) — because research sources (GitHub, docs, blogs, arxiv abstracts, raw
files) are static HTML and need no browser. The **browser** path (Crawl4AI + Playwright chromium, JS
rendering) is selectable for when it's needed, but requires the chromium binary, which requires the
Playwright download CDN to be reachable from the build environment. Install path: `playwright install
--dry-run chromium` prints the CDN host(s) → ensure they're reachable → rebuild (`WITH_BROWSER=1`, default) → set
`AER_FETCH_BACKEND=browser` (or `auto`). `auto` uses the browser only if a chromium binary is present
and falls back to http on an empty result. Graceful degradation holds throughout (unreachable/empty →
informative note or http fallback, never a crash). (Earlier same-day note said "drop the browser from
M1"; superseded — it's now optional-and-selectable rather than removed.)

## Source-reachability strategy — design for a restricted network (2026-06-03)

The deploy environment has **limited outbound network access**: only a subset of the public web is
reachable, and unreachable hosts fail with a connection reset rather than a clean error. Rather than
fight this, the researcher is built around a small set of **high-value, reliably-reachable sources** and
degrades gracefully on everything else. The reachable substrate it relies on:

- **Code forges** — GitHub (repos, raw, API, codeload, objects) + `*.github.io` docs.
- **Model/dataset hub** — Hugging Face (site, API, papers, docs, forum).
- **Package registries** — PyPI + files host; container registries (Docker Hub, GHCR, Quay, NGC).
- **Select official docs + search** — python/k8s/docker docs; Google/Bing for discovery.

**Consequence.** Stage 2's CODE mandate is viable on this substrate (GitHub + HF + PyPI + github.io docs
+ search). The gaps are papers / 3rd-party tool docs / general Q&A / blogs. The agent must (a) prefer the
reachable set, (b) not waste turns on hosts it can't reach, and (c) be honest about grounding when a key
source is unreachable (never backfill from parametric memory). The preferred-source set is kept as
env/config (env-overridable) so it expands with zero code change if more sources become reachable.

## Source prioritization + locked M1/M2 scope line (with planning chat, 2026-06-03)

**Highest-value source classes to pursue** (if/when reachable; severable, ordered by value):
- **Tier 1 (docs + papers):** `context7.com` + `mcp.context7.com` (version-specific docs aggregator,
  consumed via its MCP server — one integration replaces dozens of doc domains); `arxiv.org` +
  `export.arxiv.org` (full-text papers; HF/papers = abstracts only, not a substitute); `*.readthedocs.io`
  (wildcard — vendor-independent docs fallback so we're not single-pointed on Context7).
- **Tier 2 (background + technical discussion):** `en.wikipedia.org` + `upload.wikimedia.org`;
  `hn.algolia.com` (Hacker News full-text search API — clean JSON, no scraping; chosen over the HN site
  and over the Firebase API which is item-by-id only).
- **Tier 3 (practitioner experience; severable, ordered by ease):** `stackoverflow.com` +
  `api.stackexchange.com`; then `medium.com` + `*.substack.com`.
- **Reddit DROPPED.** A reachable domain ≠ access (free API dead; `oauth.reddit.com` needs a
  registered app + token + rate-limit handling). Rely on search snippets now; revisit + build the OAuth
  integration together only if the miss-log shows missing signal concentrates on reddit.
- **Already reachable — exploit:** full GitHub, HF (incl. `discuss.huggingface.co`, a reachable
  practitioner forum → make first-class), PyPI, container registries, Google/Bing.
- **Don't pursue:** more 3rd-party MCP doc servers (Context7 is the one; wrap GitHub/HF/PyPI REST as our
  own local tools); Wayback/archive.org/r.jina.ai/CDNs (confirmed unreachable, no proxy — fast-fail, don't
  build retry logic); npm/crates/maven/conda (Python-only scope).

**The M1/M2 line (locked).** Principle: *intelligence lives in the LOOP (M1), not the tool count (M2).*
- **M1 — lean agentic loop (prove the LOOP, not the substrate).**
  Tools: `web_search` (SearXNG) + `fetch_url` (httpx+trafilatura, HTML only — already reaches open hosts
  like GitHub raw/README, HF pages, readthedocs-if-granted, as fetchable pages, not APIs).
  Discipline (all cheap, all M1): unreachable-host fast-skip; **per-run miss-log** (telemetry of which
  sources couldn't be fetched = coverage evidence); snippet confidence-tagging; coverage-manifest scaffold in the artifact.
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

**M2 build order:** structured-API tools (GitHub → HF → PyPI; the code-scout substrate, always reachable)
→ Context7 MCP (when reachable) → the 3 subagents + dynamic spawn + lead synthesis + `code/**` output.

**M2 multi-agent VALIDATED (2026-06-03).** Structured tools (GitHub/HF/PyPI) built + GitHub live-tested.
Subagent topology built (`subagents.py`: code-scout/landscape/maturity + focused-investigator; lead
holds full toolset, subagents inherit it incl. filesystem since deepagents `tools=` REPLACES inherited)
and opt-in via `AER_MULTI_AGENT=1` (lean M1 stays default). Validated run produced: `code/**` with 7
real source files (code-scout's write_file works), an analyst-grade `comparison.md` matrix (9 frameworks
+ pairwise deep-dives + decision matrix, lead-synthesized from subagent summaries), report.md, and the
artifact. The on-prem model drove the delegation loop with no recursion error. **Remaining M2:** Context7
MCP (waits on `context7.com` becoming reachable).

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
- **Milestones M0–M3 complete.** Remaining open work is reachability-gated only: wire **Context7 MCP** if/when
  `context7.com` becomes reachable from the deploy environment (the one outstanding M2 item).

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

## Run checkpointing + resume (2026-06-08)

Cashed in the deferred "LangGraph checkpointer" above (the salvage path kept files but lost the in-flight
graph state → a full re-run on any mid-run timeout). deepagents IS a LangGraph graph, so resume is
native, not hand-rolled.

- **Mechanism.** `create_deep_agent(..., checkpointer=SqliteSaver)` (verified: 0.6.7 accepts the kwarg).
  `thread_id = run_id`; every super-step checkpoints; resume = re-invoke the same thread with `None`
  input to continue from the last checkpoint instead of restarting. New dep
  `langgraph-checkpoint-sqlite` is **lazy-imported + tolerated-absent** in `checkpoint.py` (None →
  no-resume, never a crash) so the package stays import-light for the local 3.10 box.
- **Storage = ONE shared DB + surgical cleanup** (chosen over per-run-DB with the user). `artifacts/
  checkpoints.sqlite`, one `thread_id` per run. **On a clean finish → `delete_thread(run_id)`** (verified
  present), so successful runs leave zero bloat while other runs' state is untouched; **truncated runs
  KEEP their checkpoint** (resumable). Shared-file/NFS contention is a non-issue: one run at a time
  against the single endpoint. **Retention:** a startup sweep drops checkpoints of `truncated` runs older
  than `checkpoint_retention_days` (default 7) — the run_id encodes its date, so the sweep reads
  `artifacts/*/coverage.json` (the `truncated` flag) + folder mtime, no DB timestamp query.
- **Auto-resume policy (with the user): 2 retries — 1 immediate + 1 after a backoff.** On a TRANSIENT
  failure (timeout / connection reset — classified by `is_transient_error`), `run_gather` retries within
  the same process: attempt 0 = the run, retry 1 = immediate resume, retry 2 = resume after
  `resume_backoff_s` (default 45s — lets a loaded single endpoint recover; an immediate-only retry would
  re-hit the same wall). Non-transient errors / exhausted budget → leave it `truncated` (checkpoint kept)
  and surface `--resume <run_id>` for a later **manual** cross-process resume. Salvage stays the floor.
- **Ledger persistence.** The fetch ledger is an in-memory singleton, so a cross-process `--resume` would
  start blank and lose the prior segment's fetches (→ degraded coverage/sources). `run_gather` now
  snapshots it to `run_dir/ledger.json` and restores it on resume; `elapsed_s` accumulates across
  segments. (Same-process auto-retries don't need this — the singleton survives — but persisting
  unconditionally keeps both paths consistent.)
- **Resume survives a HARD kill.** `run_gather` writes `run_meta.json` (topic+brief) BEFORE the first
  LLM call, and `resume_research` recovers inputs two-tier: partial artifact first (carries lineage/
  version; present after a caught-exception truncation), else `run_meta.json` (Ctrl-C / `docker stop`
  skip the salvage path, but the LangGraph checkpoint + run_meta are already on disk). So a deliberate
  mid-run kill is a valid way to produce a resumable truncated run for testing.
- **Contract unchanged** (rule #3). `run_research(...)` keeps its exact signature; resume rides a
  separate `resume_research(run_id)` + CLI `--resume RUN_ID` (topic/brief/lineage recovered from the
  partial artifact the truncated run already saved; the completed artifact overwrites that same version —
  it finishes the run, it is not a refinement). Knobs (all env-tunable, gitignored `.env`):
  `AER_CHECKPOINT` (0/1) · `AER_RESUME_MAX_RETRIES` · `AER_RESUME_BACKOFF_S` · `AER_CHECKPOINT_RETENTION_DAYS`.
- **Still to validate on-server (behavioral, not a one-liner):** a crash INSIDE a `task`-spawned subagent
  must resume without restarting from scratch (kill mid-subagent → `--resume` → confirm it continues).
  Also eyeball checkpoint-DB growth vs deepagents #2876 (SummarizationMiddleware not trimming messages →
  unbounded checkpoint bloat) — our delete-on-success keeps it bounded for clean runs.
- **Run management (`manage.py` + CLI).** Since a clean finish deletes its thread, "threads still in the
  shared DB" == "resumable runs" — the source of truth for `--list` / `--clean [--with-folders]` /
  `--resume-all`. `--clean` confirms before deleting (or `--yes`; refuses in a non-tty without it).
- **Orphan reaping.** The age-sweep keys off each run folder's `coverage.json`, so deleting a folder by
  hand would otherwise strand its checkpoint forever. The startup sweep now also drops threads whose run
  folder is gone → "just delete the folder" becomes eventually-sufficient (next run's sweep clears it).
- **Resume honors the original topology.** `run_meta.json` records `multi_agent`; resume passes it back so
  a multi-agent run never resumes under the lean agent (or vice-versa) — that would mismatch the
  checkpointed graph (different tools/subagents/system prompt).
- **Interactive picker, NOT a Claude skill (decided with the user).** A `/resume` skill runs where Claude
  Code runs (the user's LOCAL box), but the runs + checkpoint DB live on the SERVER and the user reaches
  it only via PuTTY — so a skill would have to SSH in (extra setup) AND keep the server host in a
  gitignored config (rule #1 bars it from any committed skill). Instead, bare `--resume` (no id) prints a
  numbered list and prompts for a selection — the same "see all + pick" UX, running in the PuTTY session
  where the work already happens, no SSH/host-config. A skill stays an option if Claude is ever run
  server-side.
- **Observability (LangSmith/Langfuse) deferred** — cloud tracers would send data off-box; if pursued
  later, self-host (a callback → `artifacts/<id>/trace.jsonl`), not a cloud endpoint.

## Observability — self-hosted Langfuse via the `service-depot` shared-infra repo (2026-06-09)

Earlier call (deferred observability as "not worth it" for a headless batch tool) **reversed** on two new
facts from the user: (a) a Gradio GUI + prompt iteration is now on the roadmap — the workload per-call
traces serve; (b) Stage 3 commits to Langfuse. So tracing is now worth wiring.

- **Self-hosting keeps trace data in-network.** A self-hosted instance runs in-network (reached by name
  like `searxng`), so traces never leave — no external SaaS dependency.
- **One instance, project-per-consumer.** Not one Langfuse per stage — ONE instance, with a Langfuse
  *project* per app (`stage-2-research`, `stage-3-poc`). Sharing is pure runtime config: each app points at
  the instance with its own project key. No cross-repo code, no secrets in tracked files.
- **Shared infra lives in its own GENERIC repo `service-depot`** (a sibling checkout alongside this repo), not
  inside a stage repo. Reasons (decided with the user): the repos are public portfolio pieces, so shared
  *platform* services (Langfuse + SearXNG; evals later) reading as their own thing demonstrates better
  judgment than burying a 6-service stack in one stage. Apps are pure consumers (env + a shared docker
  network `depot-net`); the repo is generic (not `ai-engineer-*`) because the services suit any app. Name
  chosen over `substrate`/`toolshed`/`shared-services`.
- **The `depot` launcher wraps `docker compose`, never hides it.** Compose **profiles** are the source of
  truth (`--profile stage-2` = that consumer's services); `./depot` (`up/down/status/logs/setup/connect`,
  positional args + an interactive menu) is convenience that **echoes every command it runs**, and raw
  `docker compose --profile …` stays first-class for power use + debugging. `./depot setup` = one-command
  onboarding (network, generated secrets → gitignored `.env`, data dir, compose-v2 check); `./depot connect
  <app>` prints the `LANGFUSE_*` snippet. **`depot` is a BASH script — no pip/venv/Python** (user rule:
  Docker-only host); just bash + docker compose + openssl. (Originally a Python package; reworked when the
  user flagged the `pip install`.)
- **App side is a tolerated-absent seam (`tracing.py`), mirroring the checkpointer.** Env-gated
  (`AER_TRACING`, OFF by default), lazy-imported (`langfuse` is an optional `obs` extra), None when
  absent/disabled → zero behaviour change. One `CallbackHandler` at the top-level `agent.invoke` traces the
  WHOLE run tree (lead + every subagent + tool); `session=run_id` groups every attempt + the extraction
  pass; per-attempt tags carry mode + resume/attempt #.
- **Where errors surface:** per-call failures (timeouts, subagent/tool/extraction exceptions) are auto-
  captured as ERRORED spans (pinpoint the failing node — the debugging win over coverage.json). The one LLM
  call outside the graph (`extract_artifact`) is threaded the handler so it joins the same session. Unreachable
  sources stay graceful (normal tool output) — coverage.json remains the unreached-source tally.
- **Flush-on-exit is mandatory:** the app runs via ephemeral `docker compose run --rm`, so `flush_tracer()`
  runs in `run_gather`'s `finally` and after extraction, else batched spans are lost.
- **Networking:** after Phase 4 (below), the app joins `depot-net` in the BASE compose — search now lives
  in depot too, so the network is required for every run. `./depot up stage-2` must be up first. Storage =
  local disk (named volumes on Docker's local driver; ClickHouse/MinIO misbehave on NFS).
- **SearXNG migrated into `service-depot` (Phase 4, done).** Search now lives in depot beside Langfuse
  (profile `["searxng","stage-2"]`); the app reaches `http://searxng:8080` over `depot-net` exactly as
  before. Consequence (accepted): `depot-net` is now mandatory for EVERY run (search is core), so the app's
  BASE compose joins it and `./depot up stage-2` is a prerequisite — the app repo is no longer standalone-
  runnable, which is the honest shape of a shared-services architecture. `stage-2` profile = searxng + langfuse.
- **Status:** Langfuse stack (`service-depot`) + the `depot` launcher + Stage-2 `tracing.py` wiring built &
  locally validated (logic/dry-run); end-to-end trace verification is a server step. Stack adapted from
  Langfuse's official v3 self-host compose (profiles + single-service `depot-net` exposure + telemetry-off).

## Run ergonomics: mode-tagged ids, per-run index, tunable depth/breadth, clarifying questions
Batch of UX/config changes (confirmed with the user) so a run is easier to read and tune:
- **Dead config removed.** `max_iterations`, `wall_clock_timeout_s`, `max_search_results_per_query` were in
  `RunConfig`/`pipeline.yaml` but read nowhere (search count is the agent's per-call choice via
  `web_search(max_results=…)`, 1–10). Deleted to stop documenting knobs that do nothing.
- **Run id carries the mode.** `new_artifact_id(multi_agent)` appends `-l`/`-m` AFTER the timestamp
  (`dra-<ts>-<rand>-m`) — visible at a glance without breaking the chronological `ls` sort, and nothing
  parses the id positionally (it's only a dir name + checkpoint key).
- **`00_INDEX.md` per run** (`core._write_run_index`) — lists only the files that run produced, in pipeline
  order, with one-line descriptions; `00_` sorts it to the top. Chose this over renaming files with order
  prefixes, which would break the Stage-3 contract + resume (files are read by exact name).
- **Tunable depth/breadth** (env or `pipeline.yaml`): `AER_THOROUGHNESS` (`light|standard|deep`),
  `AER_MAX_INVESTIGATORS` (focused-investigator fan-out cap; the 3 fixed subagents always run),
  `AER_CODE_MAX_REPOS`/`AER_CODE_FILES_PER_REPO` (code-scout breadth). Subagents are now built per-run by
  `subagents.build_subagents(...)` (was a static list) so the knobs inject into prompts. **Honest limit:**
  deepagents exposes no per-subagent loop counter, so thoroughness is a *prompt-injected* gather-round
  target + a scaled recursion budget (`_RECURSION_BY_THOROUGHNESS`), not an enforced iteration cap.
- **Clarifying questions** (`clarify.py`, `AER_CLARIFY`, default on). Generation lives in the package
  (`clarify_questions`/`fold_answers`) — NOT the CLI — so a planned UI reuses it and the headless
  `run_research` contract is untouched (it just gets an enriched brief). CLI prompts only on a TTY
  (`--no-clarify` to skip); the old no-op `--interactive` stub was replaced by this. Lean toward asking but
  never enforce (skipped when non-interactive). Kept `docker-compose.override.yml` over a single edited
  compose: the override pattern is standard and the only way to honor data-hygiene rule #1 (no host
  specifics in tracked files).

## Single-model setup: role-triple fallback
`build_chat_model` now resolves a role's endpoint via `_resolve_prefix`: if `<ROLE>_MODEL` is blank, it
falls back to `AER_DEFAULT_ROLE` (default `strategic`) with a logged warning. So a one-model deployment
fills ONLY `STRATEGIC_*` and leaves smart/fast/judge blank. Rationale: the live pipeline only calls
`strategic` (lead/subagents/clarify) + `smart` (extraction); `fast`/`judge` are unused until eval is wired,
so requiring four triples was friction. Sampling defaults stay keyed on the *original* role (the task
shapes temperature; only the endpoint is shared). A truly-unset default still raises a clear error.

## Customizable prompts via file overrides (not .env)
Lead + subagent prompts are overridable by dropping `config/prompts/<name>.md` (`AER_PROMPTS_DIR` to
relocate); `prompts.load_prompt(name, default)` returns the override or the baked-in default. **Chose files
over `.env`** (user asked): prompts are long multi-line markdown that fights `.env` syntax (`#`/`$`/quotes/
newlines), and they aren't secret — you WANT them tracked + diffable + reviewable, whereas `.env` is the
gitignored secrets-only file. **Granularity = body-override, code keeps the rules:** an override replaces
only the persona+method BODY; the code always appends grounding, required file outputs (report.md/notes/
code), and the injected knobs (thoroughness, fan-out budget, code-count) — so a custom prompt can't silently
drop grounding or break the artifact. Subagent prompts were refactored into `_BODIES` + `_requirements()`;
lead prompts get a code-appended `_LEAD_RULES` tail. Descriptions (dispatch hints) stay non-overridable.

## Evidence/provenance side-channel (P1+P2 reframed; Feynman-comparison handover)
Two chats (this one + a research/comparison chat) compared the repo against Feynman and converged on a
small, additive Stage-2→3 improvement, scoped deliberately.

**Root cause:** the GitHub/HF/PyPI tools fetch structured signals (stars/last-commit/archived/license) via
`r.json()`, render them to PROSE for the agent, and discard the structure (`tools/*.py` persist nothing).
The artifact's structured fields are then re-derived by the extraction LLM from that prose → lossy.

**Decision — capture the structure, enrich deterministically:**
- **NEW `evidence.py`** — a per-run side-store mirroring `runlog.py` (singleton + `configure/current/record`
  + `save/load` to `run_dir/evidence.json`, **restored on `--resume`** — same resume contract as the ledger;
  without it a cross-process resume starts empty and silently emits unenriched repos). Record shape
  `{kind,id,url,signals,gathered_at}`, generic across kinds; **github only** populated now (YAGNI).
- **`tools/github.py`** records repo JSON signals after `r.json()` (best-effort, never breaks the tool).
- **`core._finalize`** enriches each `ReferenceRepo` DETERMINISTICALLY (no LLM): join `canonical_repo(url)`
  → evidence; copy `stars/last_commit/archived/license`; `code_gathered` from the `code/` dir (tolerant of
  layout); `reproducibility` HIGH/MED/LOW from **pure-JSON signals only** (`archived`/recency/stars/license),
  `None` when unmatched. Unmatched repos keep their LLM fields and are logged (coverage signal, not a crash).
  Enrichment touches only `ReferenceRepo` metadata + `Source.origin/fetched_at` — never `evidence_ids` — so
  the §6 citation invariant is structurally safe; the artifact is re-validated before save (fail loud).
- **P2 reframed:** `Source.fetched_at` (provenance/staleness) + correct host-based `origin`
  (`raw.githubusercontent.com`→`code`, else `web`). NOT `fetch_status` (every Source is OK-by-construction →
  uniformly "ok") and NO live re-check at emit (restricted egress would false-flag live sources).

**Scoping (agreed):** this is a **provenance/metadata side-channel, strongest for `reference_repos`** — it
improves grounding, NOT findings/tech_stack synthesis (those stay LLM/prose-derived). `evidence.json` is
INTERNAL, not a contract file; the schema fields are the Stage-3 interface.

**Dispositions:** P3 (Reviewer agent) **rejected** — single-model (`AER_DEFAULT_ROLE`→strategic) means it
grades its own homework; becomes a future reflect-prompt + confidence-from-reflection improvement (per-area→
per-claim threading, non-trivial). P4 (runnable `implementation_steps` hints) **deferred** until Stage 3
exists to say what it needs. P5 (machine-readable comparison) **optional**, later.

## Stage-3-aligned prompts + numbered report citations
The lead/subagent/clarify prompts now state the FIXED objective: every run feeds the Stage-3 PoC builder, so
the deliverable is BUILD-READY material (architecture / tech stack + rationale / reference repos to template
from / implementation steps). `report.md`'s structure was reorganized into builder-oriented sections that map
to the artifact's build fields, so extraction (`extract.py`, prose→fields) has richer material to pull from.
`clarify.py` no longer asks the generic "what's the objective" (it's given) — it asks scope-specific
questions (target env/constraints, must-have capabilities, which alternatives matter). The mission + citation
format are **code-kept** (`_MISSION`/`_CITATION_RULES` in `agent.py`, assembled by the pure, testable
`compose_lead_prompt`; `_MISSION_LINE` in `build_subagents`) so a `config/prompts/` body override can't drop
them. `code-scout` additionally captures per-repo **buildability** (entry point / install+run / runnable
example) → strengthens `reference_repos` + the build plan.

**Citations:** `report.md` uses numbered inline `[n]` markers + a numbered, markdown-linked `## Sources` list
(claims trace to clickable sources). Prompt-enforced (soft, like the other prompt knobs); independent of the
machine-readable `Finding.evidence_ids`→`Source.id` layer (unchanged). Chose numbered over reference-style
for scannability. (Markdown-file reorg is a separate, deferred follow-up.)

## Web UI — FastAPI control/presentation layer + React SPA (2026-06-10)
A web UI for the headless researcher: launch/scope a run, watch it live (a pipeline diagram that lights up
per stage/subagent + a technical event/URL/token feed), prompt-engineer the lead/subagent prompts, tune the
non-secret knobs, and browse past runs. Decided with the user: **FastAPI backend wrapping the contract + a
separate React/Vite SPA** (chosen over Gradio/HTMX — richer two-audience showcase; the SPA builds in a
multi-stage Docker image, no local node). Honors **rule #3**: presentation/control ONLY — no pipeline logic
in the UI; it calls `run_research`/`resume_research` and renders events.

- **Core event seam (the one core change).** An optional, presentation-agnostic `event_callbacks: list`
  is threaded `run_research`/`resume_research` → `run_gather` → `invoke_config["callbacks"]`, **appended
  alongside** the Langfuse tracer (`agent.py`: `callbacks = [tracer?] + event_callbacks`). It rides the
  exact seam `tracing.py` proved: one handler at the top traces the WHOLE run tree (lead + subagents +
  tools) across every retry/resume attempt; `_finalize` also passes it to `extract_artifact`
  (`extra_callbacks`) so the extraction LLM call surfaces too. Empty/None → zero behaviour change, so the
  CLI path is untouched. The UI supplies a `BaseCallbackHandler` that pushes structured events onto a
  thread-safe queue; the FastAPI layer drains it to an SSE stream. Chose threading a callback list over a
  bespoke event bus because the graph already propagates LangChain callbacks for free.
- **One active run at a time (single slot).** The core uses per-process module singletons
  (`runlog._ledger`, `evidence._evidence`, the URL cache, configured per run via `configure_*`), so two
  concurrent runs would corrupt each other. The web layer enforces a single-slot `RunManager`: a 2nd
  `POST /runs` gets **409**. `run_research` is synchronous + long (~10 min multi-agent), so it runs in a
  threadpool (`run_in_executor`); the sync callback → asyncio queue bridge feeds SSE without blocking the
  loop. The live URL/coverage feed reads `runlog.current_ledger()` directly (same process); the streamed
  report is produced by polling the run-folder files (the lead writes `report.md` via `write_file`, not as
  LLM tokens), reusing the existing run artifacts rather than a parallel pipeline.
- **Edits target `config/pipeline.yaml` + `config/prompts/`, never `.env`.** Param editing is the
  non-secret pipeline knobs (validated allow-list); prompt editing writes the overridable BODY only
  (`config/prompts/<name>.md` via the existing `prompts.load_prompt` seam) — the code-kept "always
  appended" parts (mission/citations/grounding/required-outputs/injected knobs) are shown READ-ONLY. The
  **clarify** prompt gained a matching override seam (`load_prompt("clarify", …)`; added to `PROMPT_NAMES`)
  so it's tunable from the UI like the rest. `.env` (model endpoints/keys) stays out of the UI entirely.
- **Deployment.** New long-running `web` compose service (profile `["web"]`, `Dockerfile.web`), on
  `depot-net`, reached by SSH tunnel like Langfuse. Web deps are an `[ui]` extra
  (`fastapi`/`uvicorn`/`sse-starlette`, replacing the old `gradio`), lazy-imported in `webui/` so the core
  stays import-light. The one-shot `app` service is unchanged.
- **SPA built OFF-server; `frontend/dist/` committed (egress reality).** First server build failed at
  `npm install` with ECONNRESET — the deploy server's egress allows GitHub/HF/PyPI/container registries but
  **NOT the npm registry**, so a node build stage can't run on-server. So `Dockerfile.web` is Python-only
  (PyPI works) and just copies the prebuilt bundle; the SPA is built on a box with npm + internet (dev
  machine) and its `frontend/dist/` is committed (≈320 KB; minified JS/CSS, no secrets — fine for a public
  repo). Mirrors the repo's existing "tolerate-unreachable-CDN" stance (cf. the Playwright/crawl4ai chromium
  CDN). Side effect: **dropped `mermaid`** (≈2.7 MB of diagram code for a 5-node stepper) in favour of a
  tiny custom CSS diagram — keeps the committed dist small. Rebuild + recommit dist after frontend changes.
- **Status:** Phases 1 (event seam + live run stream + diagram + history) and 2 (prompt/param editors +
  clarify seam) **built**; the `tests/` pytest suite (22) + the server image build are **green on-prem**.
  Two post-build fixes: (a) request Pydantic models must live at MODULE level — with `from __future__ import
  annotations`, FastAPI couldn't resolve models nested in `create_app()`/`register_config_routes()` and
  mis-read POST/PUT bodies as query params (→ 422 on start-run / save-prompt / save-params); (b) the
  technical panel used bare `1fr` grid columns whose `auto` min-track let wide content (long URLs /
  comparison tables) overflow into the neighbour — switched to `minmax(0,1fr)` + bounded scroll regions.
  Remaining: a live run-through (esp. confirming multi-agent delegation labels — the deepagents `task` tool's
  arg keys are inferred in `events.py`). Phase 3 deferred = a replay/demo mode that re-streams a finished
  run's events from its run-folder files over the same SSE channel.

## Web UI round 2 — demo legibility + Stop/Resume over the web (2026-06-10)
Post-first-demo polish for a lecture-theatre audience. **Shell:** chatbot-style collapsible left
**sidebar** (past runs + New run + Settings + theme toggle) replacing the topbar nav; **light theme is now
the default** with a dark toggle (vars on `<html data-theme>`); the old "present" toggle is gone — larger
sizing is just the default. **Diagram legibility (non-technical viewers):** friendly node identities
(Lead→"Research Director", code-scout→"Code Finder", landscape→"Market Mapper", maturity→"Reality
Checker", focused-investigator→"Specialist"); a plain-language **phase banner** (Planning→Researching→
Cross-checking→Writing report→Complete) + a **deliverables** strip + a live **caption**, all derived in
`runner.py` via a new `_derive_phase()` → a `phase` SSE event `{label, scope, reflection, comparison,
report}` (same file-presence heuristic as `_derive_lean_stage`, both modes). Connectors rewritten as a
per-branch CSS org-chart (rail built from trimmed per-branch segments, `gap:0`) so the rail meets every
node center with no overhang (the v1 fixed-percent rail didn't line up). Delegations moved to a closed
accordion; fetch ledger + event log combined into one two-column accordion (ledger's counter row dropped —
the FetchSummary already carries those numbers — so the two tables align).
**Stop (cooperative cancellation):** a `_StopCallback(BaseCallbackHandler, raise_error=True)` in `agent.py`
raises `RunStopped` on the next LLM/tool callback when a `threading.Event` is set — because callbacks
propagate through the whole lead+subagents tree, this interrupts even mid-subagent (seconds-responsive);
`run_gather`'s except then salvages partial output and leaves the run truncated→resumable. Threaded
`stop_event` through `core.run_research`/`resume_research` → `run_gather`; `RunManager._Slot.stop_event` +
`RunManager.stop()` + `POST /api/runs/{id}/stop`; the slot ends as status `stopped`.
**Resume over the web:** `RunManager.resume()` recovers topic/brief/multi_agent from `run_meta.json`,
seeds a slot, and runs the existing `core.resume_research()` in the worker; `POST /api/runs/{id}/resume`
(409 if busy); a **Resume** button on resumable sidebar rows and on the no-report banner. Frontend also
clears any lingering "running" node on `done`/`error` (fixes the "subagent stuck blue after a truncated
run" symptom that left no report). Rebuild + recommit `frontend/dist/` as usual.

## Carried over from the GPTR repo (port + adapt)
Artifact schema/store/validate/extract (the Stage 2→3 contract); SearXNG search, Crawl4AI extract,
cross-encoder rerank — now first-class **LangChain tools**, not GPTR injections; cache; eval golden-set
+ judge. Wiki (Stage 1) integration is filesystem-native + READ-ONLY (duplicated copy, composite
backend: read-only `wiki/` + writable `artifacts/<id>/`; `index.md` entry point; ~80–370 small files →
grep suffices). BM25 vault + MCP server kept as the semantic upgrade path + Stage-3 sharing mechanism.

## Outbound network (deploy environment)
Limited outbound access — only a subset of the public web is reachable; unreachable hosts fail with a
connection reset. The reliably-reachable substrate for code gathering is the code forges, model hub, and
package/container registries (GitHub, Hugging Face, PyPI, container registries) plus search. Tools MUST
degrade gracefully (log + skip) on an unreachable host — never crash a run on a connection reset.

## Verify-on-server seams (can't be checked from the local 3.10 box)
- M0 probe end-to-end against the live vLLM endpoint (and that the model is served with tool-calling
  enabled — e.g. vLLM `--enable-auto-tool-choice` + a `--tool-call-parser`).
- The served model id may carry a LEADING SLASH — set `<ROLE>_MODEL` to exactly `GET /v1/models` →
  `data[0].id`.
