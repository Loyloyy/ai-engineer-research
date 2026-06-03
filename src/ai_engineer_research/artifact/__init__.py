"""Structured, versioned research artifact (the Stage 2→3 contract) + persistence/validation.

`extract_artifact` (the schema-constrained extraction pass) is model-coupled and lands with the
M1 loop wiring — it imports lazily from `.extract` to keep this package importable without the
model deps. Until then, schema/store/validate are fully usable offline.
"""
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
    "new_artifact_id",
    "validate_citations",
    "save",
    "load",
    "latest_version",
    "list_artifacts",
]
