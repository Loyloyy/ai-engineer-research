# Dev Notes

Setup gotchas and implementation learnings from building Stage 2. Generic by design (no server
specifics — those live in `.env`). Newest sections appended over time. See `DECISIONS.md` for the
*why* behind architecture choices; this file is the *how* and the traps.

## Environment & toolchain

- **Build locally, run on the server in Docker.** The dev box is Python 3.10; `deepagents` needs
  **≥3.11**, so the agent only runs inside the container. Do NOT install packages locally (no venv/uv).
- **Local verification without running** — use `python -m py_compile <files>` to catch syntax errors,
  and run the *pure-stdlib* modules directly (e.g. `seed.py`, `domains.py`, `runlog.py`) against real
  inputs. Anything that imports `langchain_openai` / `httpx` / `trafilatura` can only be exercised on
  the server. Keep packages **import-light** so the pure parts stay locally testable: e.g.
  `artifact/extract.py` lazy-imports `build_chat_model` *inside the function* so `import …artifact`
  doesn't drag in `langchain_openai`.

## Docker / docker-compose / NFS

- **The server runs `docker-compose` v1** (hyphenated). Implications: the compose file needs a
  top-level `version:` key (not `name:`); commands are `docker-compose …`. For a one-off env override
  use `docker-compose run --rm -e VAR=value app …` (used to flip `AER_MULTI_AGENT=1`).
- **NFS root-squash blocks bind-mount auto-creation.** Docker runs as root; on the NFS share root is
  squashed to `nobody`, so it **cannot `mkdir`** a bind-mount source that doesn't exist. Symptom:
  `error while creating mount source path … permission denied`. Fix: **pre-create output dirs as the
  user first** — `mkdir -p ../artifacts && chmod 777 ../artifacts` — before the mount is used. Don't
  mount dirs you don't need yet (M0 mounted none → no error).
- Files the container writes land **`nobody:nogroup`, mode 0644** — readable, and removable via the
  0777 parent. Not a problem, just expected.
- **Mount `../src` into the image** so code changes are picked up without a rebuild. Only `pyproject`
  changes (new deps) require `docker-compose build app`.

## vLLM / model factory

- **The served model id may have a LEADING SLASH.** Check `GET <API_BASE>/v1/models` → `data[0].id`
  and set `<ROLE>_MODEL` to *exactly* that (slash included). `api_key` can be any non-empty string.
- **The model must be served with tool-calling enabled** (vLLM `--enable-auto-tool-choice` + a
  `--tool-call-parser`). `deepagents` is tool-call-heavy (planning, filesystem, delegation are ALL tool
  calls) — without this, nothing works. **M0 (`scripts/m0_toolcall_probe.py`) exists to verify this
  before building any topology** on an unvalidated model.
- **Per-call timeout matters a lot** (see "Long runs" below) — default 120s is too low; we use 300s.

## Restricted outbound network (the biggest design constraint)

The deploy environment has **limited outbound network access** — only a subset of the public web is
reachable; unreachable hosts fail with a connection reset ("Connection reset by peer"). This shaped the
whole researcher.

- **Map it empirically, don't guess.** `scripts/reachability_probe.py` classifies the candidate source
  domains as reachable / RESET / DNS-fail / timeout, so source selection is grounded in reality.
- **Reachable substrate:** GitHub (repos/raw/api/codeload/objects), `*.github.io`, Hugging Face
  (models/api/papers/docs/blog + `discuss.huggingface.co`), PyPI, container registries, a few official
  docs (python/k8s/docker), Google + Bing. Many papers/Q&A/blog sources are **not reachable**.
- **No proxy escape hatch** — archive/reader-proxy services and public CDNs are unreachable too. Don't
  build archive/reader-proxy retry logic; it won't help here.
