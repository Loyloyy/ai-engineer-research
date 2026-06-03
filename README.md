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

## Status

- **M0** ✅ on-prem tool-calling validated · **M1** ✅ lean agentic loop (scope→gather→reflect→cited
  report + artifact) · **M2** ✅ multi-agent (code-scout/landscape/maturity + structured GitHub/HF/PyPI
  tools + `code/**` gathering); Context7 MCP pending egress appeal · **M3** ✅ Stage-3 contract documented.
- Multi-agent mode is opt-in via `AER_MULTI_AGENT=1` (lean M1 is the default).
- **Stage-2 → Stage-3 handoff contract:** [`docs/STAGE3_CONTRACT.md`](docs/STAGE3_CONTRACT.md).

See `DECISIONS.md` for architecture and the full milestone history.

## Data hygiene

This repo is public-assumed. Server IPs, hostnames, served-model ids, NFS/model paths, and keys live
ONLY in the gitignored `.env` and `docker/docker-compose.override.yml`. Tracked files use placeholders.
