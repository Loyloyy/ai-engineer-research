"""web_search tool — SearXNG over HTTP.

Decoupled from extraction (the fetch_url tool): search returns ranked hits (title/url/snippet);
the agent then decides which URLs to fetch in full. Degrades gracefully — a search failure returns
an informative message string, never raises, so a run never dies on a transient search error.
"""
from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_TIMEOUT_S = 20


def _searx_base() -> str:
    return os.environ.get("SEARX_URL", "http://searxng:8080").rstrip("/")


@tool(parse_docstring=True)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via SearXNG for sources, repos, docs, and discussions.

    Returns a numbered list of results, each with title, URL, and a short snippet. Use it to
    discover material, then call fetch_url on the URLs worth reading in full. Issue focused,
    specific queries; vary wording across calls to broaden coverage.

    Args:
        query: The search query. Be specific (include tool/library names, "github", "benchmark", etc.).
        max_results: How many results to return (1-10).
    """
    import httpx

    max_results = max(1, min(int(max_results), 10))
    base = _searx_base()
    try:
        with httpx.Client(timeout=_TIMEOUT_S) as client:
            resp = client.get(
                f"{base}/search",
                params={"q": query, "format": "json", "safesearch": 0},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001 — degrade gracefully, never crash the run
        logger.warning("web_search failed for %r: %s", query, e)
        return f"[web_search error: {type(e).__name__}: {e}. No results for {query!r}; try rephrasing or another query.]"

    results = (data.get("results") or [])[:max_results]
    if not results:
        return f"[web_search: no results for {query!r}. Try different keywords.]"

    from ..domains import is_reachable

    lines = [
        f"Search results for {query!r}  (✓ = fetchable in full; ✗ = blocked, snippet only — weak signal):"
    ]
    for i, r in enumerate(results, start=1):
        title = (r.get("title") or "").strip() or "(no title)"
        url = (r.get("url") or "").strip()
        snippet = " ".join((r.get("content") or "").split())[:300]
        mark = "✓" if is_reachable(url) else "✗"
        lines.append(f"{i}. [{mark}] {title}\n   {url}\n   {snippet}")
    return "\n".join(lines)
