"""RunManager — the single active research run, plus the queue→SSE bridge.

WHY single-slot: the core uses per-process module singletons (`runlog._ledger`, `evidence._evidence`,
the URL cache, configured per run via `configure_*`). Two concurrent runs would corrupt each other's
ledger/evidence, so we allow EXACTLY ONE active run; a second `start()` raises `RunBusy` (→ HTTP 409).

`run_research` is synchronous and long (~10 min multi-agent), so it runs in a 1-worker threadpool. The
UIEventHandler (running in that worker thread) emits events into the slot, which fans them out to any
subscribed SSE streams (a thread-safe `queue.Queue` per subscriber + a capped backlog for reconnect).
The async SSE generator drains its queue AND polls the in-process fetch ledger + the run-folder files
(report.md / scope.md / …) — reusing what the pipeline already produces, never a parallel loop.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any, AsyncIterator

from ..artifact.store import ARTIFACTS_ROOT, new_artifact_id
from ..config import load_config
from ..runlog import current_ledger
from .events import UIEventHandler

logger = logging.getLogger(__name__)

_BACKLOG_CAP = 4000          # cap the replay buffer so a very long run can't grow memory unbounded
_POLL_INTERVAL_S = 0.4       # SSE tick: drain queue + poll ledger/files
_HEARTBEAT_EVERY_S = 2.0     # emit elapsed so the UI never looks frozen
_END = "__end__"             # internal sentinel pushed when the worker finishes


class RunBusy(Exception):
    """Raised by start() when a run is already active (→ HTTP 409)."""


@dataclass
class _Slot:
    run_id: str
    topic: str
    brief: str
    multi_agent: bool
    thoroughness: str
    started_at: float
    status: str = "running"            # running | done | error
    error: str | None = None
    artifact_summary: dict | None = None
    run_dir: Path = field(default_factory=lambda: ARTIFACTS_ROOT)
    backlog: list[dict] = field(default_factory=list)
    subscribers: list[Queue] = field(default_factory=list)
    _sub_lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(self, ev: dict) -> None:
        """Fan an event out to every subscriber + append to the (capped) replay backlog."""
        with self._sub_lock:
            self.backlog.append(ev)
            if len(self.backlog) > _BACKLOG_CAP:
                del self.backlog[: len(self.backlog) - _BACKLOG_CAP]
            subs = list(self.subscribers)
        for q in subs:
            q.put(ev)

    def subscribe(self) -> tuple[Queue, list[dict]]:
        """Register a subscriber; returns (its queue, a backlog snapshot) atomically (no gap)."""
        q: Queue = Queue()
        with self._sub_lock:
            snapshot = list(self.backlog)
            self.subscribers.append(q)
        return q, snapshot

    def unsubscribe(self, q: Queue) -> None:
        with self._sub_lock:
            if q in self.subscribers:
                self.subscribers.remove(q)


class RunManager:
    """Holds the single active run + serves its event stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aer-run")
        self._slot: _Slot | None = None

    # --- control -------------------------------------------------------------------------------
    def start(
        self,
        topic: str,
        brief: str = "",
        *,
        seed_pages: list[str] | None = None,
        multi_agent: bool | None = None,
        thoroughness: str | None = None,
    ) -> str:
        """Begin a run; returns its run_id. Raises RunBusy if one is already active."""
        with self._lock:
            if self._slot is not None and self._slot.status == "running":
                raise RunBusy(self._slot.run_id)

            cfg = load_config()
            if multi_agent is not None:
                cfg.multi_agent = bool(multi_agent)
            if thoroughness:
                cfg.thoroughness = thoroughness.strip().lower()

            run_id = new_artifact_id(cfg.multi_agent)  # pre-mint so the caller can subscribe immediately
            slot = _Slot(
                run_id=run_id,
                topic=topic,
                brief=brief,
                multi_agent=cfg.multi_agent,
                thoroughness=cfg.thoroughness,
                started_at=time.time(),
                run_dir=ARTIFACTS_ROOT / run_id,
            )
            # Seed the diagram: lean stepper at "scope"; multi-agent with the lead active.
            slot.emit(
                {"type": "stage", "mode": "multi-agent" if cfg.multi_agent else "lean",
                 "node": "lead" if cfg.multi_agent else "scope", "active": True}
            )
            self._slot = slot

        self._executor.submit(self._worker, slot, cfg, list(seed_pages or []))
        logger.info("web run %s started (multi=%s thoroughness=%s)", run_id, slot.multi_agent, slot.thoroughness)
        return run_id

    def _worker(self, slot: _Slot, cfg, seed_pages: list[str]) -> None:
        handler = UIEventHandler(slot.emit)
        try:
            from ..core import run_research  # lazy: pull the agent/langchain stack only when running

            report, artifact = run_research(
                slot.topic,
                slot.brief,
                seed_pages=seed_pages or None,
                config=cfg,
                event_callbacks=[handler],
                run_id=slot.run_id,
            )
            slot.artifact_summary = self._summary(artifact)
            slot.status = "done"
            slot.emit({"type": "status", "text": "Run complete."})
        except Exception as e:  # noqa: BLE001 — surface failures to the stream, don't crash the server
            logger.exception("web run %s failed", slot.run_id)
            slot.status = "error"
            slot.error = str(e)
            slot.emit({"type": "error", "message": str(e)})
        finally:
            slot.emit({"type": _END})

    @staticmethod
    def _summary(artifact) -> dict:
        cov = (artifact.model_versions or {}).get("coverage", {}) if artifact else {}
        return {
            "id": artifact.id,
            "version": artifact.version,
            "findings": len(artifact.findings),
            "tech_stack": len(artifact.tech_stack),
            "reference_repos": len(artifact.reference_repos),
            "implementation_steps": len(artifact.implementation_steps),
            "sources": len(artifact.sources),
            "open_questions": len(artifact.open_questions),
            "coverage": cov,
        }

    def active(self) -> dict | None:
        slot = self._slot
        if slot is None:
            return None
        return {
            "run_id": slot.run_id,
            "status": slot.status,
            "topic": slot.topic,
            "multi_agent": slot.multi_agent,
            "thoroughness": slot.thoroughness,
            "elapsed_s": round(time.time() - slot.started_at, 1),
        }

    # --- streaming -----------------------------------------------------------------------------
    async def stream(self, run_id: str) -> AsyncIterator[dict]:
        """Yield SSE frames ({event, data}) for a run. Live if it's the active run, else a snapshot."""
        slot = self._slot
        if slot is None or slot.run_id != run_id:
            async for frame in self._snapshot_stream(run_id):
                yield frame
            return
        async for frame in self._live_stream(slot):
            yield frame

    async def _live_stream(self, slot: _Slot) -> AsyncIterator[dict]:
        import asyncio

        q, backlog = slot.subscribe()
        try:
            for ev in backlog:  # replay so a (re)connecting viewer catches up
                if ev.get("type") != _END:
                    yield _frame(ev)

            ledger_seen = 0
            last_report = ""
            last_lean_stage = ""
            last_heartbeat = 0.0
            ended = False

            while True:
                # 1) forward queued callback events
                drained_end = False
                while True:
                    try:
                        ev = q.get_nowait()
                    except Empty:
                        break
                    if ev.get("type") == _END:
                        drained_end = True
                        continue
                    yield _frame(ev)

                # 2) poll the in-process ledger → url + coverage feed
                ledger = current_ledger()
                attempts = list(ledger.attempts)
                for a in attempts[ledger_seen:]:
                    yield _frame({
                        "type": "url", "url": a.get("url", ""), "host": a.get("host", ""),
                        "outcome": a.get("outcome", ""), "ok": a.get("outcome") == "ok",
                    })
                if len(attempts) != ledger_seen:
                    ledger_seen = len(attempts)
                    yield _frame({"type": "coverage", **_coverage(ledger)})

                # 3) poll run-folder files → streamed report + working files + (lean) stage
                report = _read(slot.run_dir, "report.md")
                if report and report != last_report:
                    last_report = report
                    yield _frame({"type": "report", "markdown": report})
                if not slot.multi_agent:
                    stage = _derive_lean_stage(slot.run_dir, attempts)
                    if stage != last_lean_stage:
                        last_lean_stage = stage
                        yield _frame({"type": "stage", "mode": "lean", "node": stage, "active": True})

                # 4) heartbeat
                now = time.time()
                if now - last_heartbeat >= _HEARTBEAT_EVERY_S:
                    last_heartbeat = now
                    yield _frame({"type": "heartbeat", "elapsed_s": round(now - slot.started_at, 1)})

                # 5) terminate once the worker ended and the queue is drained
                if ended and q.empty():
                    break
                if drained_end or slot.status != "running":
                    ended = True

                await asyncio.sleep(_POLL_INTERVAL_S)

            # final snapshot
            files = _read_working_files(slot.run_dir)
            if files:
                yield _frame({"type": "files", **files})
            yield _frame({
                "type": "done", "run_id": slot.run_id, "status": slot.status,
                "error": slot.error, "artifact_summary": slot.artifact_summary,
            })
        finally:
            slot.unsubscribe(q)

    async def _snapshot_stream(self, run_id: str) -> AsyncIterator[dict]:
        """For a non-active (finished/historical) run: emit its report once, then done."""
        run_dir = ARTIFACTS_ROOT / run_id
        report = _read(run_dir, "report.md")
        if report:
            yield _frame({"type": "report", "markdown": report})
        files = _read_working_files(run_dir)
        if files:
            yield _frame({"type": "files", **files})
        yield _frame({"type": "done", "run_id": run_id, "status": "historical", "artifact_summary": None})


