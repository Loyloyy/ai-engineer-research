"""Optional prompt overrides — drop `config/prompts/<name>.md` to replace a default prompt body.

Defaults live in code (`agent.py` lead prompts, `subagents.py` subagent bodies) so the app works with NO
overrides. An override file replaces just the BODY (persona + method) of that prompt; the code still
appends the non-negotiable parts — grounding rules, required file outputs (`report.md`, `notes/*.md`,
`code/**`), and the injected knobs (thoroughness, fan-out budget, code-count) — so an override can't
silently break a run. Relocate the override dir with `AER_PROMPTS_DIR` (default `config/prompts/`).

Override file names (all optional): lead_lean · lead_multi · code-scout · landscape · maturity ·
focused-investigator · clarify.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .config import ROOT

logger = logging.getLogger(__name__)

PROMPT_NAMES = (
    "lead_lean", "lead_multi", "code-scout", "landscape", "maturity", "focused-investigator", "clarify",
)


def prompts_dir() -> Path:
    """Directory scanned for override files (AER_PROMPTS_DIR, else config/prompts/)."""
    return Path(os.environ.get("AER_PROMPTS_DIR", "").strip() or (ROOT / "config" / "prompts"))


def load_prompt(name: str, default: str) -> str:
    """Return the override body for `name` (config/prompts/<name>.md) if present + non-empty, else `default`."""
    p = prompts_dir() / f"{name}.md"
    try:
        if p.is_file():
            txt = p.read_text(encoding="utf-8").strip()
            if txt:
                logger.info("prompt override: using %s for %r", p, name)
                return txt
            logger.warning("prompt override %s is empty; using the built-in default", p)
    except OSError as e:
        logger.warning("could not read prompt override %s (%s); using the built-in default", p, e)
    return default
