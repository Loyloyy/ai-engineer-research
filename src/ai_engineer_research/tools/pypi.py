"""PyPI structured-API tool (pypi.org is reachable). Python package maturity + provenance.

PyPI has no usable search API (XML-RPC search is deprecated), so this is a LOOKUP: discovery happens
via GitHub/web search, then pypi_package pulls version/license/activity/links. Graceful-degrade.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_UA = "ai-engineer-research/0.1"


@tool(parse_docstring=True)
def pypi_package(name: str) -> str:
    """Look up a PyPI package: version, license, Python support, project links, release count.

    Use for the production-readiness/maturity assessment of a Python library (after finding its name
    via GitHub or web search).

    Args:
        name: the PyPI distribution name, e.g. "langchain" or "deepagents".
    """
    import httpx

    name = name.strip().strip("/")
    try:
        with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True) as c:
            r = c.get(f"https://pypi.org/pypi/{name}/json")
            if r.status_code == 404:
                return f"[pypi_package: '{name}' not found on PyPI]"
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("pypi lookup failed for %s: %s", name, e)
        return f"[pypi_package error for {name}: {type(e).__name__}: {e}]"

    info = data.get("info", {})
    releases = data.get("releases", {})
    lic = info.get("license_expression") or (info.get("license") or "?")
    if isinstance(lic, str) and len(lic) > 60:
        lic = lic[:60] + "…"
    urls = info.get("project_urls") or {}
    links = "  ".join(f"{k}={v}" for k, v in urls.items() if k in ("Homepage", "Repository", "Source", "Documentation", "Issues", "Changelog"))
    # Latest upload time from the current version's files.
    latest_files = releases.get(info.get("version"), [])
    last_upload = (latest_files[0].get("upload_time_iso_8601", "")[:10] if latest_files else "")
    return (
        f"{info.get('name')} {info.get('version')} — {(info.get('summary') or '').strip()[:160]}\n"
        f"license={lic} requires_python={info.get('requires_python') or '?'} "
        f"releases={len(releases)} latest_release={last_upload or '?'}\n"
        f"{links}\n"
        f"https://pypi.org/project/{info.get('name')}/"
    )


PYPI_TOOLS = [pypi_package]