def _frame(ev: dict) -> dict:
    """An sse-starlette frame: event name + JSON data."""
    return {"event": ev.get("type", "message"), "data": json.dumps(ev)}


def _coverage(ledger) -> dict:
    m = ledger.manifest()
    return {
        "fetched_ok": m.get("fetched_ok", 0),
        "blocked_or_failed": m.get("blocked_or_failed", 0),
        "fetch_attempts": m.get("fetch_attempts", 0),
        "elapsed_s": m.get("elapsed_s"),
    }


def _read(run_dir: Path, name: str) -> str:
    p = run_dir / name
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else ""
    except OSError:
        return ""


def _read_working_files(run_dir: Path) -> dict | None:
    """scope/reflection/comparison + per-subagent notes, for the live working-files view."""
    scope = _read(run_dir, "scope.md")
    reflection = _read(run_dir, "reflection.md")
    comparison = _read(run_dir, "comparison.md")
    notes: dict[str, str] = {}
    notes_dir = run_dir / "notes"
    if notes_dir.is_dir():
        for p in sorted(notes_dir.glob("*.md")):
            notes[p.stem] = _read(notes_dir, p.name)
    if not (scope or reflection or comparison or notes):
        return None
    return {"scope": scope, "reflection": reflection, "comparison": comparison, "notes": notes}


def _derive_lean_stage(run_dir: Path, attempts: list[dict]) -> str:
    """Heuristic lean-mode stage (scope→search→fetch→reflect→report) from files + the ledger."""
    if _read(run_dir, "report.md"):
        return "report"
    if (run_dir / "reflection.md").is_file():
        return "reflect"
    if any(a.get("outcome") == "ok" for a in attempts):
        return "fetch"
    if attempts:
        return "search"
    if (run_dir / "scope.md").is_file():
        return "search"
    return "scope"


# Process-wide single instance (the single-slot constraint is process-wide).
manager = RunManager()
