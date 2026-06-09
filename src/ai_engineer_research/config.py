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
    search_url: str = "http://searxng:8080"
    # NOTE: the code_*/max_investigators/thoroughness-depth knobs below are SOFT — injected into agent
    # prompts as targets the model is told to follow, not enforced quotas (see USAGE "Tuning depth &
    # breadth"). Only `clarify` is a hard code switch; thoroughness also sets the recursion budget (agent.py).
    # code-scout gather breadth (multi-agent). Env: AER_CODE_MAX_REPOS / AER_CODE_FILES_PER_REPO.
    code_max_repos: int = 3
    code_files_per_repo: int = 3
    # Multi-agent fan-out + per-subagent depth. Env: AER_MAX_INVESTIGATORS / AER_THOROUGHNESS.
    max_investigators: int = 2
    thoroughness: str = "standard"  # light | standard | deep (prompt-injected gather depth + recursion budget)
    # Pre-research clarifying questions. CLI prompts when on a TTY; a UI can drive the same step. AER_CLARIFY.
    clarify: bool = True
    # Crash-resume (DECISIONS: "Run checkpointing + resume"). LangGraph SqliteSaver-backed.
    checkpoint_enabled: bool = True
    resume_max_retries: int = 2   # auto-resume attempts after the initial run: 1 immediate + 1 backed-off
    resume_backoff_s: int = 45    # delay before the 2nd auto-resume (lets a loaded endpoint recover)
    checkpoint_retention_days: int = 7  # sweep checkpoints of truncated runs older than this at startup
    # Optional Langfuse tracing (self-hosted). Source of truth is env AER_TRACING (read in tracing.py);
    # mirrored here for discoverability alongside the other knobs.
    tracing_enabled: bool = False
    artifact: ArtifactConfig = field(default_factory=ArtifactConfig)


def load_config(path: str | Path | None = None) -> RunConfig:
    load_env()
    p = Path(path) if path else ROOT / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data = data or {}
    r = data.get("research", {}) or {}
    ar = data.get("artifact", {}) or {}
    env_multi = os.environ.get("AER_MULTI_AGENT", "").strip().lower()
    env_ckpt = os.environ.get("AER_CHECKPOINT", "").strip().lower()
    env_trace = os.environ.get("AER_TRACING", "").strip().lower()
    env_clarify = os.environ.get("AER_CLARIFY", "").strip().lower()
    return RunConfig(
        lead_role=os.environ.get("LEAD_ROLE") or r.get("lead_role", "strategic"),
        multi_agent=(env_multi in ("1", "true", "yes")) if env_multi else bool(r.get("multi_agent", False)),
        search_url=os.environ.get("SEARX_URL") or r.get("search_url", "http://searxng:8080"),
        code_max_repos=int(os.environ.get("AER_CODE_MAX_REPOS") or r.get("code_max_repos", 3)),
        code_files_per_repo=int(os.environ.get("AER_CODE_FILES_PER_REPO") or r.get("code_files_per_repo", 3)),
        max_investigators=int(os.environ.get("AER_MAX_INVESTIGATORS") or r.get("max_investigators", 2)),
        thoroughness=(os.environ.get("AER_THOROUGHNESS") or r.get("thoroughness", "standard")).strip().lower(),
        clarify=(env_clarify not in ("0", "false", "no")) if env_clarify else bool(r.get("clarify", True)),
        checkpoint_enabled=(env_ckpt not in ("0", "false", "no")) if env_ckpt else bool(r.get("checkpoint_enabled", True)),
        resume_max_retries=int(os.environ.get("AER_RESUME_MAX_RETRIES") or r.get("resume_max_retries", 2)),
        resume_backoff_s=int(os.environ.get("AER_RESUME_BACKOFF_S") or r.get("resume_backoff_s", 45)),
        checkpoint_retention_days=int(
            os.environ.get("AER_CHECKPOINT_RETENTION_DAYS") or r.get("checkpoint_retention_days", 7)
        ),
        tracing_enabled=(env_trace in ("1", "true", "yes")) if env_trace else bool(r.get("tracing_enabled", False)),
        artifact=ArtifactConfig(
            enabled=bool(ar.get("enabled", True)),
            model=ar.get("model", "smart"),
        ),
    )
