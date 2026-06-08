"""Preferred-source-domain policy — drives search annotation + fetch fast-skip.

A curated set of high-value, reliably-reachable source domains for a code/AI researcher. Env-overridable
so the set expands with ZERO code change: set AER_REACHABLE_DOMAINS to a comma-separated suffix list.

A host is "reachable" if it equals, or is a subdomain of, any entry. Anything else is treated as
low-priority/unreachable (fetch_url fast-skips it; web_search marks it). This is a heuristic for a
restricted-network deploy environment where much of the public web is unreachable — false negatives are
rare and recorded in the miss-log for review. Candidate domains (not yet confirmed reachable) are
PRE-INCLUDED here (harmless if unreachable: the fetch just fails + logs, and starts working the moment
the source becomes reachable).
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

# Preferred, reliably-reachable sources + candidates. Lowercase, no scheme.
_DEFAULT_REACHABLE: tuple[str, ...] = (
    # --- confirmed reachable, high-value ---
    "github.com", "raw.githubusercontent.com", "api.github.com", "codeload.github.com",
    "objects.githubusercontent.com", "user-images.githubusercontent.com",
    "github.io", "huggingface.co", "hf.co", "discuss.huggingface.co",
    "pypi.org", "files.pythonhosted.org",
    "hub.docker.com", "registry-1.docker.io", "ghcr.io", "quay.io",
    "catalog.ngc.nvidia.com", "developer.nvidia.com",
    "docs.python.org", "kubernetes.io", "docs.docker.com",
    "google.com", "bing.com",
    # --- candidates (try anyway; fails+logs until reachable) ---
    "context7.com", "mcp.context7.com", "arxiv.org", "export.arxiv.org", "readthedocs.io",
    "wikipedia.org", "wikimedia.org", "hn.algolia.com",
    "stackoverflow.com", "stackexchange.com", "medium.com", "substack.com",
)


def reachable_domains() -> tuple[str, ...]:
    env = os.environ.get("AER_REACHABLE_DOMAINS", "").strip()
    if env:
        return tuple(d.strip().lower().lstrip(".") for d in env.split(",") if d.strip())
    return _DEFAULT_REACHABLE


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def is_reachable(url: str) -> bool:
    """True if the URL's host is in the preferred-source set (exact or subdomain match)."""
    host = host_of(url)
    if not host:
        return False
    for d in reachable_domains():
        if host == d or host.endswith("." + d):
            return True
    return False
