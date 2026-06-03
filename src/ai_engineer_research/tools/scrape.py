"""fetch_url tool — clean full-page extraction, with a selectable backend.

Backend chosen via env `AER_FETCH_BACKEND` (see DECISIONS):
  - "http"    (default-safe): httpx + trafilatura. No browser. Robust on the egress allowlist;
               great for static sources (GitHub, docs, blogs, arxiv abstracts, raw files).
  - "browser" : Crawl4AI + Playwright chromium. Renders JS. Requires the browser binary installed,
               which needs the Playwright download CDN unblocked on the server egress allowlist.
  - "auto"    : use the browser backend if a chromium binary is actually present, else fall back to
               http; and if a browser fetch comes back empty, retry once over http.

Degrades gracefully everywhere: a blocked / paywalled / non-HTML / unreachable URL returns an
informative message instead of raising, so a run never dies on one bad source. Cached by URL.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import tool

from ..cache.store import default_cache

logger = logging.getLogger(__name__)

_BACKEND_ENV = "AER_FETCH_BACKEND"  # auto | http | browser
# Cap returned content so a single huge page can't blow up the agent's context.
# (Query-aware chunking + cross-encoder rerank is M2; this is the M1 guardrail.)
_MAX_CHARS = 16000
_TIMEOUT_S = 25
_PAGE_TIMEOUT_MS = 30000
_UA = "Mozilla/5.0 (compatible; ai-engineer-research/0.1; +research-agent)"
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# --------------------------------------------------------------------------- http backend
def _extract_markdown(html: str, url: str) -> str:
    """trafilatura main-content extraction, tolerant of version differences in kwargs."""
    import trafilatura

    for kwargs in (
        {"output_format": "markdown", "include_links": True, "favor_recall": True},
        {"output_format": "markdown"},
        {},
    ):
        try:
            content = trafilatura.extract(html, url=url, include_comments=False, **kwargs)
        except TypeError:
            continue
        if content:
            return content
    return ""


def _fetch_http(url: str) -> tuple[str, str]:
    """httpx + trafilatura. Returns (content_markdown, title); empty on failure (logged)."""
    import httpx

    try:
        with httpx.Client(timeout=_TIMEOUT_S, follow_redirects=True, headers={"User-Agent": _UA}) as c:
            resp = c.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").lower()
            text = resp.text
    except Exception as e:  # noqa: BLE001 — blocked/paywall/403/timeout/TLS reset on egress
        logger.warning("fetch_url(http) request failed for %s: %s", url, e)
        return "", ""

    is_html = "html" in ctype or "xml" in ctype or not ctype
    if not is_html:
        # Raw text/markdown/json/source files (e.g. raw.githubusercontent.com) are already clean.
        if ctype.startswith("text/") or "markdown" in ctype or "json" in ctype:
            return text, ""
        logger.info("fetch_url(http) skipping non-text (%s) for %s", ctype, url)
        return "", ""

    try:
        content = _extract_markdown(text, url)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_url(http) extraction failed for %s: %s", url, e)
        content = ""
    m = _TITLE_RE.search(text)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return content, title


# --------------------------------------------------------------------------- browser backend
def _run_async(coro):
    """Run a coroutine whether or not we're already inside an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


async def _afetch_browser(url: str) -> tuple[str, str]:
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    except Exception as e:  # crawl4ai not installed
        logger.warning("fetch_url(browser) crawl4ai unavailable (%s) for %s", e, url)
        return "", ""
    try:
        md_gen = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.45, threshold_type="dynamic")
        )
        run_cfg = CrawlerRunConfig(markdown_generator=md_gen, page_timeout=_PAGE_TIMEOUT_MS)
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=run_cfg)
        if not getattr(result, "success", False):
            logger.info("fetch_url(browser) non-success for %s: %s", url, getattr(result, "error_message", ""))
            return "", ""
        md = getattr(result, "markdown", None)
        content = ""
        if md is not None:
            content = getattr(md, "fit_markdown", None) or getattr(md, "raw_markdown", "") or str(md)
        meta = getattr(result, "metadata", None) or {}
        title = meta.get("title", "") if isinstance(meta, dict) else ""
        return content, title
    except Exception as e:  # browser missing / paywall / 403 / timeout / TLS reset
        logger.warning("fetch_url(browser) failed for %s: %s", url, e)
        return "", ""


def _fetch_browser(url: str) -> tuple[str, str]:
    return _run_async(_afetch_browser(url))


@lru_cache(maxsize=1)
def _browser_available() -> bool:
    """True only if crawl4ai imports AND a Playwright chromium binary is actually present."""
    try:
        import crawl4ai  # noqa: F401
    except Exception:
        return False
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.exists() and any(cache.glob("chromium-*/chrome-linux*/chrome"))


def _resolve_backend() -> str:
    choice = os.environ.get(_BACKEND_ENV, "auto").strip().lower()
    if choice in ("http", "browser"):
        return choice
    return "browser" if _browser_available() else "http"  # auto


# --------------------------------------------------------------------------- tool
@tool(parse_docstring=True)
def fetch_url(url: str) -> str:
    """Fetch a web page and return its main content as clean markdown.

    Use after web_search to read a promising result in full. Returns the extracted article/page
    text (navigation and boilerplate stripped). On a blocked, paywalled, non-HTML, or unreachable
    URL it returns a short note instead of content — move on to another source rather than retrying.

    Args:
        url: The full URL to fetch (http/https).
    """
    cached = default_cache.get(url)
    if cached is not None:
        content, title = cached.get("content", ""), cached.get("title", "")
    else:
        backend = _resolve_backend()
        if backend == "browser":
            content, title = _fetch_browser(url)
            # auto-mode safety net: an empty browser result falls back to the http backend.
            if not content and os.environ.get(_BACKEND_ENV, "auto").strip().lower() == "auto":
                content, title = _fetch_http(url)
        else:
            content, title = _fetch_http(url)
        if content:
            default_cache.set(url, content, title)

    if not content:
        return f"[fetch_url: could not retrieve {url} (blocked / paywalled / non-HTML / unreachable). Try another source.]"

    truncated = len(content) > _MAX_CHARS
    body = content[:_MAX_CHARS]
    header = f"# {title}\nSource: {url}\n\n" if title else f"Source: {url}\n\n"
    suffix = "\n\n[...truncated...]" if truncated else ""
    return header + body + suffix
