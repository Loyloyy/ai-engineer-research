"""Per-run fetch ledger — the miss-log + coverage manifest.

Records every fetch_url attempt and its outcome. Two payoffs (DECISIONS: M1 discipline):
  1. unreached-source telemetry = coverage evidence (what the agent actually wanted but couldn't
     reach), and
  2. a per-run coverage manifest so the report/artifact can disclose its grounding boundary
     (which source classes were reachable vs not).

Module-level singleton, configured per run (mirrors cache.configure_default_cache). The tools append;
the run driver reads + writes the manifest at the end.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Outcome vocabulary for a fetch attempt.
OK = "ok"                       # content retrieved
EMPTY = "empty"                 # reachable but no extractable content
BLOCKED_SKIP = "blocked-skip"   # host not in the preferred-source set → skipped before the network call
RESET = "reset"                 # connection reset / unreachable at request time
ERROR = "error"                 # other failure


@dataclass
class FetchLedger:
    attempts: list[dict] = field(default_factory=list)
    elapsed_s: float | None = None   # wall-clock of the run (set by the run driver)
    truncated: bool = False          # True if the run ended early (error/timeout) → partial output

    def record(self, url: str, host: str, outcome: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self.attempts.append({"url": url, "host": host, "outcome": outcome, "ts": ts})

    def fetched_urls(self) -> list[str]:
        """URLs that actually returned content — the verifiable sources for the artifact."""
        return [a["url"] for a in self.attempts if a["outcome"] == OK]

    def fetched_at_map(self) -> dict[str, str]:
        """url -> ISO timestamp of its latest OK fetch (for Source.fetched_at provenance)."""
        out: dict[str, str] = {}
        for a in self.attempts:
            if a.get("outcome") == OK and a.get("url") and a.get("ts"):
                out[a["url"]] = a["ts"]  # later attempts overwrite → latest wins
        return out

    def manifest(self) -> dict:
        outcomes = Counter(a["outcome"] for a in self.attempts)
        ok_hosts = sorted({a["host"] for a in self.attempts if a["outcome"] == OK})
        # Anything not OK and not empty is a reach failure worth noting for coverage.
        blocked_hosts = sorted(
            {a["host"] for a in self.attempts if a["outcome"] in (BLOCKED_SKIP, RESET, ERROR) and a["host"]}
        )
        return {
            "elapsed_s": round(self.elapsed_s, 1) if self.elapsed_s is not None else None,
            "truncated": self.truncated,
            "fetch_attempts": len(self.attempts),
            "fetched_ok": outcomes.get(OK, 0),
            "empty": outcomes.get(EMPTY, 0),
            "blocked_or_failed": outcomes.get(BLOCKED_SKIP, 0) + outcomes.get(RESET, 0) + outcomes.get(ERROR, 0),
            "by_outcome": dict(outcomes),
            "fetched_hosts": ok_hosts,
            "blocked_hosts": blocked_hosts,  # unreached-source coverage evidence
        }


_ledger = FetchLedger()


def configure_ledger() -> FetchLedger:
    """Reset the ledger for a new run; returns the fresh instance."""
    global _ledger
    _ledger = FetchLedger()
    return _ledger


def current_ledger() -> FetchLedger:
    return _ledger


def record_fetch(url: str, host: str, outcome: str) -> None:
    _ledger.record(url, host, outcome)


# --- Persistence (for crash-resume) --------------------------------------------------------------
# The ledger is an in-memory singleton, so a cross-process `--resume` would otherwise start blank and
# lose the prior segment's fetches (→ degraded coverage/sources). We snapshot it to the run folder so
# resume can restore the accumulated attempts. (Auto-retries within ONE process don't need this — the
# singleton persists across attempts — but persisting unconditionally keeps both paths consistent.)

def save_ledger(ledger: FetchLedger, path: Path) -> None:
    try:
        Path(path).write_text(
            json.dumps(
                {"attempts": ledger.attempts, "elapsed_s": ledger.elapsed_s, "truncated": ledger.truncated},
                indent=2,
            )
        )
    except OSError as e:
        logger.warning("could not write ledger %s: %s", path, e)


def load_ledger(path: Path) -> FetchLedger:
    """Restore the singleton from a prior snapshot (for resume); fresh ledger if absent/unreadable."""
    global _ledger
    try:
        data = json.loads(Path(path).read_text())
        _ledger = FetchLedger(
            attempts=list(data.get("attempts", [])),
            elapsed_s=data.get("elapsed_s"),
            truncated=bool(data.get("truncated", False)),
        )
    except (OSError, ValueError):
        _ledger = FetchLedger()
    return _ledger
