"""M1 lead research agent — the lean agentic loop.

ONE lead agent with web_search + fetch_url over a real-disk filesystem backend rooted at the run
folder. It runs scope → plan → gather → reflect → quality-stop, grounded in sources it actually
fetched (never backfilled from parametric memory). Cheap discipline (DECISIONS: M1):
domain-aware steering (✓/✗ in search), unreachable-host fast-skip, a per-run miss-log, and a coverage
manifest. The rich structured-API tools + subagents are M2; the intelligence here is the LOOP.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .artifact import new_artifact_id
from .cache.store import configure_default_cache
from .checkpoint import (
    build_checkpointer,
    checkpoint_db_path,
    delete_run,
    is_transient_error,
    sweep_truncated,
)
from .config import RunConfig, load_config
from .models import build_chat_model
from .evidence import configure_evidence, current_evidence, load_evidence, save_evidence
from .runlog import configure_ledger, current_ledger, load_ledger, save_ledger
from .tracing import build_tracer, flush_tracer, trace_metadata
from .prompts import load_prompt
from .subagents import build_subagents, thoroughness_directive
from .tools import STRUCTURED_TOOLS, WEB_TOOLS

logger = logging.getLogger(__name__)

ARTIFACTS_ROOT = Path("artifacts")
# LangGraph's default recursion limit (25) is too low for a multi-round research loop. The budget
# scales with AER_THOROUGHNESS: deeper runs make more search/fetch/reflect turns before stopping.
_RECURSION_BY_THOROUGHNESS = {"light": 120, "standard": 200, "deep": 320}
_RECURSION_LIMIT = 200  # fallback for an unrecognized thoroughness level

SYSTEM_PROMPT = """You are a meticulous senior technical researcher. Your job: produce a DETAILED, \
COMPREHENSIVE, well-grounded report a careful engineer would trust to make a build decision. You work \
by planning, searching, reading sources in full, reflecting on gaps, and stopping only when your \
success criteria are met.

You have a file workspace (write_file / read_file / edit_file / ls) and these research tools:
- web_search(query, max_results): ranked results, each marked [✓] (fetchable in full here) or [✗] \
(not reachable from here — you only get its title/snippet, which is WEAK, UNVERIFIED signal).
- fetch_url(url): returns a [✓] source's full content as clean text. A [✗]/blocked URL returns a \
"not reachable" note — don't retry it; pick a [✓] source instead.

WORKFLOW (in order):
1. SCOPE. Before searching, write `scope.md`: the sharp research question, 3-6 concrete sub-questions, \
explicit success criteria (what must be answered to be done), and your assumptions. This is your \
contract — check against it before stopping.
2. PLAN. Use write_todos to track the sub-questions as you work.
3. GATHER. Per sub-question: search, then fetch_url the most relevant [✓] results IN FULL (don't rely \
on snippets). Prefer primary sources — official repos/READMEs/code on GitHub, model cards & docs on \
Hugging Face, package pages on PyPI, official docs. Corroborate important claims across MULTIPLE \
independent sources; note disagreements.
4. REFLECT. After a gather round, write/update `reflection.md`: which success criteria are met, which \
sub-questions are still thin, and whether your evidence CONFIRMS or CONTRADICTS the prior opinions in \
the seed/brief — treat those opinions as HYPOTHESES TO TEST, not facts. Then run targeted follow-up \
searches/fetches to close the biggest gaps.
5. STOP when success criteria are genuinely met (quality-driven) — not when you run out of ideas, and \
not by padding.

GROUNDING RULES (critical — this is a research tool, not a chatbot):
- Cite ONLY sources you actually fetched (fetch_url returned real content). List them in ## Sources.
- If something is supported only by a search snippet or a blocked source, you MAY mention it but MUST \
mark it "(unverified — snippet only)" and treat it as low confidence.
- NEVER present unverified claims or your own background knowledge as findings. If you couldn't reach \
the evidence, say so plainly. Honest gaps beat confident guesses.

OUTPUT. Write the final report to `report.md`, structured so a BUILDER can act on it (these sections map \
to what Stage 3 consumes):
  # <Title>
  ## Overview — what it is, in 2-4 sentences.
  ## Recommended architecture — the components and how they fit (enough that a builder could draw it).
  ## Tech stack — per layer: the choice, the rationale, and viable alternatives.
  ## Reference implementations — the best repos to template from, why, and their maturity (stars/activity/license).
  ## Implementation steps — an ordered, concrete plan to stand up a PoC (what to build first, then next).
  ## Limitations & production-readiness — real failure modes, gotchas, what's not ready.
  ## Open questions & risks — what's unresolved or needs a decision before building.
  ## Sources — (numbered, linked; see CITATIONS).
  ## Coverage & confidence — which source kinds you could reach vs not; where confidence is HIGH (verified \
primary) vs LOWER (snippet/unreachable).
Be thorough but NOT padded — every claim earns its tokens; don't restate the brief. Do not fabricate URLs, \
quotes, or numbers. The report file is the deliverable — write it before finishing."""


