"""Manage unfinished (checkpointed) research runs: list / clean / resume-all.

A run leaves a checkpoint in the shared DB only while it is UNFINISHED — a clean finish deletes its
thread (see checkpoint.delete_run). So "threads still in the DB" == "resumable runs", which is the
source of truth here. Kept import-light (no langchain at module load): `resume_all_unfinished`
lazy-imports `core` only when it actually resumes. NO secrets/model/host info lives here — run_ids and
local artifact paths only.
"""
from __future__ import annotations

import json
import logging
import shutil

from .artifact.store import ARTIFACTS_ROOT
from .checkpoint import checkpoint_db_path, delete_threads, list_threads

logger = logging.getLogger(__name__)


def _topic_for(run_id: str) -> str:
    """Best-effort topic label: the saved (partial) artifact, else run_meta.json, else ''."""
    try:
        from .artifact import load as load_artifact

        return load_artifact(run_id).topic
    except Exception:  # noqa: BLE001
        try:
            return json.loads((ARTIFACTS_ROOT / run_id / "run_meta.json").read_text()).get("topic", "")
        except (OSError, ValueError):
            return ""


def list_unfinished() -> list[dict]:
    """The unfinished/resumable runs (one per live checkpoint thread)."""
    ids = list_threads(checkpoint_db_path(ARTIFACTS_ROOT))
    return [
        {"id": rid, "topic": _topic_for(rid), "folder_exists": (ARTIFACTS_ROOT / rid).exists()}
        for rid in ids
    ]


def clean_unfinished(delete_folders: bool = False) -> dict:
    """Delete ALL unfinished runs' checkpoints (and optionally their run folders).

    Returns {ids, threads_deleted, folders_deleted}. Destructive — callers should confirm first.
    """
    db = checkpoint_db_path(ARTIFACTS_ROOT)
    ids = list_threads(db)
    threads_deleted = delete_threads(db, ids)
    folders_deleted = 0
    if delete_folders:
        for rid in ids:
            d = ARTIFACTS_ROOT / rid
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
                folders_deleted += 1
    return {"ids": ids, "threads_deleted": threads_deleted, "folders_deleted": folders_deleted}


def resume_all_unfinished(config=None) -> dict:
    """Resume every unfinished run in sequence. Returns {resumed, failed}."""
    from .core import resume_research  # lazy: pulls the agent/langchain stack only when resuming

    resumed, failed = [], []
    for rid in [r["id"] for r in list_unfinished()]:
        try:
            resume_research(rid, config=config)
            resumed.append(rid)
        except Exception as e:  # noqa: BLE001 — one bad run shouldn't stop the batch
            logger.warning("resume %s failed: %s", rid, e)
            failed.append(rid)
    return {"resumed": resumed, "failed": failed}
