#!/usr/bin/env python3
"""Egress probe — classify which domains are reachable vs blocked from inside the container.

The server runs behind a hard egress allowlist (most sites TLS-reset). Before deciding what to
appeal and how to steer the agent, map reality: run this in the app container and read the table.

    docker-compose run --rm app python scripts/egress_probe.py

Classifications:
  OK <code>     reachable (any HTTP status, incl. 403/404 — the TLS handshake completed)
  RESET         connection reset by peer  -> blocked by the egress firewall
  DNS_FAIL      name resolution failed    -> DNS blocked for that host
  TIMEOUT       no response in time       -> likely silently dropped
  TLS_ERR       TLS/cert problem
  ERROR         other
"""
from __future__ import annotations

import sys

# (category, url). URLs are public; chosen to test real resources, not just roots.
TARGETS: list[tuple[str, str]] = [
    ("github", "https://github.com/langchain-ai/deepagents"),
    ("github", "https://raw.githubusercontent.com/langchain-ai/deepagents/main/README.md"),
    ("github", "https://api.github.com/repos/langchain-ai/deepagents"),
    ("github", "https://codeload.github.com/langchain-ai/deepagents/zip/refs/heads/main"),
    ("github", "https://objects.githubusercontent.com/"),
    ("github-pages", "https://langchain-ai.github.io/langgraph/"),
    ("pypi", "https://pypi.org/pypi/langchain/json"),
    ("pypi", "https://files.pythonhosted.org/"),
    ("huggingface", "https://huggingface.co/BAAI/bge-m3"),
    ("huggingface", "https://huggingface.co/api/models/BAAI/bge-m3"),
    ("arxiv", "https://arxiv.org/abs/1706.03762"),
    ("arxiv", "https://export.arxiv.org/abs/1706.03762"),
    ("docs", "https://docs.langchain.com/oss/python/deepagents/overview"),
    ("docs", "https://reference.langchain.com/python/deepagents/"),
    ("docs", "https://docs.python.org/3/"),
    ("docs", "https://readthedocs.org/"),
    ("search", "https://duckduckgo.com/"),
    ("search", "https://www.google.com/"),
    ("search", "https://www.bing.com/"),
    ("blogs", "https://medium.com/"),
    ("blogs", "https://www.reddit.com/r/LangChain/"),
    ("blogs", "https://dev.to/"),
    ("blogs", "https://www.langchain.com/"),
    ("reader-proxy", "https://r.jina.ai/https://github.com/langchain-ai/deepagents"),
    ("playwright-cdn", "https://cdn.playwright.dev/"),
]

_UA = "Mozilla/5.0 (compatible; ai-engineer-research-egress-probe/0.1)"
_TIMEOUT = 8


def classify(url: str) -> tuple[str, str]:
    import httpx

    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True, headers={"User-Agent": _UA}) as c:
            r = c.get(url)
        return "OK", str(r.status_code)
    except Exception as e:  # noqa: BLE001 — we WANT to bucket every failure mode
        msg = f"{type(e).__name__}: {e}".lower()
        if any(s in msg for s in ("name resolution", "name or service not known", "nodename", "[errno -3]", "[errno -2]", "getaddrinfo")):
            return "DNS_FAIL", type(e).__name__
        if any(s in msg for s in ("reset by peer", "errno 104", "connection reset")):
            return "RESET", type(e).__name__
        if "timed out" in msg or "timeout" in msg:
            return "TIMEOUT", type(e).__name__
        if "ssl" in msg or "certificate" in msg or "tls" in msg:
            return "TLS_ERR", type(e).__name__
        return "ERROR", f"{type(e).__name__}: {str(e)[:60]}"


def main() -> int:
    rows = []
    reachable = 0
    print(f"Probing {len(TARGETS)} targets (timeout {_TIMEOUT}s each)...\n")
    for category, url in TARGETS:
        result, detail = classify(url)
        if result == "OK":
            reachable += 1
        rows.append((category, url, result, detail))
        print(f"  {result:<9} {category:<14} {url}")

    print("\n==== summary by result ====")
    by_result: dict[str, int] = {}
    for _, _, result, _ in rows:
        by_result[result] = by_result.get(result, 0) + 1
    for k in sorted(by_result):
        print(f"  {k:<9} {by_result[k]}")
    print(f"\n  reachable (OK): {reachable}/{len(TARGETS)}")

    print("\n==== reachable hosts (candidates to rely on) ====")
    for category, url, result, _ in rows:
        if result == "OK":
            print(f"  [{category}] {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
