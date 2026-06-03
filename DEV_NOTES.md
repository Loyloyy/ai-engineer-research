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

## Egress allowlist (the biggest design constraint)

The server is behind a **hard egress allowlist** — most of the web TLS-resets ("Connection reset by
peer"). This shaped the whole researcher.

- **Map it empirically, don't guess.** `scripts/egress_probe.py` classifies ~120 domains as
  reachable / RESET / DNS-fail / timeout. ~28/122 were reachable.
- **Reachable substrate:** GitHub (repos/raw/api/codeload/objects), `*.github.io`, Hugging Face
  (models/api/papers/docs/blog + `discuss.huggingface.co`), PyPI, all container registries, NVIDIA,
  a few official docs (python/k8s/docker), Google + Bing. **Blocked:** arxiv, StackOverflow, Wikipedia,
  nearly all 3rd-party project docs, all blogs, npm/crates/maven.
- **There is NO proxy escape hatch** — `web.archive.org`, `archive.org`, `r.jina.ai`, and all CDNs
  (jsdelivr/unpkg/cloudflare) all reset. Don't build archive/reader-proxy retry logic; it won't work.
- **Design implications:**
  - `web_search` annotates each hit `[✓]`(reachable)/`[✗]`(blocked) so the model prefers fetchable URLs.
  - `fetch_url` **fast-skips** known-blocked hosts (instant note, no wasted turn). The reachable set is
    `domains.py`, **env-overridable** (`AER_REACHABLE_DOMAINS`) so appealed domains expand it with zero
    code change (appeal-pending domains are pre-included → they "just start working" when granted).
  - **Structured APIs beat scraping** where they exist (GitHub/HF/PyPI REST) — cleaner, attributable,
    and they're on the allowlist. This is the M2 code-scout substrate.
  - **Per-run miss-log** (`runlog.py`) records blocked-host attempts → evidence for round-2 appeals.

## Headless browser (Crawl4AI / Playwright)

- **The Playwright browser-download CDN (`cdn.playwright.dev`) is egress-blocked**, so `playwright
  install chromium` fails in the image build (silently, if you `|| echo` it) and the browser is absent
  at runtime. Symptom: `BrowserType.launch: Executable doesn't exist …`.
- **Decision: `fetch_url` is browserless by default** — `httpx` + `trafilatura` (clean
  boilerplate-stripped markdown). Research sources (GitHub/docs/blogs/arxiv) are static HTML; a browser
  is overkill *and* its CDN is blocked anyway. Browser path (Crawl4AI) is **opt-in** via
  `AER_FETCH_BACKEND=browser|auto`, gated on appealing the CDN. `auto` uses the browser only if a
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
  the run log, and the CLI summary. (Deferred: enforced wall-clock cap + LangGraph checkpointer for
  resume-across-runs, if long runs become flaky.)

## Grounding discipline (what makes it a *researcher*, not a chatbot)

- **The failure mode to avoid:** early on, with nearly all fetches egress-blocked, the agent produced a
  confident, polished report built from **search snippets + parametric memory** — *not* fetched sources.
  For a research tool that's the cardinal sin.
- **Rules baked into the prompts:** cite ONLY sources actually fetched (`fetch_url` returned content) or
  structured-API results; mark snippet/blocked sources `(unverified)`; never backfill gaps from
  background knowledge; reflect with confidence tiers (primary artifacts = HIGH, forum/snippet = MED/LOW).
- **Ground evidence in the ledger.** The artifact's `sources` are built from the URLs the run *actually
  fetched* (`runlog.fetched_urls()`), and `validate_citations` drops any `evidence_id` that doesn't
  resolve. Verified in practice: issue numbers cited in reports resolved to real fetched issue pages.
- **Coverage manifest travels with the artifact** (`model_versions.coverage`) so downstream consumers
  know the grounding boundary (reachable vs blocked source classes).
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

- **Empirical before policy.** We mapped egress (probe) *before* deciding what to appeal — turned a
  guess into a precise, defensible short list (Context7 + arxiv + readthedocs + wiki + HN-API).
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
