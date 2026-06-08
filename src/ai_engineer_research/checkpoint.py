"""Crash-resume for long research runs — a thin wrapper over LangGraph's SqliteSaver.

A multi-agent run is ~10 min / ~50+ LLM calls against a single endpoint; the observed failure mode is
one transient timeout aborting the whole run (DECISIONS: "Run robustness + timing"). deepagents is a
LangGraph graph, so we get checkpoint/resume natively: pass a `checkpointer` into `create_deep_agent`
and re-invoke with the same `thread_id` to continue from the last super-step instead of restarting.

Storage policy (DECISIONS: "Run checkpointing + resume"):
  - ONE shared sqlite DB at `artifacts/checkpoints.sqlite`; each run = its own thread_id (= run_id).
  - On a CLEAN finish we `delete_thread(run_id)` — surgical cleanup, so successful runs leave no bloat
    while every other run's state is untouched. Truncated runs KEEP their checkpoint (they're resumable).
  - A startup sweep drops checkpoints of `truncated` runs older than the retention window.

This module never imports langgraph at module load (keeps the package import-light for the local 3.10
box, per DEV_NOTES); the saver is imported lazily and tolerated-absent (returns None → no checkpointing).
NO secrets/model/host info touches this module — it deals only in run_ids and local artifact paths.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CHECKPOINT_DB = "checkpoints.sqlite"

# Substrings that mark an error as a TRANSIENT endpoint hiccup worth auto-resuming (vs a deterministic
# logic/validation error, which a retry would only re-hit). Matched against the exception type + message.
_TRANSIENT_SIGNALS = (
    "timeout", "timed out", "connection", "reset by peer", "connection reset",
    "temporarily unavailable", "service unavailable", "bad gateway", "gateway timeout",
    "502", "503", "504",
)


def is_transient_error(exc: BaseException) -> bool:
    """True if `exc` looks like a transient network/endpoint failure (→ eligible for auto-resume)."""
    blob = f"{type(exc).__name__} {exc}".lower()
    return any(sig in blob for sig in _TRANSIENT_SIGNALS)


def checkpoint_db_path(artifacts_root: Path) -> Path:
    """Path to the shared checkpoint DB (one file for all runs; thread_id distinguishes them)."""
    return Path(artifacts_root) / CHECKPOINT_DB


def build_checkpointer(db_path: Path):
    """Open the shared SqliteSaver, or return None if the optional dep isn't installed.

    `check_same_thread=False` because deepagents/LangGraph may touch the saver from worker threads.
    The single-writer pattern (one run at a time, single endpoint) keeps SQLite-on-NFS contention a
    non-issue; callers close `saver.conn` when done.
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        logger.info("langgraph-checkpoint-sqlite not installed; running without checkpoint/resume")
        return None
    try:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()  # idempotent: create the checkpoint tables if absent
        return saver
    except Exception as e:  # noqa: BLE001 — never let checkpoint setup crash a run; degrade to no-resume
        logger.warning("could not open checkpoint DB %s (%s); running without checkpoint/resume", db_path, e)
        return None


def delete_run(saver, run_id: str) -> None:
    """Drop a single run's checkpoint rows (called on a clean finish)."""
    try:
        saver.delete_thread(run_id)
    except Exception as e:  # noqa: BLE001 — cleanup is best-effort; a leftover row is harmless
        logger.warning("could not delete checkpoint thread %s: %s", run_id, e)


def sweep_truncated(artifacts_root: Path, saver, max_age_days: int) -> int:
    """Delete checkpoints of `truncated` runs older than the retention window. Returns count removed.

    The run_id encodes its date, so we don't query the DB for timestamps — we scan the run folders'
    `coverage.json` (which carries the `truncated` flag) and use each folder's mtime as the age.
    """
    root = Path(artifacts_root)
    if not root.exists() or max_age_days <= 0:
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for cov in root.glob("*/coverage.json"):
        run_dir = cov.parent
        try:
            if run_dir.stat().st_mtime > cutoff:
                continue
            data = json.loads(cov.read_text())
        except (OSError, ValueError):
            continue
        if not data.get("truncated"):
            continue
        delete_run(saver, run_dir.name)
        removed += 1
    if removed:
        logger.info("checkpoint sweep removed %d stale truncated-run checkpoint(s)", removed)
    return removed
