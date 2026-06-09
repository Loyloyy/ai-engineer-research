"""Per-run structured-evidence side-store — capture the tool JSON we'd otherwise launder through prose.

The GitHub/HF/PyPI tools fetch structured signals (stars, last-commit, license, …) and today render them
to a prose string for the agent, discarding the structure; the artifact's structured fields are then
re-derived by an LLM from that prose. This store keeps the structured facts so `core._finalize` can
enrich `ReferenceRepo` DETERMINISTICALLY (no LLM guessing, no new network calls).

Mirrors `runlog.py` exactly: a module-level singleton configured per run, appended by the tools, snapshot
to `run_dir/evidence.json` and restored on `--resume` (without this, a cross-process resume starts empty
and the url→evidence join silently misses → unenriched repos). This file is INTERNAL — not part of the
Stage-3 contract; the schema fields are the interface.

Record shape: {kind, id (canonical), url, signals: {...}, gathered_at}. Generic across kinds so HF/PyPI
slot in later with no reshape; only `github` is populated for now.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def canonical_repo(url_or_name: str | None) -> str | None:
    """Normalize a GitHub repo ref to lowercase ``owner/repo`` (or None if it isn't one).

    Handles `https://github.com/Owner/Repo`, trailing `/`, `.git`, `/tree/main`, `/blob/...`, `www.`,
    query/fragment, and a bare `owner/repo`. Used on BOTH sides of the enrichment join so it can't miss.
    """
    if not url_or_name:
        return None
    s = url_or_name.strip().split("#", 1)[0].split("?", 1)[0]
    low = s.lower()
    if "github.com/" in low:
        s = s[low.index("github.com/") + len("github.com/"):]  # path after the host
    elif "://" in s:
        return None  # a URL to some other host → not a github repo ref
    s = s.strip("/")
    parts = [p for p in s.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return None
    return f"{owner.lower()}/{repo.lower()}"


@dataclass
class EvidenceStore:
    records: list[dict] = field(default_factory=list)

    def record(self, kind: str, id: str, url: str, signals: dict) -> None:
        self.records.append(
            {
                "kind": kind,
                "id": id,
                "url": url,
                "signals": signals,
                "gathered_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get(self, canonical_id: str, kind: str = "github") -> dict | None:
        """Latest record matching (kind, canonical_id), or None. Later records win (freshest signals)."""
        match = None
        for r in self.records:
            if r.get("kind") == kind and r.get("id") == canonical_id:
                match = r
        return match


_evidence = EvidenceStore()


def configure_evidence() -> EvidenceStore:
    """Reset the store for a new run; returns the fresh instance (mirrors configure_ledger)."""
    global _evidence
    _evidence = EvidenceStore()
    return _evidence


def current_evidence() -> EvidenceStore:
    return _evidence


def record_evidence(kind: str, id: str, url: str, signals: dict) -> None:
    """Append a structured-evidence record. No-op-safe: tools call this; absence of a run is harmless."""
    _evidence.record(kind, id, url, signals)


# --- Persistence (resume parity with runlog.save_ledger/load_ledger) ------------------------------

def save_evidence(store: EvidenceStore, path: Path) -> None:
    try:
        Path(path).write_text(json.dumps({"records": store.records}, indent=2))
    except OSError as e:
        logger.warning("could not write evidence %s: %s", path, e)


def load_evidence(path: Path) -> EvidenceStore:
    """Restore the singleton from a prior snapshot (for resume); fresh store if absent/unreadable."""
    global _evidence
    try:
        data = json.loads(Path(path).read_text())
        _evidence = EvidenceStore(records=list(data.get("records", [])))
    except (OSError, ValueError):
        _evidence = EvidenceStore()
    return _evidence
