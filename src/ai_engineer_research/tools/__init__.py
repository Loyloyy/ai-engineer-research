"""LangChain tools for the researcher. Search and extraction are intentionally decoupled."""
from .scrape import fetch_url
from .search import web_search

# The default web toolset handed to the lead agent (M1). Subagent-specific tools (GitHub code
# gathering, etc.) are added in M2.
WEB_TOOLS = [web_search, fetch_url]

__all__ = ["web_search", "fetch_url", "WEB_TOOLS"]