M2_LEAD_PROMPT = """You are the LEAD of a research team. You scope the work, delegate to specialist \
subagents, reconcile their findings, and write the deliverables. You DO NOT do the bulk gathering \
yourself — you delegate it.

Your subagents (invoke via the task tool, in parallel where possible):
- code-scout — finds + gathers real implementations; saves code into code/**. ("what code exists")
- landscape — maps alternatives and their attributes. ("what else exists & how it compares")
- maturity — limitations + production-readiness of the subject. ("is it real & safe for prod")
- focused-investigator — spawn with a SPECIFIC instruction for an ad-hoc deep pass the three don't \
cover (e.g. a benchmarks/eval investigation, a security pass, a deep dive on one flagged limitation).

WORKFLOW:
1. SCOPE — write `scope.md`: sharp question, 3-6 sub-questions, success criteria, assumptions.
2. PLAN — write_todos for the sub-questions.
3. DELEGATE — call task for code-scout, landscape, and maturity (you may issue them together). Give \
each a focused instruction tied to the topic.
4. REFLECT — write `reflection.md`: read the subagents' summaries; note gaps + whether evidence \
CONFIRMS or CONTRADICTS the prior opinions in the seed/brief (treat them as hypotheses). If a gap is \
topic-specific (e.g. benchmark saturation, a security concern), spawn focused-investigator for it.
5. RECONCILE — where subagents disagree (e.g. code-scout's README claim vs maturity's issue reports), \
reconcile using confidence tiers (primary artifacts = HIGH; forum/snippet = MED/LOW) and flag genuine \
disagreements inline with the wiki convention `[CONTRADICTION: …]`. This tension is a FEATURE.
6. SYNTHESIZE — write the deliverables:
   - `comparison.md`: a markdown table — rows = the subject + each alternative (from landscape), \
columns = maturity, license, key strengths, key weaknesses, best-for. Build it from the subagents' \
summaries (you work from their distilled outputs, not raw context).
   - `report.md`: BUILDER-oriented, structured so Stage 3 can act on it — sections: Overview · \
Recommended architecture · Tech stack (layer → choice + rationale + alternatives) · Reference \
implementations (best repos to build from, from code-scout, with maturity) · Implementation steps \
(ordered plan to a PoC) · Limitations & production-readiness (from maturity) · Open questions & risks · \
`## Sources` (numbered, linked) · `## Coverage & confidence`. Pull real code refs from code-scout and the \
alternatives from comparison.md.

GROUNDING: cite only what the team actually fetched or got from structured APIs; mark snippet/blocked \
sources '(unverified)'. Never fill gaps from background knowledge. Be comprehensive, not padded. \
`report.md` is the primary deliverable — ensure it (and comparison.md) are written before you finish."""


# Code-kept rules appended AFTER any custom lead prompt (config/prompts/lead_lean|lead_multi.md), so an
# override can't drop the non-negotiables: grounding discipline + the required `report.md` deliverable.
_LEAD_RULES = (
    "NON-NEGOTIABLE (these hold regardless of any custom instructions above): cite ONLY sources actually "
    "fetched or returned by a structured API; mark snippet/blocked sources '(unverified)'; never present "
    "background knowledge as a finding. Write the final report to `report.md` before finishing."
)
_LEAD_RULES_MULTI = _LEAD_RULES + " In multi-agent mode also write `comparison.md`."

