"""Structured, versioned research artifact (the Stage 2→3 contract) + extraction/persistence/validation."""
from .extract import extract_artifact, sources_from_urls
from .schema import (
    Architecture,
    DeepResearchArtifact,
    Finding,
    ImplementationStep,
    ReferenceRepo,
    Source,
    TechStackItem,
)
from .store import latest_version, list_artifacts, load, new_artifact_id, save
from .validate import validate_citations

__all__ = [
    "Source",
    "Finding",
    "TechStackItem",
    "Architecture",
    "ReferenceRepo",
    "ImplementationStep",
    "DeepResearchArtifact",
    "extract_artifact",
    "sources_from_urls",
    "new_artifact_id",
    "validate_citations",
    "save",
    "load",
    "latest_version",
    "list_artifacts",
]
