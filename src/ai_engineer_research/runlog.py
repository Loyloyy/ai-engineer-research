"""Per-run fetch ledger — the miss-log + coverage manifest.

Records every fetch_url attempt and its outcome. Two payoffs (DECISIONS: M1 discipline):
  1. blocked-domain telemetry = evidence for round-2 egress appeals (what the agent actually wanted
     but couldn't reach), and
  2. a per-run coverage manifest so the report/artifact can disclose its grounding boundary
     (which source classes were reachable vs not).

Module-level singleton, configured per run (mirrors cache.configure_default_cache). The tools append;
the run driver reads + writes the manifest at the end.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# Outcome vocabulary for a fetch attempt.
OK = "ok"                       # content retrieved
EMPTY = "empty"                 # reachable but no extractable content
BLOCKED_SKIP = "blocked-skip"   # host not in reachable allowlist → skipped before the network call
RESET = "reset"                 # egress firewall reset / unreachable at request time
ERROR = "error"                 # other failure


@dataclass
class FetchLedger:
    attempts: list[dict] = field(default_factory=list)

    def record(self, url: str, host: str, outcome: str) -> None:
        self.attempts.append({"url": url, "host": host, "outcome": outcome})

    def fetched_urls(self) -> list[str]:
        """URLs that actually returned content — the verifiable sources for the artifact."""
        return [a["url"] for a in self.attempts if a["outcome"] == OK]

    def manifest(self) -> dict:
        outcomes = Counter(a["outcome"] for a in self.attempts)
        ok_hosts = sorted({a["host"] for a in self.attempts if a["outcome"] == OK})
        # Anything not OK and not empty is a reach failure worth appealing / noting.
        blocked_hosts = sorted(
            {a["host"] for a in self.attempts if a["outcome"] in (BLOCKED_SKIP, RESET, ERROR) and a["host"]}
        )
        return {
            "fetch_attempts": len(self.attempts),
            "fetched_ok": outcomes.get(OK, 0),
            "empty": outcomes.get(EMPTY, 0),
            "blocked_or_failed": outcomes.get(BLOCKED_SKIP, 0) + outcomes.get(RESET, 0) + outcomes.get(ERROR, 0),
            "by_outcome": dict(outcomes),
            "fetched_hosts": ok_hosts,
            "blocked_hosts": blocked_hosts,  # round-2 appeal evidence
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
