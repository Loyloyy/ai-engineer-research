# ai-engineer-research

**Stage 2 of a 3-part GenAI-scout system.** A custom multi-agent deep researcher built on
[LangChain `deepagents`](https://github.com/langchain-ai/deepagents). Given a topic (+ an optional Stage-1
wiki seed), it goes online to gather **real code** and web sources, then analyzes limitations, alternatives,
trade-offs, and production-readiness — emitting a human report and a structured artifact for the downstream
PoC builder.

```
Stage 1  LLM Wiki  ──seed──▶  Stage 2  THIS  ──artifact──▶  Stage 3  PoC Builder (future)
```

The core is **headless** — one stable contract:

```python
run_research(...) -> (report_markdown, DeepResearchArtifact)
```

Two modes, same pipeline (only the gathering differs): **lean** (one agent; default) and **multi-agent**
(`AER_MULTI_AGENT=1` — a lead delegates to code-scout/landscape/maturity, gathers real `code/**`, builds a
comparison matrix).

## Quickstart (runs on the server, in Docker)

Authored locally, **run on the server in Docker** (local Python is 3.10; `deepagents` needs ≥3.11). You
handle all git; the agent never commits.

```bash
# 1. Shared services first (search + optional tracing) — in the sibling service-depot repo:
./depot setup && ./depot up stage-2       # app reaches searxng/langfuse by name over depot-net

# 2. Configure + build (in this repo, on the server):
cp .env.example .env                      # fill STRATEGIC_* (other roles fall back to it) — USAGE §5
cd docker && docker-compose build app     # server uses docker-compose v1 (hyphenated)

# 3. Prove tool-calling, then run:
docker-compose run --rm app python scripts/m0_toolcall_probe.py          # exit 0 = PASS
docker-compose run --rm app python -m ai_engineer_research.cli "<topic>" --brief "<context>"
docker-compose run --rm -e AER_MULTI_AGENT=1 app python -m ai_engineer_research.cli "<topic>" -v
```

> NFS pre-create before the first run: `mkdir -p ../artifacts ../vault_data && chmod 777 ../artifacts ../vault_data`.

Each run writes `artifacts/<id>-l|-m/` — start at `00_INDEX.md`, then `report.md`. The full walkthrough
(setup, models, knobs, resume/tracing, output + repository layout) lives in **[`docs/USAGE.md`](docs/USAGE.md)**.

### Web UI (optional)

A browser UI (FastAPI + a React SPA) wraps the same headless contract — **presentation/control only, no
pipeline logic**. Scope and launch a run, watch it live (a pipeline diagram that lights up + a URL/event/
token feed + the report streaming in), prompt-engineer any prompt, tune the non-secret knobs, and browse
past runs. The SPA is **built off-server** (the server's egress blocks npm) and its `frontend/dist/` is
committed, so the server image is Python-only:

```bash
# only when frontend/ changes — on any box with npm + internet, then commit frontend/dist:
cd frontend && npm install && npm run build && cd ..

# on the server (after `./depot up stage-2`):
cd docker && docker compose --profile web up -d --build web    # serves :8000
ssh -N -L 8000:localhost:8000 <user>@<server>                  # tunnel, then open http://localhost:8000
```

One active run at a time (the core uses per-process singletons); a second start returns HTTP 409. Editing
targets `config/pipeline.yaml` + `config/prompts/` only — never `.env`. See **[`docs/USAGE.md`](docs/USAGE.md) §7**.

## Documentation
- **[`docs/USAGE.md`](docs/USAGE.md)** — the full guide: setup · models · running · depth/breadth knobs ·
  prompt overrides · resume · tracing · reading output · repository layout & file reference.
- **[`docs/STAGE3_CONTRACT.md`](docs/STAGE3_CONTRACT.md)** — the frozen Stage 2→3 artifact interface.
- **[`DECISIONS.md`](DECISIONS.md)** — architecture + the full milestone log (the *why*).
- **[`DEV_NOTES.md`](DEV_NOTES.md)** — gotchas/learnings (read before debugging anything weird).
- **[`CLAUDE.md`](CLAUDE.md)** — the working agreement for contributors (human + Claude).

## Status
- **M0–M3** ✅ on-prem tool-calling validated · lean agentic loop · multi-agent (code-scout/landscape/
  maturity + structured GitHub/HF/PyPI tools + `code/**` gathering) · Stage-3 contract. Context7 MCP pending
  source reachability.
- **Crash-resume** ✅ checkpointed runs + auto-retry + `--resume` / `--list` / `--clean` / `--resume-all`.
- **Observability** ✅ optional self-hosted Langfuse (`AER_TRACING`, off by default; backend in the sibling
  [`service-depot`](../service-depot) repo).
- **Web UI** ✅ built — FastAPI control layer + SSE live-event stream + React SPA (`webui/` + `frontend/`).
  Server image build + the pytest suite are green on-prem; live run-through is the remaining validation step.

## Data hygiene
Public-assumed repo. Server IPs, hostnames, served-model ids, NFS/model paths, and keys live ONLY in the
gitignored `.env` and `docker/docker-compose.override.yml`. Tracked files use placeholders.
