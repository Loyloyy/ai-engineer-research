"""Structured-artifact extraction — a schema-constrained pass over report.md → DeepResearchArtifact.

Runs after the research loop: the model re-reads the finished report + the list of ACTUALLY-FETCHED
sources and emits the structured fields (findings / tech_stack / reference_repos / ...). Uses the
in-process role→model factory (build_chat_model), no proxy. Structured output via LangChain
`with_structured_output` (pydantic-validated); citation validation then drops any evidence_id that
doesn't resolve to a real Source. Never fails the run — on extraction error it returns a content-light
artifact so the report is still preserved (extraction hardening is M3).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .schema import (
    Architecture,
    DeepResearchArtifact,
    Finding,
    ImplementationStep,
    ReferenceRepo,
    Source,
    TechStackItem,
)
from .validate import validate_citations

logger = logging.getLogger(__name__)


class _Extraction(BaseModel):
    """Only the fields the model extracts; lineage/request fields are filled programmatically."""

    findings: list[Finding] = Field(default_factory=list)
    recommended_architectures: list[Architecture] = Field(default_factory=list)
    tech_stack: list[TechStackItem] = Field(default_factory=list)
    reference_repos: list[ReferenceRepo] = Field(default_factory=list)
    implementation_steps: list[ImplementationStep] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


_SYSTEM = """You extract a structured research artifact from a FINISHED research report. Rules:
- Use ONLY information supported by the report and the listed sources. Add no outside knowledge.
- Every finding.evidence_ids entry MUST be an id from the provided SOURCES list. Never invent ids.
- Keep each finding atomic and specific; confidence in [0,1].
- If a section has no support, return an empty list. Do not fabricate repos, licenses, architectures, or steps."""


def sources_from_urls(urls: list[str]) -> list[Source]:
    """Build the Source list (stable src-NNN ids) from the URLs actually fetched during the run."""
    seen: set[str] = set()
    out: list[Source] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(Source(id=f"src-{len(out) + 1:03d}", url=u, origin="web"))
    return out


def _sources_block(sources: list[Source]) -> str:
    if not sources:
        return "(none)"
    return "\n".join(f"- {s.id} | {s.url}" + (f" | {s.title}" if s.title else "") for s in sources)


def _user_prompt(topic: str, brief: str, report_md: str, sources: list[Source]) -> str:
    return (
        f"TOPIC:\n{topic}\n\n"
        f"BRIEF:\n{brief or '(none)'}\n\n"
        f"SOURCES (use these ids for evidence_ids):\n{_sources_block(sources)}\n\n"
        f"REPORT:\n{report_md}"
    )


def extract_artifact(
    *,
    topic: str,
    brief: str,
    report_md: str,
    sources: list[Source],
    artifact_id: str,
    version: int = 1,
    parent_id: str | None = None,
    seed_pages: list[str] | None = None,
    model: str = "smart",  # ROLE name -> build_chat_model(role)
    model_versions: dict | None = None,
) -> DeepResearchArtifact:
    ext = _Extraction()
    if report_md.strip():
        structured = None
        try:
            from ..models import build_chat_model  # lazy: keep the artifact package import-light

            structured = build_chat_model(model, temperature=0.1).with_structured_output(_Extraction)
        except Exception as e:  # noqa: BLE001 — model unavailable → keep the report, skip extraction
            logger.warning("extraction model unavailable (%s); returning content-light artifact", e)

        if structured is not None:
            msgs = [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _user_prompt(topic, brief, report_md, sources)},
            ]
            for attempt in (1, 2):  # one stricter retry before giving up
                try:
                    ext = structured.invoke(msgs)
                    break
                except Exception as e:  # noqa: BLE001
                    logger.warning("artifact extraction attempt %d failed: %s", attempt, e)
                    if attempt == 1:
                        msgs.append({
                            "role": "user",
                            "content": "Return STRICT JSON matching the schema exactly. Use an empty list for any field with no support; do not invent data.",
                        })
                    else:
                        ext = _Extraction()  # content-light fallback

    artifact = DeepResearchArtifact(
        id=artifact_id,
        version=version,
        parent_id=parent_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_versions=model_versions or {},
        topic=topic,
        brief=brief,
        seed_pages=seed_pages or [],
        sources=sources,
        report_markdown=report_md,
        findings=ext.findings,
        recommended_architectures=ext.recommended_architectures,
        tech_stack=ext.tech_stack,
        reference_repos=ext.reference_repos,
        implementation_steps=ext.implementation_steps,
        open_questions=ext.open_questions,
    )
    # Drop hallucinated citations (evidence_ids that don't resolve to a real source).
    return validate_citations(artifact)
