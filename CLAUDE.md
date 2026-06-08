# CLAUDE.md — working agreement for this repo

**ai-engineer-research** = Stage 2 (deep research) of a 3-part GenAI-scout system, built on LangChain
`deepagents`. Read `DECISIONS.md` for architecture + the M0→M3 milestone plan before non-trivial work.

## Hard rules
1. **Data hygiene.** Public-assumed repo. NEVER put server IPs, hostnames, served-model ids, NFS/model
   paths, or keys in tracked files. Those live only in gitignored `.env` / `docker/docker-compose.override.yml`.
   Tracked files use placeholders (`<served-model-id>`, `host.docker.internal:<port>`, `/path/to/models`).
2. **No model names in app code.** Models are `.env`-driven via `build_chat_model(role)`.
3. **Headless core.** Keep the `run_research` contract; UI (if any) holds no pipeline logic.
4. **Decouple search and extraction** (separate tools). Lazy-import heavy deps (crawl4ai/torch/gradio).
5. **Wiki is READ-ONLY.** Never write back into the Stage-1 wiki; output goes to `artifacts/`.
6. **Log non-trivial choices in `DECISIONS.md`.** Confirm the approach with the user (or the planning
   chat) before big structural moves.

## Build / run model
- Authored locally; **run on the H200 server in Docker** (no host venv/uv — do not install packages locally).
- The local box is Python 3.10; deepagents needs ≥3.11, so the agent runs only in the container.
- The **user handles ALL git** (commit/push here, pull on server). Do NOT run git commands unless asked.
- Reach in-network services by NAME (`http://searxng:8080`); reach host vLLM via `host.docker.internal`.
- There is a **planning chat** that designed this work — consult it (via the user) on genuinely open
  structural decisions.

## Status
M0–M3 built & validated end-to-end (single-agent **and** multi-agent) on the on-prem model. **Crash-resume
built & validated** (checkpointed runs + auto-retry + `--resume`/`--list`/`--clean`/`--resume-all`; see the
"Run checkpointing + resume" entry in `DECISIONS.md`). **Observability built** (optional self-hosted Langfuse
via `tracing.py`; backend in the sibling `service-depot` repo; locally validated, server trace-check pending).
Only appeal-gated work remains: Context7 MCP once `context7.com` is unblocked. **Deferred:** migrating SearXNG
into `service-depot` (search is core → would make `depot-net` mandatory for all runs). See `DECISIONS.md` for
the full log, `DEV_NOTES.md` for gotchas/learnings, `docs/STAGE3_CONTRACT.md` for the Stage 2→3 handoff.

## Layout (`src/ai_engineer_research/`)
- `core.py` — `run_research(...)`, the stable contract (assemble brief → loop → extract → save).
- `agent.py` — the lead research loop: lean M1 (`SYSTEM_PROMPT`) + multi-agent M2 (`M2_LEAD_PROMPT`),
  `build_research_agent(multi_agent=)`, `run_gather(...)` (timing + salvage-on-error).
- `subagents.py` — M2 subagent specs: code-scout / landscape / maturity + focused-investigator.
- `models.py` — `build_chat_model(role)` → `ChatOpenAI` (role→model factory; env timeout/retries).
- `config.py` — `RunConfig` + `load_config` (`.env` + `config/pipeline.yaml`).
- `seed.py` — Stage-1 wiki page → research brief (Opinions=hypotheses, Sources, 1-hop links).
- `domains.py` — reachable-domain policy (egress allowlist, env-overridable).
- `runlog.py` — per-run fetch ledger → miss-log + coverage manifest (+ elapsed/truncated); persisted to
  `ledger.json` for resume.
- `checkpoint.py` — crash-resume via LangGraph SqliteSaver (shared `artifacts/checkpoints.sqlite`;
  delete-on-success; startup sweep of stale-truncated + orphaned threads). `core.resume_research`.
- `tracing.py` — optional self-hosted Langfuse tracing (env-gated `AER_TRACING`, lazy/tolerated-absent like
  `checkpoint.py`). One CallbackHandler at `agent.invoke` traces the whole tree; backend = `service-depot`.
- `manage.py` — list/clean/resume-all unfinished (checkpointed) runs; backs CLI `--list` / `--clean`
  `[--with-folders]` / `--resume-all` / `--resume <id>` / bare `--resume` (interactive numbered picker).
  Resume honors the run's original `multi_agent` mode (persisted in `run_meta.json`).
- `tools/` — `search.py` (SearXNG), `scrape.py` (browserless `fetch_url`), `github.py`/`hf.py`/`pypi.py`
  (M2 structured APIs). `WEB_TOOLS` (lean M1) vs `STRUCTURED_TOOLS`.
- `artifact/` — `schema.py` (DeepResearchArtifact), `store.py`, `validate.py`, `extract.py`.
- `cache/store.py` — URL-keyed content cache (shared across subagents). `cli.py` — CLI entrypoint.
- `scripts/` — `m0_toolcall_probe.py`, `egress_probe.py`. `docker/` — Dockerfile + compose (searxng +
  app; **no litellm**).

## Key env knobs (all in gitignored `.env`)
- `<ROLE>_MODEL/_API_BASE/_API_KEY` (strategic/smart/fast/judge) · `LEAD_ROLE` · `SEARX_URL`
- `AER_MULTI_AGENT` (0/1) · `AER_FETCH_BACKEND` (http/browser/auto) · `AER_REACHABLE_DOMAINS`
- `AER_LLM_TIMEOUT_S` / `AER_LLM_MAX_RETRIES` · `GITHUB_TOKEN` (optional, lifts GH rate limit)
- `AER_CHECKPOINT` (0/1) · `AER_RESUME_MAX_RETRIES` · `AER_RESUME_BACKOFF_S` · `AER_CHECKPOINT_RETENTION_DAYS`
- `AER_TRACING` (0/1) · `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (self-hosted; via `service-depot`)
