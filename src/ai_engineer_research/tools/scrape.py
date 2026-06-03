"""fetch_url tool — clean full-page extraction via Crawl4AI.

Query-agnostic clean extraction (Crawl4AI PruningContentFilter -> fit_markdown). Lazy-imports
crawl4ai so the package imports without the heavy dep. Degrades gracefully: paywalls / 403s /
timeouts / TLS resets / crawl4ai-not-installed all return an informative message instead of
raising, so a blocked domain never kills a run (egress allowlist on the server WILL block many
domains — see DECISIONS). Results are content-cached by URL.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging

from langchain_core.tools import tool

from ..cache.store import default_cache

logger = logging.getLogger(__name__)

# Cap returned content so a single huge page can't blow up the agent's context.
# (Query-aware chunking + cross-encoder rerank is M2; this is the M1 guardrail.)
_MAX_CHARS = 16000
_PAGE_TIMEOUT_MS = 30000


def _run_async(coro):
    """Run a coroutine whether or not we're already inside an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already in a loop (e.g. async agent run) → execute in a worker thread with its own loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


async def _fetch(url: str) -> tuple[str, str]:
    """Return (content_markdown, title). Empty content on any failure."""
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    except Exception as e:  # crawl4ai not installed (e.g. M0/M1-lean image)
        logger.warning("crawl4ai unavailable (%s); cannot fetch %s", e, url)
        return "", ""

    try:
        md_gen = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.45, threshold_type="dynamic")
        )
        run_cfg = CrawlerRunConfig(markdown_generator=md_gen, page_timeout=_PAGE_TIMEOUT_MS)
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=run_cfg)

        if not getattr(result, "success", False):
            logger.info("fetch_url non-success for %s: %s", url, getattr(result, "error_message", ""))
            return "", ""

        md = getattr(result, "markdown", None)
        content = ""
        if md is not None:
            content = getattr(md, "fit_markdown", None) or getattr(md, "raw_markdown", "") or str(md)
        meta = getattr(result, "metadata", None) or {}
        title = meta.get("title", "") if isinstance(meta, dict) else ""
        return content, title
    except Exception as e:  # paywall / 403 / timeout / TLS reset on a blocked domain
        logger.warning("fetch_url failed for %s: %s", url, e)
        return "", ""


@tool(parse_docstring=True)
def fetch_url(url: str) -> str:
    """Fetch a web page and return its main content as clean markdown.

    Use after web_search to read a promising result in full. Returns the extracted article/page
    text (boilerplate stripped). On a blocked, paywalled, or unreachable URL it returns a short
    note instead of content — move on to another source rather than retrying the same URL.

    Args:
        url: The full URL to fetch (http/https).
    """
    cached = default_cache.get(url)
    if cached is not None:
        content, title = cached.get("content", ""), cached.get("title", "")
    else:
        content, title = _run_async(_fetch(url))
        if content:
            default_cache.set(url, content, title)

    if not content:
        return f"[fetch_url: could not retrieve {url} (blocked / paywalled / unreachable). Try another source.]"

    truncated = len(content) > _MAX_CHARS
    body = content[:_MAX_CHARS]
    header = f"# {title}\nSource: {url}\n\n" if title else f"Source: {url}\n\n"
    suffix = "\n\n[...truncated...]" if truncated else ""
    return header + body + suffix
