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

## Layout
- `src/ai_engineer_research/` — `models.py` (role→ChatModel factory), `config.py` (RunConfig). Core grows per milestone.
- `scripts/m0_toolcall_probe.py` — M0 tool-calling validation.
- `docker/` — Dockerfile (python:3.11-slim), compose (searxng + app; **no litellm**).
- Reusable layers to port from the sibling `deep-researcher` repo: artifact/{schema,store,validate,extract},
  scrapers/crawl4ai, rerank, cache, vault, eval — re-wrapped as LangChain **tools**, not GPTR injections.
