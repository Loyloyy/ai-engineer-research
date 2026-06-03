"""M1 lead research agent — the lean agentic loop.

ONE lead agent with web_search + fetch_url over a real-disk filesystem backend rooted at the run
folder. It runs scope → plan → gather → reflect → quality-stop, grounded in sources it actually
fetched (never backfilled from parametric memory). Cheap discipline (DECISIONS: M1):
domain-aware steering (✓/✗ in search), known-blocked fast-skip, a per-run miss-log, and a coverage
manifest. The rich structured-API tools + subagents are M2; the intelligence here is the LOOP.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .artifact import new_artifact_id
from .cache.store import configure_default_cache
from .config import RunConfig, load_config
from .models import build_chat_model
from .runlog import configure_ledger, current_ledger
from .subagents import RESEARCH_SUBAGENTS
from .tools import STRUCTURED_TOOLS, WEB_TOOLS

logger = logging.getLogger(__name__)

ARTIFACTS_ROOT = Path("artifacts")
# LangGraph's default recursion limit (25) is too low for a multi-round research loop.
_RECURSION_LIMIT = 200

SYSTEM_PROMPT = """You are a meticulous senior technical researcher. Your job: produce a DETAILED, \
COMPREHENSIVE, well-grounded report a careful engineer would trust to make a build decision. You work \
by planning, searching, reading sources in full, reflecting on gaps, and stopping only when your \
success criteria are met.

You have a file workspace (write_file / read_file / edit_file / ls) and these research tools:
- web_search(query, max_results): ranked results, each marked [✓] (fetchable in full here) or [✗] \
(egress-blocked — you only get its title/snippet, which is WEAK, UNVERIFIED signal).
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

OUTPUT. Write the final report to `report.md`:
  # <Title>
  <comprehensive, specific, structured sections: mechanisms, real code/examples, numbers, limitations, \
alternatives, trade-offs vs alternatives, production-readiness. Inline-cite by URL. Thorough but NOT \
padded — every claim earns its tokens; don't restate the brief.>
  ## Sources
  - <url> — <what it supported>
  ## Coverage & confidence
  <one short paragraph: which source kinds you could reach vs not, and where confidence is HIGH \
(verified from fetched primary sources) vs LOWER (snippet/unreachable-limited).>
The report file is the deliverable — write it before finishing. Do not fabricate URLs, quotes, or numbers."""


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
   - `report.md`: comprehensive, specific, structured (architecture/mechanisms, real code refs from \
code-scout, limitations + production-readiness from maturity, alternatives + comparison). Inline-cite \
by URL. Then `## Sources` (only fetched/API-derived) and `## Coverage & confidence` (what you could \
reach vs not; HIGH vs LOWER confidence).

GROUNDING: cite only what the team actually fetched or got from structured APIs; mark snippet/blocked \
sources '(unverified)'. Never fill gaps from background knowledge. Be comprehensive, not padded. \
`report.md` is the primary deliverable — ensure it (and comparison.md) are written before you finish."""


def _run_dir(run_id: str) -> Path:
    d = ARTIFACTS_ROOT / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def build_research_agent(cfg: RunConfig, run_dir: Path, multi_agent: bool = False):
    """Create the lead deep agent rooted at run_dir.

    multi_agent=False (M1): lean single agent with web tools.
    multi_agent=True  (M2): lead delegates to code-scout/landscape/maturity (+ focused-investigator);
      lead holds the full toolset so subagents inherit it (incl. filesystem → they can write code/**).
    """
    try:
        from deepagents.backends.filesystem import FilesystemBackend
    except ImportError:  # tolerate a top-level re-export across beta versions
        from deepagents import FilesystemBackend  # type: ignore
    from deepagents import create_deep_agent

    backend = FilesystemBackend(root_dir=str(run_dir), virtual_mode=True)
    model = build_chat_model(cfg.lead_role)
    if multi_agent:
        return create_deep_agent(
            model=model,
            tools=[*WEB_TOOLS, *STRUCTURED_TOOLS],
            system_prompt=M2_LEAD_PROMPT,
            subagents=RESEARCH_SUBAGENTS,
            backend=backend,
        )
    return create_deep_agent(
        model=model,
        tools=WEB_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        backend=backend,
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
) -> tuple[str, Path, str]:
    """Lead-loop entrypoint. Returns (report_markdown, run_dir, run_id).

    multi_agent: None → use cfg.multi_agent (env AER_MULTI_AGENT / pipeline.yaml); True/False overrides.
    Writes into the run folder: report.md, scope.md, reflection.md (+ comparison.md & code/** in M2),
    coverage.json (ledger).
    """
    cfg = config or load_config()
    use_multi = cfg.multi_agent if multi_agent is None else multi_agent
    configure_default_cache(enabled=True, ttl_hours=24)
    configure_ledger()  # fresh per-run miss-log (shared across subagents — they run in-process)
    run_id = run_id or new_artifact_id()
    run_dir = _run_dir(run_id)
    if interactive:
        logger.info("interactive scope-gate not wired yet; running headless for run %s", run_id)

    agent = build_research_agent(cfg, run_dir, multi_agent=use_multi)
    logger.info(
        "research run %s starting (mode=%s lead_role=%s) -> %s",
        run_id, "multi-agent" if use_multi else "lean", cfg.lead_role, run_dir,
    )
    agent.invoke(
        {"messages": [{"role": "user", "content": _task(topic, brief)}]},
        config={"recursion_limit": _RECURSION_LIMIT},
    )

    # Coverage manifest from the fetch ledger (objective grounding telemetry + round-2 appeal evidence).
    coverage = current_ledger().manifest()
    try:
        (run_dir / "coverage.json").write_text(json.dumps(coverage, indent=2))
    except OSError as e:
        logger.warning("could not write coverage.json: %s", e)

    report_md = _read(run_dir, "report.md")
    if not report_md:
        logger.warning("run %s finished but produced no report.md in %s", run_id, run_dir)
    logger.info(
        "run %s done: fetched_ok=%d blocked/failed=%d (blocked hosts: %s)",
        run_id, coverage["fetched_ok"], coverage["blocked_or_failed"],
        ", ".join(coverage["blocked_hosts"][:10]) or "none",
    )
    return report_md, run_dir, run_id
