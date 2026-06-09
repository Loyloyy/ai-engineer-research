"""Pre-research clarifying questions — a small, reusable scoping step.

`clarify_questions` only GENERATES the questions (one LLM call); collecting answers is the caller's
job (the CLI prompts on a TTY; a future UI renders a form). `fold_answers` merges answered Q&A back
into the brief. Keeping generation here — not in the CLI — means a UI reuses the exact same logic, and
the headless `run_research` contract stays untouched (it just receives an enriched brief).
"""
from __future__ import annotations

import logging
import re

from .config import RunConfig, load_config
from .models import build_chat_model
from .prompts import load_prompt

logger = logging.getLogger(__name__)

# Default clarify prompt BODY. Overridable via config/prompts/clarify.md (load_prompt) so the UI can tune
# it like the lead/subagent prompts. The `{n}` placeholder (max question count) is the one code-kept
# contract — `clarify_appended_note()` documents it for the read-only editor panel.
_DEFAULT_CLARIFY_PROMPT = (
    "You are scoping a technical research task before it begins. The END OBJECTIVE IS FIXED: this research "
    "feeds a Stage-3 PoC builder, so the deliverable is always BUILD-READY material (recommended "
    "architecture, tech stack, reference repos to template from, implementation steps). Do NOT ask what "
    "the overall goal/objective is — that is given. Instead ask the {n} MOST useful questions that pin "
    "down the SPECIFIC PoC: target environment / stack constraints, must-have capabilities, scale or "
    "performance needs, which alternatives matter, and any hard constraints (license, on-prem, budget). "
    "Do NOT ask anything the brief already answers. Output ONLY the questions, one per line, no numbering "
    "or preamble. If nothing genuinely needs clarifying, output nothing."
)


def clarify_appended_note() -> str:
    """The code-kept rule for the clarify prompt (shown read-only in the UI editor)."""
    return (
        "CODE-KEPT: the `{n}` placeholder is substituted with the max question count; the topic + brief "
        "are appended after this prompt, and the output is parsed one-question-per-line."
    )


def clarify_questions(
    topic: str,
    brief: str = "",
    cfg: RunConfig | None = None,
    *,
    max_questions: int = 3,
) -> list[str]:
    """Generate up to `max_questions` clarifying questions for a research topic.

    Returns [] on empty/failure — clarification is best-effort and must NEVER block a run. Reusable by
    the CLI and a future UI; does not collect answers (that's the caller's I/O concern).
    """
    cfg = cfg or load_config()
    try:
        model = build_chat_model(cfg.lead_role)
        template = load_prompt("clarify", _DEFAULT_CLARIFY_PROMPT)  # config/prompts/clarify.md override
        try:
            head = template.format(n=max_questions)
        except (KeyError, IndexError, ValueError):
            # A custom body may have dropped/broken the {n} placeholder — degrade gracefully.
            head = template + f"\n\nAsk at most {max_questions} questions."
        msg = (
            head
            + f"\n\nTopic: {topic}\n"
            + (f"Brief:\n{brief.strip()}\n" if brief.strip() else "Brief: (none)\n")
        )
        resp = model.invoke(msg)
        text = getattr(resp, "content", resp)
        if isinstance(text, list):  # some providers return content as a list of parts
            text = " ".join(str(p) for p in text)
    except Exception as e:  # noqa: BLE001 — best-effort; degrade to "no questions" rather than crash
        logger.warning("clarify_questions failed (%s: %s); skipping", type(e).__name__, e)
        return []

    questions: list[str] = []
    for line in str(text).splitlines():
        q = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line.strip())  # strip any bullets/numbering
        if q and "?" in q:
            questions.append(q)
    return questions[:max_questions]


def fold_answers(brief: str, qa: list[tuple[str, str]]) -> str:
    """Append answered clarifying Q&A to the brief (blank answers skipped). Returns the enriched brief."""
    answered = [(q, a.strip()) for q, a in qa if a and a.strip()]
    if not answered:
        return brief
    block = "\n".join(f"- Q: {q}\n  A: {a}" for q, a in answered)
    addition = "Clarifications (from the requester):\n" + block
    return (brief.strip() + "\n\n" + addition) if brief.strip() else addition
