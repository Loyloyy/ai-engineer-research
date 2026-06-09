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

This project runs in a **restricted-network environment** with limited outbound access — only a subset of
the public web is reachable, and unreachable hosts fail with a connection reset. The reliably-reachable
substrate is **GitHub, Hugging Face, PyPI, container registries, a few official docs (python/k8s/docker),
and Google/Bing search**; many papers/Q&A/blog sources aren't reachable, and there is **no proxy escape
hatch**.

This is why the researcher leans on **structured APIs** (GitHub/HF/PyPI REST) rather than scraping, and
why it tags every source as reachable `[✓]` / unreachable `[✗]`. You don't configure this — just know that
"it didn't fetch that arxiv link" is by design, not a bug.

## 3. Where you run it

**You author code locally, but you run it on the server in Docker.** Don't try to run it on your local
box — the local Python is 3.10 and `deepagents` needs ≥3.11. Everything happens inside the container.
(Also: you handle all git; the agent never commits/pushes.)

## 4. First-time setup (on the server)

```bash
# 1. Configure models + endpoints (the only file you MUST edit)
cp .env.example .env
#    → fill in the role triples (see §5). All can point at the same model; or fill ONLY strategic
#      and leave the rest blank (they fall back to it — see §5 "single-model setup").

# 2. Optional host-specific bits (mounts, etc.)
cp docker/docker-compose.override.yml.example docker/docker-compose.override.yml

# 3. Build the image (the server uses docker-compose v1 — hyphenated)
cd docker
docker-compose build app
```

> **NFS gotcha:** before the first real run, pre-create the output dirs or Docker's root-squash will fail
> to mkdir them:
> `mkdir -p ../artifacts ../vault_data && chmod 777 ../artifacts ../vault_data`

> **Shared services (search + tracing).** SearXNG (always needed) and Langfuse (optional, `AER_TRACING`)
> live in the separate `service-depot` repo and are reached over the `depot-net` network. Bring them up
> first — in `service-depot`: `./depot setup` then `./depot up stage-2`. The app's compose joins
> `depot-net`, so a run errors with `network depot-net … not found` if depot isn't up.

## 5. Configuring models (`.env`)

There's **no model name in the code** — it's all `.env`-driven. You fill in four *roles*, each a triple
(`_MODEL` / `_API_BASE` / `_API_KEY`):

| role | what it does |
|------|--------------|
| `strategic` | the lead agent that plans + drives tools |
| `smart` | writes the report / extracts the artifact |
| `fast` | high-volume summarizing / subtasks |
| `judge` | eval only |

**Single-model setup.** Only `strategic` (lead + subagents + clarify) and `smart` (artifact extraction)
are used by the live pipeline today; `fast`/`judge` aren't called yet. Any role whose `_MODEL` is blank
**falls back to `AER_DEFAULT_ROLE`** (default `strategic`), so to run everything on one model just fill the
`STRATEGIC_*` triple and leave the rest blank (the fallback is logged when it kicks in).

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

### Clarifying questions before a run

By default, when you run on a terminal the lead first asks **2–3 clarifying questions** to sharpen scope
(intended use, constraints, environment, what "done" means); your answers are folded into the brief
before gathering starts. It's best-effort — skipped automatically when stdin isn't a TTY (so Docker batch
runs never hang), and a no-op if the model returns no questions. Disable per run with `--no-clarify`, or
globally with `AER_CLARIFY=0`. (The generator lives in `clarify.py` so a future UI can drive the same
step — the headless `run_research` contract just receives the enriched brief.)

### Tuning depth & breadth (multi-agent)

Three dials, all env-settable (or in `config/pipeline.yaml`): `AER_THOROUGHNESS` (`light`/`standard`/`deep`
— how many gather rounds each subagent does + the lead's recursion budget), `AER_MAX_INVESTIGATORS` (how
many ad-hoc focused-investigator passes the lead may spawn beyond the 3 fixed subagents), and
`AER_CODE_MAX_REPOS` / `AER_CODE_FILES_PER_REPO` (how much real code code-scout gathers).

**Soft vs. hard — important for expectations.** `AER_CODE_*`, `AER_MAX_INVESTIGATORS`, and the *depth* part
of `AER_THOROUGHNESS` are **prompt-injected**: the values are written into the agent/subagent system
prompts as targets the model is *told* to follow (e.g. "save up to 3 files each", "spawn at most 2
focused-investigators"). They're ceilings/targets, not enforced quotas — nothing in code counts and stops
the model, and it won't pad to hit a number. deepagents exposes no per-subagent loop counter, so "gather
rounds" is guidance, not a hard cap. The **one hard switch** is `AER_CLARIFY` (a real on/off code branch),
plus `AER_THOROUGHNESS` additionally raises the lead's **recursion budget** (a genuine step ceiling:
light 120 / standard 200 / deep 320) so deeper runs are *allowed* the extra turns. If you ever need a soft
knob enforced for real, that requires logic in the tools, not just prompt text.

