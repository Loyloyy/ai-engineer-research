# ai-engineer-research

**Stage 2 of a 3-part GenAI-scout system.** A custom multi-agent deep researcher built on
[LangChain `deepagents`](https://github.com/langchain-ai/deepagents). Given a topic + a curated
wiki page (the Stage-1 seed), it goes online to gather **real code** and web sources and analyzes
**limitations, alternatives, pros/cons vs alternatives, and production-readiness** — writing a run
folder (report + gathered code + comparison) and a structured artifact for the downstream PoC builder.

```
Stage 1  LLM Wiki (ai-engineer-wiki)  ──seed──▶  Stage 2  THIS  ──artifact──▶  Stage 3  PoC Builder (future)
```

The core is **headless**. The stable contract is:

```python
run_research(...) -> (report_markdown, DeepResearchArtifact)
```

## Models — no proxy

Each role binds its own OpenAI-compatible endpoint directly (vLLM or frontier); there is no
LiteLLM gateway. Configure four role triples in `.env` (see `.env.example`):

| role | use | env triple |
|------|-----|-----------|
| `strategic` | planner / lead reasoning (the tool-driving agent) | `STRATEGIC_MODEL` / `_API_BASE` / `_API_KEY` |
| `smart` | report writer / artifact extraction | `SMART_*` |
| `fast` | high-volume summarize / sub-tasks | `FAST_*` |
| `judge` | eval only (different family) | `JUDGE_*` |

`build_chat_model(role)` (`src/ai_engineer_research/models.py`) turns a triple into a `ChatOpenAI`.
**No concrete model name appears in tracked code** — it is `.env`-driven.

## Build & run (server, containerized)

Code is authored locally and run on the server in Docker (no host venv). On the server:

> The server runs **`docker-compose` v1** (hyphenated). Commands below use that form.

```bash
cp .env.example .env            # then fill in the role triples (all roles can point at the same model)
cp docker/docker-compose.override.yml.example docker/docker-compose.override.yml   # optional host bits

cd docker
docker-compose build app
```

### Milestone 0 — validate tool-calling (do this first)

deepagents is tool-call-heavy. Prove the LEAD model reliably plans, calls tools, uses results, and
finishes before building the subagent topology:

```bash
docker-compose run --rm app python scripts/m0_toolcall_probe.py            # drives $LEAD_ROLE (default strategic)
docker-compose run --rm app python scripts/m0_toolcall_probe.py --role smart
```

> **NFS note:** M0 mounts no output dirs. When M1/M2 enable the `vault_data/` and `artifacts/`
> mounts, pre-create them first (Docker root-squash blocks mkdir on NFS):
> `mkdir -p ../artifacts ../vault_data && chmod 777 ../artifacts ../vault_data`.

Exit 0 = PASS (safe to build topology). Non-zero = route LEAD to a stronger caller (frontier) and
keep on-prem for summarize/extract. The probe prints the endpoint + served id it used (never the key).

> The model must be served with **tool-calling enabled** (e.g. vLLM `--enable-auto-tool-choice` plus a
> `--tool-call-parser`). The served id may carry a leading slash — set `<ROLE>_MODEL` to exactly
> `GET <API_BASE>/models` → `data[0].id`.

### Run a research (after M0 passes)

```bash
# Lean single-agent loop (default): scope → gather → reflect → cited report + artifact
docker-compose run --rm app python -m ai_engineer_research.cli "<topic>" --brief "<context>"

# Multi-agent (code-scout / landscape / maturity + lead synthesis): adds comparison.md + code/**
docker-compose run --rm -e AER_MULTI_AGENT=1 app python -m ai_engineer_research.cli "<topic>" --brief "<context>" -v

# Seed from a Stage-1 wiki page instead of a freeform brief
docker-compose run --rm app python -m ai_engineer_research.cli "<topic>" --seed-page <Wiki-Page-Id>
```

Each run writes a timestamped folder `artifacts/<id>/`:

```
report.md · comparison.md · code/** · scope.md · reflection.md · notes/** · coverage.json · vNN.json
run_meta.json · ledger.json     (resume bookkeeping)
```

`vNN.json` is the structured **`DeepResearchArtifact`** (the Stage 2→3 contract); `coverage.json` records
grounding telemetry (fetched vs blocked) + wall-clock. Programmatic entry: `run_research(...)` in
`ai_engineer_research.core`. How it all fits together: see **`DEV_NOTES.md`** (learnings) and
**`DECISIONS.md`** (architecture log).

### Resume & manage long runs

A multi-agent run is ~10 min / ~50+ LLM calls against one endpoint, so a single transient timeout used to
throw the whole run away. Runs are now **checkpointed** (LangGraph `SqliteSaver` → shared
`artifacts/checkpoints.sqlite`): on a transient failure the run **auto-resumes** (1 immediate retry, then
1 after a backoff), and anything left unfinished can be **resumed manually**. A clean finish deletes its
checkpoint; a startup sweep clears stale/orphaned ones. (Disable with `AER_CHECKPOINT=0`.)

```bash
# Pick an unfinished run from a numbered list and resume it (interactive):
docker-compose run --rm app python -m ai_engineer_research.cli --resume

# Resume a specific run by id (mode — lean/multi-agent — is remembered automatically):
docker-compose run --rm app python -m ai_engineer_research.cli --resume <run_id>

# List / resume-all / delete unfinished runs:
docker-compose run --rm app python -m ai_engineer_research.cli --list
docker-compose run --rm app python -m ai_engineer_research.cli --resume-all
docker-compose run --rm app python -m ai_engineer_research.cli --clean [--with-folders] [--yes]
```

> The interactive picker needs a TTY — `docker-compose run` provides one by default, so **don't pass
> `-T`**. `--clean` lists what it will delete and confirms first (or `--yes`; it refuses in a non-tty
> without it). Tunable knobs (all in `.env`): `AER_CHECKPOINT` · `AER_RESUME_MAX_RETRIES` ·
> `AER_RESUME_BACKOFF_S` · `AER_CHECKPOINT_RETENTION_DAYS`.

## Observability (optional)

Per-call LLM tracing via **self-hosted Langfuse** (keeps trace data in-network; no external SaaS). It's
**off by default** and fully optional — the Langfuse stack lives in the separate **`service-depot`**
shared-services repo, and this app is a pure consumer.

```bash
# in service-depot (no pip/venv — a bash script over docker compose):
./depot up stage-2
./depot connect stage-2        # → LANGFUSE_HOST + project keys

# in this repo's .env: paste the snippet + enable
AER_TRACING=1
# and join the shared network: uncomment the depot-net block in docker-compose.override.yml
```

One `CallbackHandler` traces the whole run tree — lead + every subagent + tool + LLM call, with token
counts, latency, and **errored spans** pinpointing any failing call (the debugging win over
`coverage.json`). Traces group by `session = run_id`. With `AER_TRACING=0` (default) there's zero
behavior change and no dependency on the stack. See [`service-depot`](../service-depot) for the backend.

## Status

- **M0** ✅ on-prem tool-calling validated · **M1** ✅ lean agentic loop (scope→gather→reflect→cited
  report + artifact) · **M2** ✅ multi-agent (code-scout/landscape/maturity + structured GitHub/HF/PyPI
  tools + `code/**` gathering); Context7 MCP pending egress appeal · **M3** ✅ Stage-3 contract documented.
- **Crash-resume** ✅ checkpointed runs (LangGraph SqliteSaver) with auto-retry + manual `--resume` and
  list/clean/resume-all management commands (validated end-to-end on the server, incl. multi-agent).
- **Observability** ✅ optional self-hosted Langfuse tracing (`AER_TRACING`, off by default); backend in
  the shared [`service-depot`](../service-depot) repo. Built + locally validated; server trace check pending.
- Multi-agent mode is opt-in via `AER_MULTI_AGENT=1` (lean M1 is the default).
- **Stage-2 → Stage-3 handoff contract:** [`docs/STAGE3_CONTRACT.md`](docs/STAGE3_CONTRACT.md).

See `DECISIONS.md` for architecture and the full milestone history.

## Data hygiene

This repo is public-assumed. Server IPs, hostnames, served-model ids, NFS/model paths, and keys live
ONLY in the gitignored `.env` and `docker/docker-compose.override.yml`. Tracked files use placeholders.
