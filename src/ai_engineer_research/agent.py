"""M1 lead research agent.

Slice 2 (current): ONE agentic lead agent with the web tools + a real-disk filesystem backend
rooted at the run folder. Given topic+brief it searches, fetches, and writes a cited `report.md`
into `artifacts/<run_id>/`. This proves the search→scrape→write loop on the on-prem model.
Scope + reflection discipline (Slice 3) and artifact extraction (Slice 4) layer on top of this;
the full `run_research` contract (core.py) is wired in Slice 5.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .artifact import new_artifact_id
from .cache.store import configure_default_cache
from .config import RunConfig, load_config
from .models import build_chat_model
from .tools import WEB_TOOLS

logger = logging.getLogger(__name__)

ARTIFACTS_ROOT = Path("artifacts")
# LangGraph's default recursion limit (25) is too low for a multi-round research loop.
# (A proper wall-clock / iteration cap lands with Slice 3's scope+reflection discipline.)
_RECURSION_LIMIT = 150

GATHER_SYSTEM_PROMPT = """You are a thorough technical research agent. You investigate a topic by \
searching the web and reading sources in full, then write a detailed, well-sourced report.

Tools:
- web_search(query, max_results): find sources. Issue focused, specific queries; vary wording across \
calls to broaden coverage (official docs, GitHub repos, benchmarks, critiques, comparisons).
- fetch_url(url): read a promising result in full. If it returns a "could not retrieve" note, move on \
to another source — do not retry the same URL.

Method:
1. Search broadly, then read the most relevant sources in full with fetch_url (do not rely on snippets).
2. Corroborate claims across MULTIPLE independent sources. Note disagreements.
3. Be comprehensive and specific — concrete mechanisms, numbers, trade-offs, limitations, alternatives. \
Do NOT pad: every claim earns its place; no filler, no restating the prompt.

When you have enough, write the FINAL report to the file `report.md` using write_file, structured as:
  # <Title>
  <sections with specific, sourced claims; inline-cite by URL>
  ## Sources
  - <url> — <what it supported>
Only include sources you actually read. Do not fabricate URLs, quotes, or numbers. The report file is \
the deliverable — make sure you write it before finishing."""


def _run_dir(run_id: str) -> Path:
    d = ARTIFACTS_ROOT / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def build_research_agent(cfg: RunConfig, run_dir: Path):
    """Create the lead deep agent with the web tools + a real-disk backend rooted at run_dir."""
    try:
        from deepagents.backends.filesystem import FilesystemBackend
    except ImportError:  # tolerate a top-level re-export across beta versions
        from deepagents import FilesystemBackend  # type: ignore
    from deepagents import create_deep_agent

    backend = FilesystemBackend(root_dir=str(run_dir), virtual_mode=True)
    model = build_chat_model(cfg.lead_role)
    return create_deep_agent(
        model=model,
        tools=WEB_TOOLS,
        system_prompt=GATHER_SYSTEM_PROMPT,
        backend=backend,
    )


def _task(topic: str, brief: str) -> str:
    t = f"Research topic: {topic}\n\n"
    if brief.strip():
        t += f"Context / brief:\n{brief.strip()}\n\n"
    t += "Research this thoroughly using your tools, then write the final report to report.md."
    return t


def run_gather(
    topic: str,
    brief: str = "",
    config: RunConfig | None = None,
    run_id: str | None = None,
) -> tuple[str, Path, str]:
    """Slice-2 entrypoint: gather + write report.md. Returns (report_markdown, run_dir, run_id)."""
    cfg = config or load_config()
    configure_default_cache(enabled=True, ttl_hours=24)
    run_id = run_id or new_artifact_id()
    run_dir = _run_dir(run_id)

    agent = build_research_agent(cfg, run_dir)
    logger.info("research run %s starting (lead_role=%s) -> %s", run_id, cfg.lead_role, run_dir)
    agent.invoke(
        {"messages": [{"role": "user", "content": _task(topic, brief)}]},
        config={"recursion_limit": _RECURSION_LIMIT},
    )

    report_path = run_dir / "report.md"
    report_md = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if not report_md:
        logger.warning("run %s finished but produced no report.md in %s", run_id, run_dir)
    return report_md, run_dir, run_id