### Customizing the agent prompts

The lead and subagent prompts have built-in defaults, but you can override any of them **without touching
code** — drop a markdown file in **`config/prompts/`** (`lead_lean.md`, `lead_multi.md`, `code-scout.md`,
`landscape.md`, `maturity.md`, `focused-investigator.md`). An override replaces that prompt's **body**
(persona + method); the code still appends the non-negotiable parts — grounding rules, required outputs
(`report.md`/`notes/*`/`code/**`), and the injected knobs (thoroughness, fan-out, code-count) — so a custom
prompt can't silently break grounding or the artifact. No file = the default. Relocate the dir with
`AER_PROMPTS_DIR`. See [`../config/prompts/README.md`](../config/prompts/README.md) for the full list.

### Resuming a crashed run + managing unfinished runs

Long runs are **checkpointed** to a shared `artifacts/checkpoints.sqlite` (LangGraph `SqliteSaver`). If a
run hits a transient failure (e.g. an endpoint timeout) it **auto-resumes** — one immediate retry, then
one after a short backoff — instead of throwing away the work. Whatever is still unfinished after that you
can resume by hand. A clean finish deletes its own checkpoint; a startup sweep clears stale + orphaned
ones. (Turn the whole thing off with `AER_CHECKPOINT=0`.)

```bash
# See all unfinished runs and pick one to resume (interactive numbered menu):
docker-compose run --rm app python -m ai_engineer_research.cli --resume

# Resume a specific run (its lean/multi-agent mode is remembered — you don't re-pass AER_MULTI_AGENT):
docker-compose run --rm app python -m ai_engineer_research.cli --resume <run_id>

# List them without resuming:
docker-compose run --rm app python -m ai_engineer_research.cli --list

# Resume every unfinished run in sequence:
docker-compose run --rm app python -m ai_engineer_research.cli --resume-all

# Delete unfinished runs' checkpoints (lists them + confirms first; --yes to skip the prompt):
docker-compose run --rm app python -m ai_engineer_research.cli --clean            # checkpoints only
docker-compose run --rm app python -m ai_engineer_research.cli --clean --with-folders --yes  # + run dirs
```

Notes:
- The interactive picker needs a terminal — `docker-compose run` allocates one by default, so **don't
  pass `-T`**.
- "Unfinished" is the source of truth: a run leaves a checkpoint **only** while incomplete (a clean finish
  deletes it), so `--list` shows exactly what's resumable.
- Resume is robust to a hard kill (Ctrl-C / `docker stop`): `run_meta.json` is written before the first
  LLM call, so the run can still be recovered even though a hard kill skips the normal salvage path.

### Observability (optional Langfuse tracing)

Off by default. When you want to *see* what a run did call-by-call (which subagent/LLM call was slow,
token counts, the exact prompt/output, and **errored spans** for failures), enable self-hosted Langfuse
tracing. The backend lives in the separate **`service-depot`** repo (self-hosted — trace data stays
in-network); this app just sends traces to it.

```bash
# 1. in service-depot (a bash script over docker compose — no pip/venv): bring up Langfuse + get keys
./depot up stage-2
./depot connect stage-2               # prints LANGFUSE_HOST + project keys

# 2. in this repo: paste those into .env, then
AER_TRACING=1
#    (the app already joins depot-net via the base compose — that's also how it reaches searxng)
```

**Reading the traces.** Each run shows up as **one session** (`sessionId = run_id`) containing **two
traces**: the **agent loop** (tagged `lean`/`multi-agent` — the substantial one: scope → search → fetch →
reflect → report, with every subagent fan-out and tool/LLM call nested) and the **extraction** pass
(tagged `extract` — the single LLM call that builds the structured artifact). They're separate because
they're two `.invoke()` entry points; the shared session links them. In the UI, start from **Sessions** →
your `dra-…` session → open the `lean`/`multi-agent` trace. Each span shows input/output, latency and
tokens; a failed call is an **errored span** (how you localize a failure — vs. `coverage.json`, which only
flags that the run truncated). With `AER_TRACING=0` (default) there's zero behavior change and no
dependency on the stack.

## 8. Reading the output

Each run writes a timestamped folder `artifacts/<id>/`. The id ends in **`-l`** (lean) or **`-m`**
(multi-agent), after the timestamp, so a glance tells you the mode while `ls` still sorts by date:

