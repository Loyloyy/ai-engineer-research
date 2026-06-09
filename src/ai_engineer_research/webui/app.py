"""FastAPI app — the control/presentation surface over the headless researcher.

Built via `create_app()` so the heavy web deps (fastapi / sse-starlette) are imported only when the UI
is actually served (the `[ui]` extra), keeping the core import-light. API lives under `/api/*`; the
built React SPA (if present) is served at `/`.

Routes (Phase 1):
  POST /api/clarify            → pre-run clarifying questions
  POST /api/runs               → start the single active run (409 if busy)
  GET  /api/runs/active        → the active run's status (for reconnect)
  GET  /api/runs/{id}/stream   → SSE live event stream
  GET  /api/runs               → history list
  GET  /api/runs/{id}          → run detail (artifact + coverage + evidence + files + langfuse)
  GET  /api/runs/{id}/files/{name} → a run-folder file (path-confined)
Phase 2 prompt/param editing routes are attached by `register_config_routes` when present.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel

from ..config import ROOT
from . import history
from .runner import RunBusy, manager

logger = logging.getLogger(__name__)


# Request models MUST live at module level: with `from __future__ import annotations` the route hints are
# strings, and FastAPI resolves them against module globals — models nested inside create_app() wouldn't
# resolve, so FastAPI would mis-read the body params as query params (→ 422). (pydantic is a core dep, so
# importing BaseModel here keeps app import light; fastapi/sse-starlette stay lazy inside create_app.)
class ClarifyRequest(BaseModel):
    topic: str
    brief: str = ""


class RunRequest(BaseModel):
    topic: str
    brief: str = ""
    seed_pages: list[str] | None = None
    multi_agent: bool | None = None
    thoroughness: str | None = None
    clarifications: list[tuple[str, str]] | None = None  # [(question, answer), ...]


def _static_dir() -> Path:
    return Path(os.environ.get("AER_UI_STATIC_DIR", "").strip() or (ROOT / "frontend" / "dist"))


def create_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse
    from sse_starlette.sse import EventSourceResponse

    app = FastAPI(title="ai-engineer-research UI", version="0.1.0")

    # ---- run control ----
    @app.post("/api/clarify")
    def clarify(req: ClarifyRequest) -> dict:
        from ..clarify import clarify_questions

        return {"questions": clarify_questions(req.topic, req.brief)}

    @app.post("/api/runs")
    def start_run(req: RunRequest) -> dict:
        from ..clarify import fold_answers

        brief = req.brief
        if req.clarifications:
            brief = fold_answers(brief, [(q, a) for q, a in req.clarifications])
        try:
            run_id = manager.start(
                req.topic,
                brief,
                seed_pages=req.seed_pages,
                multi_agent=req.multi_agent,
                thoroughness=req.thoroughness,
            )
        except RunBusy as e:
            raise HTTPException(status_code=409, detail=f"a run is already active: {e}") from e
        return {"run_id": run_id}

    @app.get("/api/runs/active")
    def active_run() -> dict:
        return {"active": manager.active()}

    @app.get("/api/runs/{run_id}/stream")
    async def stream_run(run_id: str):
        return EventSourceResponse(manager.stream(run_id))

    # ---- history (read-only) ----
    @app.get("/api/runs")
    def list_runs() -> dict:
        return {"runs": history.list_runs()}

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict:
        detail = history.run_detail(run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"no run {run_id}")
        return detail

    @app.get("/api/runs/{run_id}/files/{name:path}")
    def run_file(run_id: str, name: str):
        path = history.resolve_run_file(run_id, name)
        if path is None:
            raise HTTPException(status_code=404, detail="file not found")
        # Markdown/JSON/etc. as text so the browser renders rather than downloads.
        return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))

    # ---- Phase 2 config editing (prompts + params), attached if the module is importable ----
    try:
        from .config_api import register_config_routes

        register_config_routes(app)
    except Exception as e:  # noqa: BLE001 — Phase 1 works without the editing routes
        logger.debug("config-editing routes not registered: %s", e)

    # ---- static SPA (served last so /api/* wins) ----
    _mount_spa(app)
    return app


def _mount_spa(app) -> None:
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    static = _static_dir()
    index = static / "index.html"
    if not index.is_file():
        logger.info("no built SPA at %s — serving API only", static)
        return
    # Assets under /assets, index for everything else (client-side routing fallback).
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        return FileResponse(index)


# Module-level ASGI app for `uvicorn ai_engineer_research.webui.app:app`.
# Guarded so importing this module (e.g. in tests that only touch helpers) doesn't require fastapi.
try:  # pragma: no cover - exercised only when the [ui] extra is installed
    app = create_app()
except Exception as e:  # noqa: BLE001
    app = None
    logger.debug("create_app() deferred (ui extra not installed?): %s", e)
