"""Headless entrypoint — the stable Stage-1→2→3 contract.

    run_research(topic, brief="", *, seed_pages=None, parent_id=None, config=None, interactive=False)
        -> (report_markdown, DeepResearchArtifact)

Signature locked with the planning chat (DECISIONS: "M1 research-loop design", decision E). Wires the
M1 lean loop: assemble brief (caller brief + Stage-1 wiki seed) → run the agentic loop (agent.run_gather)
→ build the Source list from what was ACTUALLY fetched (the run ledger) → schema-constrained extraction
→ save versioned artifact. Supports refinement lineage via parent_id.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .agent import run_gather
from .artifact import (
    DeepResearchArtifact,
    extract_artifact,
    new_artifact_id,
    sources_from_urls,
)
from .artifact import load as load_artifact
from .artifact import save as save_artifact
from .config import RunConfig, load_config
from .runlog import current_ledger
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

    # Refinement lineage: a parent_id resumes an existing artifact, bumps the version, and feeds prior
    # findings into the brief so the run deepens/extends rather than restarts.
    parent = load_artifact(parent_id) if parent_id else None
    if parent is not None:
        artifact_id, version = parent.id, parent.version + 1
        lineage_parent = f"{parent.id}@v{parent.version}"
        prior = "\n".join(f"- {f.claim}" for f in parent.findings[:20])
        if prior:
            full_brief = (
                full_brief + "\n\nBuild on these prior findings; deepen/extend, do NOT repeat:\n" + prior
            ).strip()
    else:
        artifact_id, version, lineage_parent = new_artifact_id(), 1, None

    # Run the agentic loop (writes report.md / scope.md / reflection.md / coverage.json into the run dir).
    report_md, run_dir, _ = run_gather(topic, full_brief, config=cfg, run_id=artifact_id, interactive=interactive)

    # Ground the artifact in what was actually fetched (verifiable sources) + per-run coverage telemetry.
    ledger = current_ledger()
    sources = sources_from_urls(ledger.fetched_urls())
    model_versions = {
        "roles": {"lead": cfg.lead_role, "extract": cfg.artifact.model},
        "coverage": ledger.manifest(),  # scaffold: grounding boundary travels with the artifact
    }

    if cfg.artifact.enabled:
        artifact = extract_artifact(
            topic=topic,
            brief=full_brief,
            report_md=report_md,
            sources=sources,
            artifact_id=artifact_id,
            version=version,
            parent_id=lineage_parent,
            seed_pages=seed_pages or [],
            model=cfg.artifact.model,
            model_versions=model_versions,
        )
    else:
        artifact = DeepResearchArtifact(
            id=artifact_id,
            version=version,
            parent_id=lineage_parent,
            generated_at=datetime.now(timezone.utc).isoformat(),
            model_versions=model_versions,
            topic=topic,
            brief=full_brief,
            seed_pages=seed_pages or [],
            sources=sources,
            report_markdown=report_md,
        )

    save_artifact(artifact, root=run_dir.parent)  # artifacts/<id>/vNN.json, alongside report.md
    return report_md, artifact


def _assemble_brief(topic: str, brief: str, seed_pages: list[str] | None) -> str:
    """Combine the caller-supplied brief with the Stage-1 wiki seed (if any)."""
    parts = [brief.strip()] if brief.strip() else []
    if seed_pages:
        seed_text, _ = seed_brief(seed_pages, topic=topic)
        if seed_text:
            parts.append(seed_text)
    return "\n\n".join(parts).strip()