```
00_INDEX.md     ← reading guide: this run's files in pipeline order, one-line descriptions (start here)
report.md       ← the main human-readable cited report
comparison.md   ← alternatives matrix (multi-agent only)
code/**         ← real source files gathered (multi-agent only)
scope.md        ← what the agent decided to investigate
reflection.md   ← confidence tiers + seed-hypothesis verdicts
notes/**        ← per-subagent working notes (code-scout/landscape/maturity)
coverage.json   ← grounding telemetry: fetched vs blocked + wall-clock elapsed_s + truncated flag
vNN.json        ← the structured DeepResearchArtifact (the Stage 2→3 contract)
run_meta.json   ← topic/brief/mode, written before the first call → enables resume after a hard kill
ledger.json     ← fetch-ledger snapshot so coverage/sources survive a cross-process --resume
evidence.json   ← structured GitHub signals captured during the run (enriches reference_repos); internal, resume-restored
```

Each cited source now carries `fetched_at` (when it was fetched) and an `origin` (`web`/`code`). Each
`reference_repos` entry is **enriched deterministically** (copied from real GitHub data, not LLM-guessed)
with `stars` / `last_commit` / `archived` / `code_gathered` / a `reproducibility` tier — so the downstream
Stage 3 can rank which repo to build from. `evidence.json` is the internal capture behind that.

(The shared checkpoint DB lives one level up at `artifacts/checkpoints.sqlite`, not inside the run folder.)

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
| `AER_THOROUGHNESS` (standard) | per-subagent gather depth + recursion budget: `light` / `standard` / `deep` |
| `AER_MAX_INVESTIGATORS` (2) | cap on ad-hoc focused-investigator spawns (the 3 fixed subagents always run) |
| `AER_CODE_MAX_REPOS` (3) / `AER_CODE_FILES_PER_REPO` (3) | code-scout gather breadth: top-N repos × files saved each |
| `AER_CLARIFY` (1) | pre-research clarifying questions; CLI prompts on a TTY (`--no-clarify` to skip a run) |
| `AER_FETCH_BACKEND=http\|browser\|auto` | scraping backend (default `http` = httpx+trafilatura; browser is opt-in and its CDN isn't reachable anyway) |
| `AER_REACHABLE_DOMAINS` | override the preferred-source set (e.g. when a new source becomes reachable — no code change needed) |
| `AER_LLM_TIMEOUT_S` (300) / `AER_LLM_MAX_RETRIES` (3) | robustness for long runs |
| `AER_CHECKPOINT` (1) | crash-resume checkpointing; set `0` to disable |
| `AER_RESUME_MAX_RETRIES` (2) / `AER_RESUME_BACKOFF_S` (45) | auto-resume attempts + backoff before the 2nd |
| `AER_CHECKPOINT_RETENTION_DAYS` (7) | startup sweep drops truncated-run checkpoints older than this |
| `AER_TRACING` (0) | self-hosted Langfuse tracing; `1` to enable (needs the `service-depot` stack + `LANGFUSE_*`) |
| `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Langfuse connection (from `depot connect <app>`) |
| `GITHUB_TOKEN` | optional; lifts GitHub rate limit 60→5000/hr + enables code search |

## 10. Quick troubleshooting

- **"Connection reset" on a fetch** → that domain isn't reachable from this environment. Expected; the
  agent fast-skips known-unreachable hosts.
- **Tools never get called / agent gives up early** → re-run M0. If it fails, the lead model isn't
  tool-calling reliably; route it to a frontier model.
- **`permission denied` creating a mount path** → you skipped the NFS pre-create step
  (`mkdir -p … && chmod 777 …`).
- **Browser/Playwright errors** → ignore; the default `http` backend doesn't use a browser, and the
  Playwright CDN isn't reachable.
- **A run "crashed" but you still got files** → that's salvage-on-error; check `coverage.json`
  `truncated`. To finish it, resume it: `--resume` (pick from the list) or `--resume <run_id>`.
- **`--resume` says "No unfinished runs"** → every checkpoint was either cleaned on success or swept;
  nothing is resumable. `--list` shows the same set.
- **Interactive picker doesn't prompt / exits immediately** → no TTY. Don't pass `-T` to
  `docker-compose run`, or just use `--resume <run_id>` directly.

## 11. Where to go deeper

- [`REPO_GUIDE.md`](REPO_GUIDE.md) — what every folder & file means, and which run-folder files appear in each mode.
- [`../README.md`](../README.md) — the canonical quickstart.
- [`../DEV_NOTES.md`](../DEV_NOTES.md) — every gotcha and learning (network reachability, vLLM quirks,
  deepagents API traps, grounding discipline). Read this before debugging anything weird.
- [`../DECISIONS.md`](../DECISIONS.md) — the *why* behind the architecture + full M0→M3 milestone history.
- [`STAGE3_CONTRACT.md`](STAGE3_CONTRACT.md) — how the artifact feeds the future PoC Builder.
