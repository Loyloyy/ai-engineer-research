# Using ai-engineer-research — a guide for newcomers

A from-scratch walkthrough of **ai-engineer-research** (Stage 2 of the GenAI-scout pipeline).
For the *why* behind the architecture see [`../DECISIONS.md`](../DECISIONS.md); for gotchas/learnings
see [`../DEV_NOTES.md`](../DEV_NOTES.md); for the quickstart see [`../README.md`](../README.md).

## 1. What it is (the mental model)

It's a **multi-agent deep researcher**. You give it a topic (and optionally a curated wiki page as a
seed), and it goes online to gather **real code + web sources**, then analyzes limitations, alternatives,
pros/cons, and production-readiness. It writes a **run folder** (human-readable report + gathered code)
and a **structured artifact** (the machine-readable handoff to the future Stage 3 PoC Builder).

```
Stage 1: LLM Wiki  ──seed──▶  Stage 2: THIS  ──artifact──▶  Stage 3: PoC Builder (future)
```

The whole thing is **headless**. Everything funnels through one stable function:

```python
run_research(topic, brief="", *, seed_pages=None, parent_id=None, config=None) -> (report_markdown, DeepResearchArtifact)
```

The CLI is just a thin wrapper over that.

## 2. The one rule that shapes everything

This project lives behind a **hard egress allowlist** — most of the web is unreachable (TLS-reset). Only
~28 of 122 probed domains work: **GitHub, Hugging Face, PyPI, container registries, NVIDIA, a few official
docs (python/k8s/docker), and Google/Bing search**. Blocked: arxiv, StackOverflow, Wikipedia, blogs, npm,
and all CDNs. There is **no proxy escape hatch**.

This is why the researcher leans on **structured APIs** (GitHub/HF/PyPI REST) rather than scraping, and
why it tags every source as reachable `[✓]` / blocked `[✗]`. You don't configure this — just know that
"it didn't fetch that arxiv link" is by design, not a bug.

## 3. Where you run it

**You author code locally, but you run it on the server in Docker.** Don't try to run it on your local
box — the local Python is 3.10 and `deepagents` needs ≥3.11. Everything happens inside the container.
(Also: you handle all git; the agent never commits/pushes.)

## 4. First-time setup (on the server)

```bash
# 1. Configure models + endpoints (the only file you MUST edit)
cp .env.example .env
#    → fill in the four role triples (see §5). All four can point at the same model.

# 2. Optional host-specific bits (mounts, etc.)
cp docker/docker-compose.override.yml.example docker/docker-compose.override.yml

# 3. Build the image (the server uses docker-compose v1 — hyphenated)
cd docker
docker-compose build app
```

> **NFS gotcha:** before the first real run, pre-create the output dirs or Docker's root-squash will fail
> to mkdir them:
> `mkdir -p ../artifacts ../vault_data && chmod 777 ../artifacts ../vault_data`

## 5. Configuring models (`.env`)

There's **no model name in the code** — it's all `.env`-driven. You fill in four *roles*, each a triple
(`_MODEL` / `_API_BASE` / `_API_KEY`):

| role | what it does |
|------|--------------|
| `strategic` | the lead agent that plans + drives tools |
| `smart` | writes the report / extracts the artifact |
| `fast` | high-volume summarizing / subtasks |
| `judge` | eval only |

Two vLLM quirks to watch:
- The served model id **may have a leading slash** — set `<ROLE>_MODEL` to *exactly* what
  `GET <API_BASE>/v1/models` → `data[0].id` returns.
- The model **must be served with tool-calling enabled** (vLLM `--enable-auto-tool-choice` + a
  `--tool-call-parser`). Without this, nothing works — the whole system is tool-call-driven.

## 6. ⚠️ Step zero: the M0 tool-calling probe (do this first)

Before any real research, **prove the lead model can reliably call tools and finish.** This is a
30-second sanity gate:

```bash
docker-compose run --rm app python scripts/m0_toolcall_probe.py            # tests the LEAD role
docker-compose run --rm app python scripts/m0_toolcall_probe.py --role smart
```

- **Exit 0 = PASS** → safe to run real research.
- **Non-zero** → route the lead to a stronger (frontier) model and keep on-prem for summarize/extract.