- **Design implications:**
  - `web_search` annotates each hit `[✓]`(reachable)/`[✗]`(unreachable) so the model prefers fetchable URLs.
  - `fetch_url` **fast-skips** known-unreachable hosts (instant note, no wasted turn). The preferred set is
    `domains.py`, **env-overridable** (`AER_REACHABLE_DOMAINS`) so it expands with zero
    code change if more sources become reachable (candidate domains are pre-included → they "just start working").
  - **Structured APIs beat scraping** where they exist (GitHub/HF/PyPI REST) — cleaner, attributable,
    and reliably reachable. This is the M2 code-scout substrate.
  - **Per-run miss-log** (`runlog.py`) records unreached-source attempts → coverage telemetry.

## Headless browser (Crawl4AI / Playwright)

- **The Playwright browser-download CDN (`cdn.playwright.dev`) isn't reachable** from the deploy
  environment, so `playwright install chromium` fails in the image build (silently, if you `|| echo` it)
  and the browser is absent at runtime. Symptom: `BrowserType.launch: Executable doesn't exist …`.
- **Decision: `fetch_url` is browserless by default** — `httpx` + `trafilatura` (clean
  boilerplate-stripped markdown). Research sources (GitHub/docs/blogs/arxiv) are static HTML; a browser
  is overkill *and* its CDN isn't reachable anyway. Browser path (Crawl4AI) is **opt-in** via
  `AER_FETCH_BACKEND=browser|auto`, gated on the CDN being reachable. `auto` uses the browser only if a
  chromium binary is actually present, else falls back to http.
- **Browser installs must happen at image-BUILD time** (a Dockerfile `RUN`), not via
  `docker-compose run --rm` (which discards the container — the download vanishes).
- **Content-type handling**: return raw text directly for `text/*` / markdown / json (e.g.
  `raw.githubusercontent.com` is `text/plain` — don't run it through HTML extraction; it's already clean).

## deepagents (beta) API gotchas

Pinned `deepagents==0.6.7`. Verified against the docs/reference rather than guessed (paid off):
- `create_deep_agent(model, tools, *, system_prompt, subagents, backend, …)` accepts a **`BaseChatModel`
  instance** for `model` (pass our `ChatOpenAI`), and returns a LangGraph `CompiledStateGraph` →
  invoke with `.invoke({"messages": [{"role": "user", "content": …}]})`.
- **Filesystem backend**: `from deepagents.backends.filesystem import FilesystemBackend` →
  `FilesystemBackend(root_dir="<abs>", virtual_mode=True)` writes to real disk, rooted at the run
  folder. Subagents **share** the backend (so a subagent's file is readable by the lead, and code-scout
  can write `code/**`).
- **Subagent `tools` REPLACES inherited tools entirely** — if you set `tools` on a subagent it loses the
  built-in filesystem tools (`write_file` etc.). **So we do NOT set `tools` per subagent** — they
  inherit the lead's full toolset and we scope each one's behavior via its **system prompt**. (The lead
  therefore holds the full tool set: web + GitHub/HF/PyPI + filesystem.)
- Subagent dict keys: `{name, description, system_prompt, tools?, model?, middleware?, …}`. The lead
  delegates via the **`task`** tool; there's a built-in `general-purpose` subagent. We define our own
  `focused-investigator` to guarantee the dynamic-spawn vehicle has the research tools.
- **`recursion_limit` default is 25 — far too low** for a multi-round research loop. Set it high
  (we use 200) in the `.invoke(config=…)`.

## On-prem model behaviour (the served vLLM model)

- It is a **reliable multi-step tool caller** (M0 passed cleanly) and drives the multi-agent delegation
  loop (the `task` tool) without issue.
- It does **not spontaneously call `write_todos`/plan** on trivial tasks → so the agent prompt must make
  the **scope/plan step explicit** (write `scope.md` first), not assume the model self-plans.
- **`with_structured_output` over nested pydantic works** for artifact extraction — no JSON-mode
  fallback needed. (We still keep one stricter retry + a content-light fallback for safety.)
