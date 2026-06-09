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
- Authored locally; **run on the on-prem GPU server in Docker** (no host venv/uv — do not install packages locally).
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
SearXNG + Langfuse now live in the sibling **`service-depot`** repo (shared services); the app reaches them
over `depot-net` — bring depot up first. **Web UI built** (FastAPI control/presentation layer in `webui/`
wrapping the contract + an SSE live-event stream; React/Vite SPA in `frontend/`; served by the `web` compose
service via `Dockerfile.web`, reach over an SSH tunnel; see the "Web UI" entry in `DECISIONS.md`) — local
logic validated, server end-to-end pending. Only reachability-gated work remains: Context7 MCP if/when
`context7.com` becomes reachable. See `DECISIONS.md` for the full log, `DEV_NOTES.md` for gotchas/learnings, `docs/STAGE3_CONTRACT.md`
for the Stage 2→3 handoff.

## Layout (`src/ai_engineer_research/`)
Entry points: `core.py` = `run_research(...)`, the stable contract (assemble brief → loop → extract → save)
+ the deterministic `reference_repos` enrichment in `_finalize`; `agent.py` = the lead loop
(`build_research_agent` / `run_gather`, lean `SYSTEM_PROMPT` + multi `M2_LEAD_PROMPT`); `cli.py` = CLI.
Config + models: `config.py` (`RunConfig`/`load_config`), `models.py` (`build_chat_model(role)`). Prompts
are overridable via `config/prompts/` (`prompts.py`; now incl. `clarify`); per-run telemetry in `runlog.py`
+ `evidence.py`. The Stage-3 contract is `artifact/schema.py` (`DeepResearchArtifact`) +
`extract`/`store`/`validate`. **UI** (presentation/control ONLY, rule #3): `webui/` (`app.py` FastAPI +
`events.py` callback→event handler injected via `run_research(event_callbacks=…)` + `runner.py` single-slot
RunManager + `history.py` + `config_api.py`) and `frontend/` (React SPA). `run_research` gained optional
`event_callbacks` + `run_id` params (back-compat, default-off).

**Full module-by-module map + run-folder file reference → `docs/USAGE.md` (§11 Repository layout, §8 Reading
the output).** Ops: `docker/` (no litellm;
joins external `depot-net`); searxng + langfuse live in the sibling `service-depot` repo — bring them up
first (`./depot up stage-2`).

## Key env knobs (all in gitignored `.env`)
- `<ROLE>_MODEL/_API_BASE/_API_KEY` (strategic/smart/fast/judge) · `LEAD_ROLE` · `SEARX_URL`
- `AER_DEFAULT_ROLE` (blank role triples fall back to this; default strategic — single-model setup)
- `AER_MULTI_AGENT` (0/1) · `AER_THOROUGHNESS` (light/standard/deep) · `AER_MAX_INVESTIGATORS` · `AER_CODE_MAX_REPOS` / `AER_CODE_FILES_PER_REPO`
- `AER_CLARIFY` (0/1, pre-research questions) · `AER_PROMPTS_DIR` (relocate `config/prompts/` overrides)
- `AER_FETCH_BACKEND` (http/browser/auto) · `AER_REACHABLE_DOMAINS`
- `AER_LLM_TIMEOUT_S` / `AER_LLM_MAX_RETRIES` · `GITHUB_TOKEN` (optional, lifts GH rate limit)
- `AER_CHECKPOINT` (0/1) · `AER_RESUME_MAX_RETRIES` · `AER_RESUME_BACKOFF_S` · `AER_CHECKPOINT_RETENTION_DAYS`
- `AER_TRACING` (0/1) · `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (self-hosted; via `service-depot`)
