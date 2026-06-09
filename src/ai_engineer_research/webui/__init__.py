"""Web UI layer — a FastAPI control/presentation surface over the headless contract.

PRESENTATION + CONTROL ONLY (CLAUDE.md rule #3): this package wraps `core.run_research` /
`resume_research`, streams live events, and reads `artifacts/` for history. It holds NO pipeline logic —
the research loop lives in `agent.py`/`core.py`. Heavy web deps (fastapi/uvicorn/sse-starlette) are the
optional `[ui]` extra and are imported lazily inside `app.py`, so importing the core stays light.

Modules:
- events.py  — a LangChain BaseCallbackHandler that turns the run's callbacks into UI event dicts.
- runner.py  — the single-slot RunManager (one active run; threadpool + queue→SSE bridge).
- history.py — read-only views over artifacts/<id>/ (list + detail + run-folder files).
- app.py     — the FastAPI app + routes (built lazily via create_app()).
"""
