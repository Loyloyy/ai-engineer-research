"""Configuration: loads .env (secrets/endpoints) + config/pipeline.yaml (knobs) into a RunConfig.

Kept intentionally small for M0; grows as milestones land (search/scrape/rerank/artifact knobs).
Machine-specific values (model ids, endpoints, private model paths) live in .env, NOT here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# repo root = .../ai-engineer-research (two levels up from this file's package dir)
ROOT = Path(__file__).resolve().parents[2]

_ENV_LOADED = False


def load_env() -> None:
    """Load .env once (idempotent). Safe to call from any entrypoint."""
    global _ENV_LOADED
    if not _ENV_LOADED:
        load_dotenv(ROOT / ".env")
        _ENV_LOADED = True


@dataclass
class ArtifactConfig:
    enabled: bool = True
    model: str = "smart"  # role name -> build_chat_model(role)


@dataclass
class RunConfig:
    # Which role drives the LEAD agent. M0 validates this role's tool-calling.
    lead_role: str = "strategic"
    # M2: multi-agent mode (lead + code-scout/landscape/maturity subagents). False = lean M1 loop.
    multi_agent: bool = False
    max_iterations: int = 3
    wall_clock_timeout_s: int = 1800
    search_url: str = "http://searxng:8080"
    max_search_results_per_query: int = 5
    artifact: ArtifactConfig = field(default_factory=ArtifactConfig)


def load_config(path: str | Path | None = None) -> RunConfig:
    load_env()
    p = Path(path) if path else ROOT / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data = data or {}
    r = data.get("research", {}) or {}
    ar = data.get("artifact", {}) or {}
    env_multi = os.environ.get("AER_MULTI_AGENT", "").strip().lower()
    return RunConfig(
        lead_role=os.environ.get("LEAD_ROLE") or r.get("lead_role", "strategic"),
        multi_agent=(env_multi in ("1", "true", "yes")) if env_multi else bool(r.get("multi_agent", False)),
        max_iterations=int(r.get("max_iterations", 3)),
        wall_clock_timeout_s=int(r.get("wall_clock_timeout_s", 1800)),
        search_url=os.environ.get("SEARX_URL") or r.get("search_url", "http://searxng:8080"),
        max_search_results_per_query=int(r.get("max_search_results_per_query", 5)),
        artifact=ArtifactConfig(
            enabled=bool(ar.get("enabled", True)),
            model=ar.get("model", "smart"),
        ),
    )
