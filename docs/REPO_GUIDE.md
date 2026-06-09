# Repository guide — what every folder & file means

A map of the repo for newcomers: what each top-level folder is for, what each module in the package does,
and — crucially — **what each file in a research run folder means, and in which mode it appears.** For the
*why* behind the design see [`../DECISIONS.md`](../DECISIONS.md); for how to run it see [`USAGE.md`](USAGE.md).

---

## 1. Top-level layout

| Path | What it is |
|------|------------|
| `src/ai_engineer_research/` | The Python package — all pipeline logic (see §2). |
| `config/` | Non-secret runtime knobs. `pipeline.yaml` (lead role, depth/breadth, clarify, artifact); `prompts/` (optional `<name>.md` files to override lead/subagent prompt bodies — defaults are in code). Env vars override these. |
| `docker/` | How it runs: `Dockerfile` (the app image), `docker-compose.yml` (tracked, placeholder-clean), `docker-compose.override.yml.example` (copy → gitignored override for host-specific mounts/GPU). |
| `docs/` | Long-form docs: `USAGE.md` (operator walkthrough), `STAGE3_CONTRACT.md` (the frozen Stage 2→3 interface), this guide. |
| `scripts/` | Operational probes (not unit tests): `m0_toolcall_probe.py` (does the lead model reliably tool-call + finish? — the go/no-go gate), `reachability_probe.py` (which source domains this network can reach). |
| `artifacts/` | Output. One folder per run (`dra-…`); plus the shared `checkpoints.sqlite`. **Gitignored.** See §3. |
| `.env` / `docker-compose.override.yml` | **Gitignored** — the ONLY place for secrets/host specifics (model ids, endpoints, keys, paths). Tracked files use placeholders. |
| `README.md` · `DECISIONS.md` · `DEV_NOTES.md` · `CLAUDE.md` | Quickstart · architecture + milestone log · gotchas/learnings · the repo's working agreement. |
| `pyproject.toml` | Package metadata + dependency extras (`web`, `browser`, `obs`, …). |

---

## 2. The package (`src/ai_engineer_research/`)

| Module | Responsibility |
|--------|----------------|
| `core.py` | `run_research(...)` / `resume_research(...)` — the **stable headless contract**: assemble brief → run loop → ground sources → extract → save versioned artifact → write `00_INDEX.md`. |
| `agent.py` | The lead research loop. Lean prompt (`SYSTEM_PROMPT`) + multi-agent lead prompt (`M2_LEAD_PROMPT`), `build_research_agent(multi_agent=)`, `run_gather(...)` (timing, salvage-on-error, checkpoint/resume, recursion budget). |
| `subagents.py` | `build_subagents(...)` — the M2 roster (code-scout / landscape / maturity + focused-investigator), with the thoroughness + code-breadth knobs injected into prompts. |
| `clarify.py` | Pre-research clarifying questions (`clarify_questions` / `fold_answers`); reusable by the CLI and a future UI. |
| `prompts.py` | `load_prompt(name, default)` — optional prompt-body overrides from `config/prompts/<name>.md` (`AER_PROMPTS_DIR` to relocate). |
| `models.py` | `build_chat_model(role)` → `ChatOpenAI`. Role→endpoint factory; unset roles fall back to `AER_DEFAULT_ROLE` (default strategic). No model name in code. |
| `config.py` | `RunConfig` + `load_config` (`.env` + `pipeline.yaml`, env overrides). |
| `seed.py` | Stage-1 wiki page → research brief (hypotheses, sources, 1-hop links). Wiki is READ-ONLY. |
| `domains.py` | Preferred / reachable source-domain policy (the `[✓]`/`[✗]` tagging; env-overridable). |
| `runlog.py` | Per-run fetch ledger → miss-log + coverage manifest; persisted to `ledger.json` for resume. |
| `checkpoint.py` | Crash-resume via LangGraph SqliteSaver (shared `checkpoints.sqlite`; delete-on-success; stale sweep). |
| `tracing.py` | Optional self-hosted Langfuse tracing (env-gated `AER_TRACING`; backend in `service-depot`). |
| `manage.py` | List / clean / resume-all unfinished runs (backs the CLI `--list` / `--clean` / `--resume-all`). |
| `cli.py` | CLI entrypoint — a thin wrapper over `core.run_research` (+ clarify prompting, resume management). |
| `tools/` | `search.py` (SearXNG), `scrape.py` (`fetch_url`), `github.py` / `hf.py` / `pypi.py` (structured APIs). `WEB_TOOLS` (lean) vs `STRUCTURED_TOOLS` (multi-agent). |
| `artifact/` | `schema.py` (`DeepResearchArtifact`), `store.py` (versioned save/load + `new_artifact_id`), `validate.py`, `extract.py` (the M3 extraction pass). |
| `cache/store.py` | URL-keyed content cache, shared across subagents within a run. |

---

## 3. A research run folder (`artifacts/<id>/`)

The run id ends in **`-l`** (lean) or **`-m`** (multi-agent) — after the timestamp, so `ls` still sorts by
date. Which files appear depends on the mode:

| File / dir | Meaning | Mode |
|------------|---------|------|
| `00_INDEX.md` | Reading guide: this run's files in pipeline order, with one-line descriptions. Sorts to the top. | both |
| `run_meta.json` | Run inputs (topic / brief / mode), written **before** the first LLM call → enables resume after a hard kill. | both |
| `scope.md` | The agent's sharp research question, sub-questions, success criteria, assumptions. | both |
| `reflection.md` | Gap analysis: which criteria are met, which sub-questions are thin, and whether evidence **confirms/contradicts** the seed hypotheses. | both |
| `report.md` | **The main human-readable cited report — read this first.** | both |
| `coverage.json` | Grounding telemetry: fetched-OK vs blocked/failed, `elapsed_s`, and a `truncated` flag (true = salvaged-partial). | both |
| `ledger.json` | Fetch-ledger snapshot so coverage/sources survive a cross-process `--resume`. | both |
| `vNN.json` | The structured **`DeepResearchArtifact`** — the machine-readable Stage 2→3 contract. `v01`, `v02`… are refinement versions. | both |
| `notes/**` | Per-subagent working notes (`code-scout.md`, `landscape.md`, `maturity.md`, `focused-<slug>.md`) — each subagent's *full* findings (the lead only gets their concise summary). | **multi-agent only** |
| `code/**` | Real source files gathered by code-scout, laid out as `code/<owner-repo>/<file>`. | **multi-agent only** |
| `comparison.md` | Subject-vs-alternatives matrix, built by the lead from the landscape subagent's data. | **multi-agent only** |

> The shared checkpoint DB (`artifacts/checkpoints.sqlite`) lives **one level up**, not inside a run folder.

**Quick way to tell modes apart:** a folder ending `-m` (or containing `notes/` / `code/` / `comparison.md`)
was multi-agent; `-l` (just `report.md` + `scope.md` + `reflection.md`) was the lean single-agent loop.
The authoritative source is `run_meta.json`'s `multi_agent` field.

---

## 4. The two modes in one line each

- **Lean (default)** — one agent: scope → search/fetch → reflect → cited `report.md` + artifact. Fast.
- **Multi-agent (`AER_MULTI_AGENT=1`)** — a lead delegates to code-scout/landscape/maturity (+ ad-hoc
  focused-investigators), gathering real `code/**` and building `comparison.md`. Deeper, ~10 min / 50+ calls.

Both run the *same* `run_research` pipeline; only the gathering step differs. See [`USAGE.md`](USAGE.md) §7–8.