## 7. Running a research

```bash
# Default: lean single-agent loop (scope → gather → reflect → cited report + artifact)
docker-compose run --rm app python -m ai_engineer_research.cli "<topic>" --brief "<context>"

# Multi-agent: adds code-scout / landscape / maturity subagents → comparison.md + gathered code/**
docker-compose run --rm -e AER_MULTI_AGENT=1 app \
  python -m ai_engineer_research.cli "<topic>" --brief "<context>" -v

# Seed from a Stage-1 wiki page instead of a freeform brief
docker-compose run --rm app python -m ai_engineer_research.cli "<topic>" --seed-page <Wiki-Page-Id>
```

**Which mode?**
- **Lean (default)** — fast, proves the loop, produces a real cited report. Good for most quick topics.
- **Multi-agent (`AER_MULTI_AGENT=1`)** — deeper: gathers actual source files into `code/**`, builds a
  comparison matrix, reconciles contradictions. **Takes ~10 minutes and ~50+ LLM calls** — it's
  batch-oriented, so don't expect interactivity. It's robust (300s per-call timeout + salvage-on-error),
  but it's the heavy path.

## 8. Reading the output

Each run writes a timestamped folder `artifacts/<id>/`:

```
report.md       ← the main human-readable cited report
comparison.md   ← alternatives matrix (multi-agent only)
code/**         ← real source files gathered (multi-agent only)
scope.md        ← what the agent decided to investigate
reflection.md   ← confidence tiers + seed-hypothesis verdicts
notes/**        ← per-subagent working notes (code-scout/landscape/maturity)
coverage.json   ← grounding telemetry: fetched vs blocked + wall-clock elapsed_s + truncated flag
vNN.json        ← the structured DeepResearchArtifact (the Stage 2→3 contract)
```

**Where to look first:** `report.md` for the answer, then `coverage.json` to judge *how grounded* it is —
it tells you which source classes were reachable vs blocked. If `truncated: true`, a long run hit an error
and the output is salvaged-partial, not complete.

**Trust signal:** citations are validated — the artifact's `sources` come only from URLs the run
*actually fetched*, and any citation that doesn't resolve is dropped. So a cited source is a real, fetched
source (not a hallucination or a search snippet). Snippets/blocked sources are marked `(unverified)`.

## 9. Useful knobs (all env vars)

| var | effect |
|-----|--------|
| `AER_MULTI_AGENT=1` | turn on the multi-agent path |
| `AER_FETCH_BACKEND=http\|browser\|auto` | scraping backend (default `http` = httpx+trafilatura; browser is opt-in and its CDN is blocked anyway) |
| `AER_REACHABLE_DOMAINS` | override the egress allowlist (e.g. when a domain gets appealed/unblocked — no code change needed) |
| `AER_LLM_TIMEOUT_S` (300) / `AER_LLM_MAX_RETRIES` (3) | robustness for long runs |
| `GITHUB_TOKEN` | optional; lifts GitHub rate limit 60→5000/hr + enables code search |

## 10. Quick troubleshooting

- **"Connection reset" on a fetch** → that domain is egress-blocked. Expected; the agent fast-skips
  known-blocked hosts.
- **Tools never get called / agent gives up early** → re-run M0. If it fails, the lead model isn't
  tool-calling reliably; route it to a frontier model.
- **`permission denied` creating a mount path** → you skipped the NFS pre-create step
  (`mkdir -p … && chmod 777 …`).
- **Browser/Playwright errors** → ignore; the default `http` backend doesn't use a browser, and the
  Playwright CDN is blocked.
- **A run "crashed" but you still got files** → that's salvage-on-error; check `coverage.json`
  `truncated`.

## 11. Where to go deeper

- [`../README.md`](../README.md) — the canonical quickstart.
- [`../DEV_NOTES.md`](../DEV_NOTES.md) — every gotcha and learning (egress, vLLM quirks, deepagents API
  traps, grounding discipline). Read this before debugging anything weird.
- [`../DECISIONS.md`](../DECISIONS.md) — the *why* behind the architecture + full M0→M3 milestone history.
- [`STAGE3_CONTRACT.md`](STAGE3_CONTRACT.md) — how the artifact feeds the future PoC Builder.
