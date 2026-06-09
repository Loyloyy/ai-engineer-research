"""GitHub structured-API tools — the M2 code-scout substrate (api.github.com is reachable).

Uses the REST API directly (httpx) — cleaner + more attributable than scraping HTML. An optional
GITHUB_TOKEN (gitignored .env) lifts rate limits (60 → 5000 req/hr) and enables code search; without
it the metadata/readme/issue tools still work at low rate and code search degrades to a note. Same
graceful-degradation contract as the web tools: a failure returns an informative string, never raises.
"""
from __future__ import annotations

import base64
import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_API = "https://api.github.com"
_TIMEOUT = 20
_MAX_CHARS = 16000


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "ai-engineer-research/0.1",
         "X-GitHub-Api-Version": "2022-11-28"}
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(path: str, params: dict | None = None):
    """GET api.github.com{path} -> (json, error_str). json is None on failure."""
    import httpx

    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_headers(), follow_redirects=True) as c:
            r = c.get(f"{_API}{path}", params=params or {})
        if r.status_code in (403, 429) and "rate limit" in r.text.lower():
            return None, "GitHub rate-limited — set GITHUB_TOKEN in .env for 5000 req/hr."
        r.raise_for_status()
        return r.json(), ""
    except Exception as e:  # noqa: BLE001 — degrade gracefully
        logger.warning("github API %s failed: %s", path, e)
        return None, f"{type(e).__name__}: {e}"


def _split_repo(repo: str) -> tuple[str, str] | None:
    parts = repo.strip().strip("/").split("/")
    return (parts[0], parts[1]) if len(parts) == 2 else None


def _record_repo_evidence(data: dict) -> None:
    """Capture a GitHub repo JSON's maturity signals into the run evidence store (best-effort).

    Keeps the structured facts the prose return value would otherwise discard, so `core._finalize` can
    enrich ReferenceRepo deterministically. Must NEVER break the tool (same no-raise contract).
    """
    try:
        from ..evidence import canonical_repo, record_evidence

        cid = canonical_repo(data.get("full_name") or data.get("html_url"))
        if not cid:
            return
        record_evidence(
            "github",
            cid,
            data.get("html_url") or "",
            {
                "stars": data.get("stargazers_count"),
                "forks": data.get("forks_count"),
                "open_issues": data.get("open_issues_count"),
                "archived": data.get("archived"),
                "pushed_at": data.get("pushed_at"),
                "license": (data.get("license") or {}).get("spdx_id"),
                "created": data.get("created_at"),
            },
        )
    except Exception as e:  # noqa: BLE001 — evidence capture is best-effort
        logger.debug("evidence capture skipped: %s", e)


@tool(parse_docstring=True)
def github_search_repos(query: str, max_results: int = 5) -> str:
    """Search GitHub repositories (by keyword/topic) ranked by stars. Use to DISCOVER implementations.

    Returns full_name, stars, language, license, last-push, description, and URL for each hit.

    Args:
        query: keywords/qualifiers, e.g. "deep agents langchain" or "vector database topic:rag".
        max_results: how many repos to return (1-10).
    """
    max_results = max(1, min(int(max_results), 10))
    data, err = _get("/search/repositories", {"q": query, "sort": "stars", "order": "desc", "per_page": max_results})
    if data is None:
        return f"[github_search_repos error: {err}]"
    items = data.get("items", [])[:max_results]
    if not items:
        return f"[github_search_repos: no repos for {query!r}]"
    lines = [f"GitHub repositories for {query!r} (by stars):"]
    for it in items:
        _record_repo_evidence(it)  # search returns full repo objects → capture signals
        lic = (it.get("license") or {}).get("spdx_id") or "?"
        lines.append(
            f"- {it.get('full_name')}  ★{it.get('stargazers_count')}  {it.get('language') or '?'}  "
            f"license={lic}  pushed={(it.get('pushed_at') or '')[:10]}\n"
            f"  {(it.get('description') or '').strip()[:200]}\n  {it.get('html_url')}"
        )
    return "\n".join(lines)


@tool(parse_docstring=True)
def github_repo(repo: str) -> str:
    """Fetch a repo's metadata — maturity/adoption signals (stars, license, activity, archived).

    Args:
        repo: "owner/name", e.g. "langchain-ai/deepagents".
    """
    if not _split_repo(repo):
        return "[github_repo: pass repo as 'owner/name']"
    data, err = _get(f"/repos/{repo.strip().strip('/')}")
    if data is None:
        return f"[github_repo error for {repo}: {err}]"
    _record_repo_evidence(data)  # capture structured maturity signals for deterministic enrichment
    lic = (data.get("license") or {}).get("spdx_id") or "?"
    return (
        f"{data.get('full_name')} — {(data.get('description') or '').strip()}\n"
        f"stars={data.get('stargazers_count')} forks={data.get('forks_count')} "
        f"open_issues={data.get('open_issues_count')} license={lic} archived={data.get('archived')}\n"
        f"language={data.get('language')} topics={', '.join(data.get('topics') or [])}\n"
        f"created={(data.get('created_at') or '')[:10]} last_push={(data.get('pushed_at') or '')[:10]} "
        f"homepage={data.get('homepage') or ''}\n{data.get('html_url')}"
    )


@tool(parse_docstring=True)
def github_readme(repo: str) -> str:
    """Fetch a repo's README as markdown (the primary doc for most projects).

    Args:
        repo: "owner/name".
    """
    if not _split_repo(repo):
        return "[github_readme: pass repo as 'owner/name']"
    data, err = _get(f"/repos/{repo.strip().strip('/')}/readme")
    if data is None:
        return f"[github_readme error for {repo}: {err}]"
    try:
        content = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        content = ""
    if not content:
        return f"[github_readme: no README content for {repo}]"
    truncated = len(content) > _MAX_CHARS
    return f"README for {repo} ({data.get('html_url','')}):\n\n" + content[:_MAX_CHARS] + ("\n\n[...truncated...]" if truncated else "")


@tool(parse_docstring=True)
def github_search_issues(repo: str, query: str = "", max_results: int = 8) -> str:
    """Search a repo's issues — surfaces limitations, bugs, and gotchas for the maturity assessment.

    Args:
        repo: "owner/name" to scope the search.
        query: extra terms, e.g. "production bug" or "limitation memory leak". Empty = recent issues.
        max_results: how many issues to return (1-15).
    """
    if not _split_repo(repo):
        return "[github_search_issues: pass repo as 'owner/name']"
    max_results = max(1, min(int(max_results), 15))
    q = f"repo:{repo.strip().strip('/')} is:issue {query}".strip()
    data, err = _get("/search/issues", {"q": q, "sort": "reactions", "order": "desc", "per_page": max_results})
    if data is None:
        return f"[github_search_issues error for {repo}: {err}]"
    items = data.get("items", [])[:max_results]
    if not items:
        return f"[github_search_issues: no issues for {q!r}]"
    lines = [f"Issues in {repo} matching {query or '(recent)'!r}:"]
    for it in items:
        lines.append(
            f"- #{it.get('number')} [{it.get('state')}] {(it.get('title') or '').strip()[:140]} "
            f"(👍{(it.get('reactions') or {}).get('+1', 0)})\n  {it.get('html_url')}"
        )
    return "\n".join(lines)


GITHUB_TOOLS = [github_search_repos, github_repo, github_readme, github_search_issues]
