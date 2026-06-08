"""Headless entrypoint — the stable Stage-1→2→3 contract.

    run_research(topic, brief="", *, seed_pages=None, parent_id=None, config=None, interactive=False)
        -> (report_markdown, DeepResearchArtifact)

Signature locked with the planning chat (DECISIONS: "M1 research-loop design", decision E). Wires the
M1 lean loop: assemble brief (caller brief + Stage-1 wiki seed) → run the agentic loop (agent.run_gather)
→ build the Source list from what was ACTUALLY fetched (the run ledger) → schema-constrained extraction
→ save versioned artifact. Supports refinement lineage via parent_id.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .agent import ARTIFACTS_ROOT, run_gather
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
from .tracing import build_tracer, flush_tracer


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

    return _finalize(
        cfg, topic, full_brief, report_md, run_dir,
        artifact_id=artifact_id, version=version, lineage_parent=lineage_parent, seed_pages=seed_pages or [],
    )


def resume_research(
    run_id: str,
    *,
    config: RunConfig | None = None,
) -> tuple[str, DeepResearchArtifact]:
    """Resume a prior TRUNCATED run from its checkpoint and finalize the artifact.

    Topic/brief/lineage are recovered via `_recover_run_inputs` (partial artifact, or run_meta.json on a
    hard kill). The completed artifact OVERWRITES that same version (this finishes the run, it is not a
    new refinement). Returns the same contract tuple.
    """
    cfg = config or load_config()
    topic, brief, version, lineage_parent, seed_pages = _recover_run_inputs(run_id)
    # Honor the ORIGINAL topology — resuming a multi-agent run with the lean agent (or vice-versa) would
    # mismatch the checkpointed graph. None (old run_meta without the field) → fall back to cfg.
    multi_agent = _meta_field(run_id, "multi_agent")
    report_md, run_dir, _ = run_gather(
        topic, brief, config=cfg, run_id=run_id, resume=True, multi_agent=multi_agent
    )
    return _finalize(
        cfg, topic, brief, report_md, run_dir,
        artifact_id=run_id, version=version, lineage_parent=lineage_parent, seed_pages=seed_pages,
    )


def _meta_field(run_id: str, key: str):
    """Read one field from a run's run_meta.json, or None if absent/unreadable."""
    try:
        return json.loads((ARTIFACTS_ROOT / run_id / "run_meta.json").read_text()).get(key)
    except (OSError, ValueError):
        return None


def _recover_run_inputs(run_id: str) -> tuple[str, str, int, str | None, list[str]]:
    """Recover (topic, brief, version, parent_id, seed_pages) for a resume.

    Prefer the partial artifact (carries lineage/version — present after a caught-exception truncation).
    Fall back to `run_meta.json` (written before the first LLM call → survives a hard kill / docker stop).
    """
    try:
        p = load_artifact(run_id)
        return p.topic, p.brief, p.version, p.parent_id, p.seed_pages
    except FileNotFoundError:
        pass
    try:
        meta = json.loads((ARTIFACTS_ROOT / run_id / "run_meta.json").read_text())
    except (OSError, ValueError) as e:
        raise FileNotFoundError(
            f"cannot resume {run_id}: no saved artifact and no readable run_meta.json ({e})"
        ) from e
    return meta.get("topic", ""), meta.get("brief", ""), 1, None, []


def _finalize(
    cfg: RunConfig,
    topic: str,
    full_brief: str,
    report_md: str,
    run_dir,
    *,
    artifact_id: str,
    version: int,
    lineage_parent: str | None,
    seed_pages: list[str],
) -> tuple[str, DeepResearchArtifact]:
    """Shared tail for run_research/resume_research: ground sources in the ledger → extract → save."""
    # Ground the artifact in what was actually fetched (verifiable sources) + per-run coverage telemetry.
    ledger = current_ledger()
    sources = sources_from_urls(ledger.fetched_urls())
    model_versions = {
        "roles": {"lead": cfg.lead_role, "extract": cfg.artifact.model},
        "coverage": ledger.manifest(),  # scaffold: grounding boundary travels with the artifact
    }

    if cfg.artifact.enabled:
        # Trace the extraction LLM call into the same run session (no-op when AER_TRACING is off).
        tracer = build_tracer()
        try:
            artifact = extract_artifact(
                topic=topic,
                brief=full_brief,
                report_md=report_md,
                sources=sources,
                artifact_id=artifact_id,
                version=version,
                parent_id=lineage_parent,
                seed_pages=seed_pages,
                model=cfg.artifact.model,
                model_versions=model_versions,
                tracer=tracer,
            )
        finally:
            flush_tracer()
    else:
        artifact = DeepResearchArtifact(
            id=artifact_id,
            version=version,
            parent_id=lineage_parent,
            generated_at=datetime.now(timezone.utc).isoformat(),
            model_versions=model_versions,
            topic=topic,
            brief=full_brief,
            seed_pages=seed_pages,
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