- **A subagent with two write jobs may drop one.** `code-scout` (save `code/**` *and* write
  `notes/code-scout.md`) initially skipped the note after doing the more salient code-saving. Fix:
  phrase both as **explicit required deliverables** ("TWO required outputs … do not return until
  notes/code-scout.md exists"). If a `write_file` step is still skipped, make it the *first* action.

## Long runs & robustness

- **A full multi-agent run takes ~10 minutes** and makes **~50+ LLM calls** against the single vLLM
  endpoint. Concurrent subagent calls + long contexts make individual generations slow.
- **A single timed-out LLM call must not abort the whole run.** Original symptom: an `openai
  .APITimeoutError` deep inside a subagent crashed an otherwise-excellent ~10-min run, losing everything.
  Fixes:
  - per-call timeout **120 → 300s**, retries **2 → 3**, both env-tunable
    (`AER_LLM_TIMEOUT_S` / `AER_LLM_MAX_RETRIES`).
  - `run_gather` **wraps `agent.invoke`**: on any error it marks the run `truncated`, salvages whatever
    reached disk (scope/notes/code/partial report), still writes the coverage manifest, and returns a
    (content-light if needed) artifact — never a raw traceback.
- **Record wall-clock `elapsed_s`** (+ `truncated`) in the run ledger → surfaces in `coverage.json`,
  the run log, and the CLI summary.
- **Crash-resume via LangGraph checkpointer** (now built — see DECISIONS "Run checkpointing + resume").
  - deepagents 0.6.7's `create_deep_agent` **accepts a `checkpointer=` kwarg** (verified) → pass a
    `SqliteSaver`; no need to recompile the returned graph yourself.
  - The saver ships in a **separate package** (`langgraph-checkpoint-sqlite`, NOT in deepagents/langgraph
    core). `checkpoint.py` lazy-imports it and returns None if absent → runs degrade to no-resume, never
    crash. Construct as `SqliteSaver(sqlite3.connect(path, check_same_thread=False))` then `.setup()`
    (subagents may touch the saver from worker threads → `check_same_thread=False` is required).
  - **Resume re-invokes with `None` input + the same `{"configurable": {"thread_id": run_id}}`** — passing
    the original messages again would APPEND, not continue. `delete_thread(run_id)` (verified present)
    does the surgical on-success cleanup of the shared DB.
  - **Ledger is an in-memory singleton** → it does NOT survive a cross-process `--resume`; we snapshot it
    to `run_dir/ledger.json` and restore on resume (else coverage/sources cover only the resumed segment).
  - **SQLite on NFS**: fine here because runs are single-writer (one run at a time, single endpoint); did
    NOT enable WAL (WAL-on-NFS is itself fragile). Revisit only if runs ever overlap.
  - **Watch checkpoint-DB growth** (deepagents #2876: summarization doesn't trim `state.messages` →
    unbounded checkpoint bloat). Bounded for clean runs by delete-on-success + the truncated-run age sweep.

## Observability (self-hosted Langfuse — `tracing.py` + the `service-depot` repo)

- **Self-host (keeps trace data in-network)** — no external SaaS dependency. Backend runs in-network
  (`service-depot` repo); the app reaches `langfuse-web:3000` by name over a shared docker network
  `depot-net`. Same shape as searxng.
- **One handler traces everything.** LangChain callbacks propagate down the LangGraph tree, so a single
  `CallbackHandler` on the top-level `agent.invoke` captures lead + every subagent + tool + LLM call. The
  ONE call outside the graph (`extract_artifact`) is passed the handler explicitly so it joins the same
  `session = run_id`.
- **Flush-before-exit is mandatory.** The app runs via ephemeral `docker compose run --rm`; the Langfuse
  SDK batches, so without `flush_tracer()` (in `run_gather`'s `finally` + after extraction) the spans never
  ship. Symptom: "tracing on, run finished, no trace in the UI."
- **Import path is `from langfuse.langchain import CallbackHandler`** (v3; moved from `langfuse.callback`
  in v2). Trace attributes (session/tags/user) go via the invoke `config["metadata"]` keys
  `langfuse_session_id` / `langfuse_tags` / `langfuse_user_id`, NOT the handler constructor.
- **Tolerated-absent + env-gated** (mirrors the checkpointer): `AER_TRACING` off by default; `langfuse` is
  an optional `obs` extra; `build_tracer()` returns None if disabled/absent → zero behavior change.
- **The app joins `depot-net` in the BASE compose** — Phase 4 moved searxng into depot, so the network is
  required for every run (search + tracing both come from depot). `./depot up stage-2` must be up first; a
  bare `docker compose run app` errors with "network depot-net … not found" if depot isn't up.
- **Langfuse v3 self-host needs `docker compose` v2** (the app stack historically used v1). `depot setup`
  checks this. **Local-disk volumes only** — ClickHouse/MinIO misbehave on NFS (named volumes use Docker's
  local driver by default; relocate the data-root if it's on NFS).
- **`depot` = a BASH script wrapping compose profiles** (no pip/venv/Python — user rule is Docker-only on
  the host; just bash + docker compose + openssl). Echoes every command; raw `docker compose --profile …`
  always works. Profiles are the source of truth; the script's app map is just friendly names.

## Grounding discipline (what makes it a *researcher*, not a chatbot)

- **The failure mode to avoid:** early on, with many fetches unreachable, the agent produced a
  confident, polished report built from **search snippets + parametric memory** — *not* fetched sources.
  For a research tool that's the cardinal sin.
- **Rules baked into the prompts:** cite ONLY sources actually fetched (`fetch_url` returned content) or
  structured-API results; mark snippet/unfetched sources `(unverified)`; never backfill gaps from
  background knowledge; reflect with confidence tiers (primary artifacts = HIGH, forum/snippet = MED/LOW).
- **Ground evidence in the ledger.** The artifact's `sources` are built from the URLs the run *actually
  fetched* (`runlog.fetched_urls()`), and `validate_citations` drops any `evidence_id` that doesn't
  resolve. Verified in practice: issue numbers cited in reports resolved to real fetched issue pages.
- **Coverage manifest travels with the artifact** (`model_versions.coverage`) so downstream consumers
  know the grounding boundary (reachable vs unreached source classes).
- **Challenge the seed.** Stage-1 wiki `## Opinions` are treated as **hypotheses to verify/refute**, not
  facts — the reflect step issues an explicit confirm/contradict verdict (observed working: it refuted a
  "production-ready out of the box" claim citing four specific issues).

## Seed-builder (Stage-1 wiki parsing)

- Wiki pages are intentionally **concise**; Stage 2's job is the opposite (comprehensive). The brief
  frames the seed as a **floor, not a ceiling** ("How to use this seed" header).
- Wiki writes links as `[url](url)` → the URL regex double-matches → **dedupe URLs**.
- Parse top-level `## ` sections; **exclude `## Opinions` / `## Sources` / `## Notes`** from the body
  (Opinions/Sources are captured separately; Notes are user-owned and never seeded from).

## Process learnings

- **Empirical before policy.** We mapped source reachability (probe) *before* deciding what to prioritize —
  turned a guess into a precise, defensible short list (Context7 + arxiv + readthedocs + wiki + HN-API).
- **De-risk-first slicing.** M1 was built as slices (tools → bare gather → scope/reflect → extraction →
  wire-up), each validated on the server before the next. M0 de-risked tool-calling before topology.
- **Decompose subagents by INVESTIGATION, not report section.** The handover's 5 (one per output
  section) over-fragmented; the right cut is 3 by distinct sources+skill (code-scout / landscape /
  maturity) + dynamic spawning. Spin a subagent only when its context is heavy enough to justify
  isolation.
- **Intelligence lives in the loop, not the tool count.** M1 (lean tools, strong loop) already produces
  real cited reports; M2 adds depth (rich tools + subagents), not basic capability.
- A **planning chat** owns higher-level design; consult it (via the user) on open structural calls
  (subagent roster, whitelist strategy) rather than guessing.
