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
import logging
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
from .evidence import canonical_repo, current_evidence
from .runlog import current_ledger
from .seed import seed_brief
from .tracing import build_tracer, flush_tracer

logger = logging.getLogger(__name__)


def run_research(
    topic: str,
    brief: str = "",
    *,
    seed_pages: list[str] | None = None,
    parent_id: str | None = None,
    config: RunConfig | None = None,
    interactive: bool = False,
    event_callbacks: list | None = None,
    run_id: str | None = None,
    stop_event=None,
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
        # A caller (e.g. the UI) may pre-supply the run_id so it can subscribe to the live stream before
        # this long run returns; otherwise mint a fresh one. parent_id (refinement) still wins above.
        artifact_id, version, lineage_parent = run_id or new_artifact_id(cfg.multi_agent), 1, None

    # Run the agentic loop (writes report.md / scope.md / reflection.md / coverage.json into the run dir).
    report_md, run_dir, _ = run_gather(
        topic, full_brief, config=cfg, run_id=artifact_id, interactive=interactive,
        event_callbacks=event_callbacks, stop_event=stop_event,
    )

    return _finalize(
        cfg, topic, full_brief, report_md, run_dir,
        artifact_id=artifact_id, version=version, lineage_parent=lineage_parent, seed_pages=seed_pages or [],
        event_callbacks=event_callbacks,
    )


def resume_research(
    run_id: str,
    *,
    config: RunConfig | None = None,
    event_callbacks: list | None = None,
    stop_event=None,
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
        topic, brief, config=cfg, run_id=run_id, resume=True, multi_agent=multi_agent,
        event_callbacks=event_callbacks, stop_event=stop_event,
    )
    return _finalize(
        cfg, topic, brief, report_md, run_dir,
        artifact_id=run_id, version=version, lineage_parent=lineage_parent, seed_pages=seed_pages,
        event_callbacks=event_callbacks,
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
    event_callbacks: list | None = None,
) -> tuple[str, DeepResearchArtifact]:
    """Shared tail for run_research/resume_research: ground sources in the ledger → extract → save."""
    # Ground the artifact in what was actually fetched (verifiable sources) + per-run coverage telemetry.
    ledger = current_ledger()
    sources = sources_from_urls(ledger.fetched_urls(), ledger.fetched_at_map())
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
                extra_callbacks=event_callbacks,
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

    # Deterministic provenance enrichment (NOT LLM): copy the captured GitHub signals onto each repo,
    # flag whether we gathered its code, derive a reproducibility tier. Touches only ReferenceRepo
    # metadata — never evidence_ids — so the §6 citation invariant is structurally safe.
    _enrich_reference_repos(artifact, run_dir)
    # Fail loud if enrichment produced something schema-invalid, rather than writing a bad vNN.json.
    artifact = DeepResearchArtifact.model_validate(artifact.model_dump())

    save_artifact(artifact, root=run_dir.parent)  # artifacts/<id>/vNN.json, alongside report.md
    _write_run_index(run_dir, artifact)
    return report_md, artifact


_PERMISSIVE_LICENSES = {"MIT", "APACHE-2.0", "BSD-3-CLAUSE", "BSD-2-CLAUSE", "ISC", "MPL-2.0", "0BSD"}


def _norm_key(s: str) -> str:
    """Fold owner/repo separators so 'Owner-Repo', 'Owner_Repo', 'Owner/Repo' compare equal."""
    return (s or "").lower().replace("_", "-").replace("/", "-").strip("-")


def _gathered_code_keys(run_dir) -> set[str]:
    """Normalized dir keys for repos that actually have files under code/ (tolerant of layout).

    code-scout writes `code/<owner-repo>/...` but the exact dir name is ambiguous (single `owner-repo`
    dir vs nested `owner/repo`), so we index both immediate and one-level-nested non-empty dirs.
    """
    code_root = run_dir / "code"
    keys: set[str] = set()
    if not code_root.is_dir():
        return keys
    for sub in code_root.iterdir():
        if not sub.is_dir():
            continue
        if any(f.is_file() for f in sub.rglob("*")):
            keys.add(_norm_key(sub.name))
        for child in sub.iterdir():  # nested owner/repo layout
            if child.is_dir() and any(f.is_file() for f in child.rglob("*")):
                keys.add(_norm_key(f"{sub.name}/{child.name}"))
    return keys


def _code_gathered(cid: str | None, name: str, keys: set[str]) -> bool:
    """Did this repo produce files under code/? Tolerant match against the gathered-code dir keys."""
    if not keys:
        return False
    cands: set[str] = set()
    repo_token = None
    if cid:
        repo_token = _norm_key(cid.split("/")[-1])
        cands |= {_norm_key(cid), repo_token}
    if name:
        cands |= {_norm_key(name), _norm_key(name.split("/")[-1])}
    cands.discard("")
    if cands & keys:
        return True
    # looser: a dir whose trailing segment is the repo name (e.g. 'langchain-ai-deepagents' vs 'deepagents')
    return bool(repo_token) and any(k == repo_token or k.endswith("-" + repo_token) for k in keys)


def _reproducibility(rec: dict | None) -> str | None:
    """Tier from PURE-JSON signals only (archived/recency/stars/license). None = no evidence match."""
    if not rec:
        return None
    sig = rec.get("signals") or {}
    if sig.get("archived"):
        return "LOW"
    score = 0
    pushed = sig.get("pushed_at")
    if pushed:
        try:
            days = (datetime.now(timezone.utc) - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            if days <= 365:
                score += 1
            if days <= 90:
                score += 1
        except ValueError:
            pass
    if (sig.get("stars") or 0) >= 1000:
        score += 1
    if (sig.get("license") or "").upper() in _PERMISSIVE_LICENSES:
        score += 1
    return "HIGH" if score >= 3 else "MED" if score >= 1 else "LOW"


def _enrich_reference_repos(artifact: DeepResearchArtifact, run_dir) -> None:
    """Copy captured GitHub signals onto each ReferenceRepo + derive code_gathered/reproducibility.

    Deterministic, best-effort: unmatched repos keep their LLM-extracted fields and are logged as a
    coverage signal (a miss is information, not an error). No network calls.
    """
    store = current_evidence()
    code_keys = _gathered_code_keys(run_dir)
    unmatched: list[str] = []
    for repo in artifact.reference_repos:
        cid = canonical_repo(repo.url) or canonical_repo(repo.name)
        rec = store.get(cid) if cid else None
        if rec:
            sig = rec.get("signals") or {}
            if sig.get("stars") is not None:
                repo.stars = sig["stars"]
            if sig.get("pushed_at"):
                repo.last_commit = sig["pushed_at"][:10]
            if sig.get("archived") is not None:
                repo.archived = sig["archived"]
            if sig.get("license") and not repo.license:
                repo.license = sig["license"]
        else:
            unmatched.append(repo.url or repo.name)
        repo.code_gathered = _code_gathered(cid, repo.name, code_keys)
        repo.reproducibility = _reproducibility(rec)
    if unmatched:
        logger.info(
            "reference_repos with no structured evidence match (%d/%d): %s",
            len(unmatched), len(artifact.reference_repos), ", ".join(unmatched[:10]),
        )


def _write_run_index(run_dir, artifact: DeepResearchArtifact) -> None:
    """Write `00_INDEX.md` — a human reading-guide listing the run's files in pipeline order.

    Lists only files/dirs that actually exist (lean runs lack notes/, code/, comparison.md), numbered
    in the order the pipeline produces them, each with a one-line description. The `00_` prefix sorts it
    to the top of `ls`. Best-effort: never fails the run.
    """
    # (name, is_dir, description) in the order the pipeline produces them.
    catalog = [
        ("run_meta.json", False, "run inputs (topic / brief / mode) — written before the first LLM call"),
        ("scope.md", False, "the agent's research question, sub-questions, and success criteria"),
        ("notes", True, "per-subagent working notes (code-scout / landscape / maturity) — multi-agent"),
        ("code", True, "real source files gathered by code-scout, as code/<owner-repo>/<file> — multi-agent"),
        ("reflection.md", False, "gap analysis + verdicts on the seed/brief hypotheses"),
        ("comparison.md", False, "subject-vs-alternatives matrix — multi-agent"),
        ("report.md", False, "the main human-readable cited report — READ THIS FIRST"),
        ("coverage.json", False, "grounding telemetry: fetched vs blocked, elapsed_s, truncated flag"),
        ("ledger.json", False, "fetch-ledger snapshot (survives a cross-process --resume)"),
        (f"v{artifact.version:02d}.json", False, "the structured DeepResearchArtifact (the Stage 2->3 contract)"),
    ]
    lines = [
        f"# Run {artifact.id} — file index",
        "",
        f"_Topic:_ {artifact.topic}",
        "",
        "Files are listed in the order the pipeline produces them. Start with `report.md`.",
        "",
    ]
    n = 0
    for name, is_dir, desc in catalog:
        p = run_dir / name
        if not (p.is_dir() if is_dir else p.exists()):
            continue
        n += 1
        label = f"{name}/" if is_dir else name
        lines.append(f"{n}. **`{label}`** — {desc}")
    try:
        (run_dir / "00_INDEX.md").write_text("\n".join(lines) + "\n")
    except OSError as e:
        logger.warning("could not write 00_INDEX.md: %s", e)


def _assemble_brief(topic: str, brief: str, seed_pages: list[str] | None) -> str:
    """Combine the caller-supplied brief with the Stage-1 wiki seed (if any).

    Leads with today's date so the model grounds "as of" phrasing and dated claims in the report on
    the real run date instead of guessing one (otherwise the report header date is hallucinated).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = [f"Today's date is {today}. Date any time-sensitive claims relative to this."]
    if brief.strip():
        parts.append(brief.strip())
    if seed_pages:
        seed_text, _ = seed_brief(seed_pages, topic=topic)
        if seed_text:
            parts.append(seed_text)
    return "\n\n".join(parts).strip()
