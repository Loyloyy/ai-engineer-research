"""Headless entrypoint — the stable Stage-1→2→3 contract.

    run_research(topic, brief="", *, seed_pages=None, parent_id=None, config=None, interactive=False)
        -> (report_markdown, DeepResearchArtifact)

Signature locked with the planning chat (DECISIONS: "M1 research-loop design", decision E). Optionals
are keyword-only to prevent call-site mix-ups (CLI / UI / automated trigger). The agentic loop itself
(scope → plan → gather → reflect → write) lands in M1; this module owns the contract + seed assembly.
"""
from __future__ import annotations

from .artifact import DeepResearchArtifact
from .config import RunConfig, load_config
from .seed import seed_brief


def run_research(
    topic: str,
    brief: str = "",
    *,
    seed_pages: list[str] | None = None,
    parent_id: str | None = None,
    config: RunConfig | None = None,
    interactive: bool = False,
) -> tuple[str, DeepResearchArtifact]:
    cfg = config or load_config()
    full_brief = _assemble_brief(topic, brief, seed_pages)

    # --- M1: the agentic lead loop is wired here (after M0 confirms tool-calling). ---
    # Build the lead ChatModel via build_chat_model(cfg.lead_role), create_deep_agent(...) with the
    # search/scrape tools + a composite filesystem backend (read-only wiki + writable artifacts/<id>/),
    # run scope → plan → gather → reflect → write, then extract_artifact over report.md.
    raise NotImplementedError(
        "run_research agentic loop lands in M1 (gated on M0 tool-call validation). "
        "Seed assembly + the artifact contract are in place. "
        f"[topic={topic!r} seed_pages={seed_pages or []} interactive={interactive} "
        f"lead_role={cfg.lead_role} brief_chars={len(full_brief)}]"
    )


def _assemble_brief(topic: str, brief: str, seed_pages: list[str] | None) -> str:
    """Combine the caller-supplied brief with the Stage-1 wiki seed (if any)."""
    parts = [brief.strip()] if brief.strip() else []
    if seed_pages:
        seed_text, _ = seed_brief(seed_pages, topic=topic)
        if seed_text:
            parts.append(seed_text)
    return "\n\n".join(parts).strip()