# Standing objective + citation format. Code-kept (applied regardless of any config/prompts override) so
# every run stays oriented at the Stage-3 PoC builder and emits traceable citations.
_MISSION = (
    "MISSION: this research is the INPUT to a Stage-3 PoC builder. The end objective is FIXED — produce "
    "BUILD-READY material an engineer can act on: a recommended architecture, a concrete tech stack (with "
    "rationale + alternatives), the best reference implementations to template from, and concrete "
    "implementation steps to stand up a working proof-of-concept. Orient gathering and the report toward "
    "what someone needs to START BUILDING — not a literature survey."
)
_CITATION_RULES = (
    "CITATIONS: in report.md, cite claims with inline numbered markers like [1], [2] placed right after the "
    "supported statement. End the report with a numbered `## Sources` list where every entry is a markdown "
    "link: `1. [title or owner/repo](url) — what it supported`. Number sources in order of first appearance "
    "and reuse the same number when a source recurs. Only fetched / structured-API sources get a number; "
    "snippet-only or blocked sources stay marked '(unverified)' and are NOT numbered."
)


def _assemble_lead(body: str, multi_agent: bool, cfg: RunConfig) -> str:
    """Wrap a lead prompt BODY with the code-kept parts. Single source of truth for the assembly order:
    mission + body + thoroughness + [fan-out budget] + citation rules + lead rules.
    """
    depth = thoroughness_directive(cfg.thoroughness)
    if multi_agent:
        fanout = (
            "FAN-OUT BUDGET: the three fixed subagents (code-scout/landscape/maturity) always run; beyond "
            f"them, spawn AT MOST {cfg.max_investigators} focused-investigator pass(es), and only for a "
            "genuine topic-specific gap — not by default."
        )
        return f"{_MISSION}\n\n{body}\n\n{depth}\n\n{fanout}\n\n{_CITATION_RULES}\n\n{_LEAD_RULES_MULTI}"
    return f"{_MISSION}\n\n{body}\n\n{depth}\n\n{_CITATION_RULES}\n\n{_LEAD_RULES}"


def lead_default_body(multi_agent: bool) -> str:
    """The built-in lead body (what a config/prompts/lead_*.md override replaces)."""
    return M2_LEAD_PROMPT if multi_agent else SYSTEM_PROMPT


def lead_appended_preview(multi_agent: bool, cfg: RunConfig) -> str:
    """Read-only display of the code-kept wrapper, with a marker where the editable body lands.

    Used by the UI prompt editor so a user sees exactly which parts an override can NOT change.
    """
    return _assemble_lead("«— your editable body (config/prompts/lead_*.md) goes here —»", multi_agent, cfg)


def compose_lead_prompt(multi_agent: bool, cfg: RunConfig) -> str:
    """Assemble the lead system prompt (pure + testable; no model/agent construction).

    Order: mission + overridable body (config/prompts/lead_*) + thoroughness + [fan-out budget] +
    citation rules + lead rules. Mission/citations/rules are code-kept so a body override can't drop them.
    """
    name = "lead_multi" if multi_agent else "lead_lean"
    base = load_prompt(name, lead_default_body(multi_agent))
    return _assemble_lead(base, multi_agent, cfg)


def _run_dir(run_id: str) -> Path:
    d = ARTIFACTS_ROOT / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def build_research_agent(cfg: RunConfig, run_dir: Path, multi_agent: bool = False, checkpointer=None):
    """Create the lead deep agent rooted at run_dir.

    multi_agent=False (M1): lean single agent with web tools.
    multi_agent=True  (M2): lead delegates to code-scout/landscape/maturity (+ focused-investigator);
      lead holds the full toolset so subagents inherit it (incl. filesystem → they can write code/**).
    checkpointer: optional LangGraph saver → enables crash-resume (same thread_id continues the run).
    """
    try:
        from deepagents.backends.filesystem import FilesystemBackend
    except ImportError:  # tolerate a top-level re-export across beta versions
        from deepagents import FilesystemBackend  # type: ignore
    from deepagents import create_deep_agent

    backend = FilesystemBackend(root_dir=str(run_dir), virtual_mode=True)
    model = build_chat_model(cfg.lead_role)
    extra = {"checkpointer": checkpointer} if checkpointer is not None else {}
    if multi_agent:
        subagents = build_subagents(
            thoroughness=cfg.thoroughness,
            code_max_repos=cfg.code_max_repos,
            code_files_per_repo=cfg.code_files_per_repo,
        )
        return create_deep_agent(
            model=model,
            tools=[*WEB_TOOLS, *STRUCTURED_TOOLS],
            system_prompt=compose_lead_prompt(True, cfg),
            subagents=subagents,
            backend=backend,
            **extra,
        )
    return create_deep_agent(
        model=model,
        tools=WEB_TOOLS,
        system_prompt=compose_lead_prompt(False, cfg),
        backend=backend,
        **extra,
    )


