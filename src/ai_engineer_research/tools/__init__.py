"""LangChain tools for the researcher. Search and extraction are intentionally decoupled."""
from .github import GITHUB_TOOLS, github_readme, github_repo, github_search_issues, github_search_repos
from .hf import HF_TOOLS, hf_model_card, hf_search_datasets, hf_search_models
from .pypi import PYPI_TOOLS, pypi_package
from .scrape import fetch_url
from .search import web_search

# The lean toolset handed to the M1 lead agent (intelligence in the loop, not the tool count).
WEB_TOOLS = [web_search, fetch_url]

# M2 structured-API tools (code-scout / maturity substrate). Wired into subagents in M2, not the
# lean M1 lead. STRUCTURED_TOOLS is the full set; subagents get tailored subsets.
STRUCTURED_TOOLS = [*GITHUB_TOOLS, *HF_TOOLS, *PYPI_TOOLS]

__all__ = [
    "web_search",
    "fetch_url",
    "WEB_TOOLS",
    "github_search_repos",
    "github_repo",
    "github_readme",
    "github_search_issues",
    "GITHUB_TOOLS",
    "hf_search_models",
    "hf_model_card",
    "hf_search_datasets",
    "HF_TOOLS",
    "pypi_package",
    "PYPI_TOOLS",
    "STRUCTURED_TOOLS",
]