def _task(topic: str, brief: str) -> str:
    t = f"Research topic: {topic}\n\n"
    if brief.strip():
        t += f"Seed / brief:\n{brief.strip()}\n\n"
    t += "Follow the workflow: scope.md → plan → gather (fetch [✓] sources in full) → reflection.md → report.md."
    return t


def _read(run_dir: Path, name: str) -> str:
    p = run_dir / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def run_gather(
    topic: str,
    brief: str = "",
    config: RunConfig | None = None,
    run_id: str | None = None,
    interactive: bool = False,
    multi_agent: bool | None = None,
    resume: bool = False,
    event_callbacks: list | None = None,
) -> tuple[str, Path, str]:
    """Lead-loop entrypoint. Returns (report_markdown, run_dir, run_id).

    multi_agent: None → use cfg.multi_agent (env AER_MULTI_AGENT / pipeline.yaml); True/False overrides.
    resume: continue a prior truncated run from its checkpoint (same run_id/thread_id), restoring the
      fetch ledger from disk; the initial invoke continues the graph instead of starting fresh.
    event_callbacks: optional, presentation-agnostic LangChain callback handlers (e.g. a UI event
      handler) appended ALONGSIDE the Langfuse tracer onto invoke_config — so they trace the whole run
      tree (lead + subagents + tools) across every retry/resume attempt, exactly like the tracer.
    Writes into the run folder: report.md, scope.md, reflection.md (+ comparison.md & code/** in M2),
    coverage.json + ledger.json (ledger).
    """
    cfg = config or load_config()
    use_multi = cfg.multi_agent if multi_agent is None else multi_agent
    configure_default_cache(enabled=True, ttl_hours=24)
    run_id = run_id or new_artifact_id(use_multi)
    run_dir = _run_dir(run_id)
    ledger_path = run_dir / "ledger.json"
    evidence_path = run_dir / "evidence.json"
    # Ledger + evidence store: fresh for a new run; restored from disk on resume so coverage/sources AND
    # the structured GitHub signals (used to enrich reference_repos) span both segments. Without restoring
    # evidence, a cross-process --resume would start empty and silently emit unenriched repos.
    ledger = load_ledger(ledger_path) if resume else configure_ledger()
    load_evidence(evidence_path) if resume else configure_evidence()
    if not resume:
        # Persist the inputs needed to resume BEFORE any LLM call, so even a hard kill (Ctrl-C / docker
        # stop — which skips the salvage path) leaves enough on disk for `--resume` to recover. `multi_agent`
        # MUST be remembered: resuming with the wrong topology would mismatch the checkpointed graph.
        try:
            (run_dir / "run_meta.json").write_text(
                json.dumps({"topic": topic, "brief": brief, "multi_agent": use_multi}, indent=2)
            )
        except OSError as e:
            logger.warning("could not write run_meta.json: %s", e)
    if interactive:
        # Clarifying questions are gathered up-front at the CLI/UI layer and folded into the brief
        # (see clarify.py); the core gather loop itself always runs headless.
        logger.info("interactive clarify handled pre-brief at the CLI/UI layer; run %s proceeds headless", run_id)

    # Checkpointer: shared sqlite DB → crash-resume. Absent dep / disabled → None (no resume, no crash).
    saver = build_checkpointer(checkpoint_db_path(ARTIFACTS_ROOT)) if cfg.checkpoint_enabled else None
    if resume and saver is None:  # nothing to continue from → re-run fresh rather than invoke an empty graph
        logger.warning("run %s: resume requested but no checkpointer available; running fresh", run_id)
        resume = False
    if saver is not None and not resume:
        sweep_truncated(ARTIFACTS_ROOT, saver, cfg.checkpoint_retention_days)  # startup retention sweep

    agent = build_research_agent(cfg, run_dir, multi_agent=use_multi, checkpointer=saver)
    recursion_limit = _RECURSION_BY_THOROUGHNESS.get(cfg.thoroughness, _RECURSION_LIMIT)
    invoke_config: dict = {"recursion_limit": recursion_limit}
    if saver is not None:
        invoke_config["configurable"] = {"thread_id": run_id}
    # Optional Langfuse tracing: one handler at the top traces the whole run tree (lead + subagents +
    # tools); session=run_id groups every attempt + the extraction pass. None when AER_TRACING is off.
    # The optional UI event handler(s) ride the same seam — both propagate through the graph identically.
    mode = "multi-agent" if use_multi else "lean"
    tracer = build_tracer()
    callbacks = ([tracer] if tracer is not None else []) + list(event_callbacks or [])
    if callbacks:
        invoke_config["callbacks"] = callbacks
    logger.info(
        "research run %s %s (mode=%s lead_role=%s checkpoint=%s trace=%s) -> %s",
        run_id, "RESUMING" if resume else "starting",
        mode, cfg.lead_role, saver is not None, tracer is not None, run_dir,
    )

    # Resilience + crash-resume. A single LLM timeout / tool error mid-run must NOT throw away an
    # expensive run. We auto-resume from the last checkpoint on TRANSIENT failures (1 immediate retry,
    # then 1 after a backoff — env-tunable); a non-transient error or an exhausted budget leaves the
    # run `truncated` (checkpoint kept for manual `--resume`). On any path we still salvage whatever
    # reached disk (scope/notes/code/report-if-any) so the artifact captures the work done.
    t0 = time.monotonic()
    prior_elapsed = (ledger.elapsed_s or 0.0) if resume else 0.0
    max_attempts = cfg.resume_max_retries + 1
    succeeded = False
    try:
        for attempt in range(max_attempts):
            is_continue = resume or attempt > 0  # resume / retry → continue the graph from its checkpoint
            if attempt >= 2:  # the backed-off retry: give a loaded endpoint room to recover
                logger.info("run %s backoff %ds before resume attempt %d/%d",
                            run_id, cfg.resume_backoff_s, attempt + 1, max_attempts)
                time.sleep(cfg.resume_backoff_s)
            if tracer is not None:
                # Per-attempt trace tags (all known upfront → no fragile post-hoc tagging). A failed
                # attempt's trace still carries ERRORED spans, so failures are findable by session.
                tags = [mode] + (["resume", f"attempt-{attempt + 1}"] if is_continue else [])
                invoke_config["metadata"] = trace_metadata(run_id, tags)
            try:
                payload = None if is_continue else {"messages": [{"role": "user", "content": _task(topic, brief)}]}
                agent.invoke(payload, config=invoke_config)
                succeeded = True
                ledger.truncated = False
                break
            except Exception as e:  # noqa: BLE001 — salvage/resume instead of crashing the run
                ledger.truncated = True
                transient = is_transient_error(e)
                logger.warning(
                    "run %s attempt %d/%d failed (%s, transient=%s): %s",
                    run_id, attempt + 1, max_attempts, type(e).__name__, transient, e,
                )
                if not transient or saver is None or attempt == max_attempts - 1:
                    break  # non-transient, no checkpoint, or out of budget → stop and salvage
    finally:
        ledger.elapsed_s = prior_elapsed + (time.monotonic() - t0)
        flush_tracer()  # ephemeral container exits soon after — push the lead-loop spans now

    # Clean finish → drop this run's checkpoint (surgical, shared-DB cleanup). Truncated → keep it.
    if saver is not None:
        if succeeded:
            delete_run(saver, run_id)
        try:
            saver.conn.close()
        except Exception:  # noqa: BLE001 — connection close is best-effort
            pass

    save_ledger(ledger, ledger_path)  # snapshot so a later cross-process --resume has the fetch history
    save_evidence(current_evidence(), evidence_path)  # same: structured signals survive --resume
    coverage = ledger.manifest()  # now includes elapsed_s + truncated
    try:
        (run_dir / "coverage.json").write_text(json.dumps(coverage, indent=2))
    except OSError as e:
        logger.warning("could not write coverage.json: %s", e)

    report_md = _read(run_dir, "report.md")
    if not report_md:
        logger.warning("run %s produced no report.md%s", run_id, " (truncated)" if ledger.truncated else "")
    logger.info(
        "run %s done in %.0fs%s: fetched_ok=%d blocked/failed=%d",
        run_id, ledger.elapsed_s or 0.0, " [TRUNCATED]" if ledger.truncated else "",
        coverage["fetched_ok"], coverage["blocked_or_failed"],
    )
    return report_md, run_dir, run_id
