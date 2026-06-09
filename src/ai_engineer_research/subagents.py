"""M2 subagent specs — decomposed by INVESTIGATION, not report section (DECISIONS: M2 roster).

3 fixed subagents (code-scout / landscape / maturity) + a general focused-investigator the lead
spawns for ad-hoc deep passes (benchmarks/eval, security, …). Subagents do NOT set `tools` — in
deepagents, specifying `tools` REPLACES the inherited set (dropping the built-in filesystem tools), so
we let them inherit the lead's full toolset (web + structured GitHub/HF/PyPI + filesystem) and scope
each one's behavior via its prompt. They share the run filesystem + URL cache + fetch ledger (all
in-process), so code-scout's files and each subagent's summary are available to the lead.

The roster is built per-run via `build_subagents(...)`. Each subagent prompt = an overridable BODY
(persona + method; replace via `config/prompts/<name>.md`, see prompts.py) + code-kept REQUIREMENTS
(grounding, the thoroughness directive, required file outputs, code-count knob). The requirements are
appended in code so a custom body can't drop grounding/outputs. deepagents exposes no hard per-subagent
loop counter, so thoroughness is a prompt-injected gather-round target, not an enforced iteration cap.
"""
from __future__ import annotations

from .prompts import load_prompt

_GROUNDING = (
    "GROUNDING: cite only sources you actually fetched (fetch_url returned content) or structured-API "
    "results (github_*/hf_*/pypi_*). Mark anything from a search snippet or blocked source "
    "'(unverified — snippet only)' and treat it as low confidence. Never present background knowledge as "
    "a finding. Prefer [✓] search results; don't waste calls on [✗] blocked ones."
)

# Per-subagent gather depth. Prompt-injected (deepagents has no hard loop counter) — the model
# self-limits toward the target. The lead's recursion budget scales alongside this (see agent.py).
_THOROUGHNESS = {
    "light": (
        "THOROUGHNESS=light: do ONE focused gather pass — a few targeted searches plus the most "
        "important fetches. Be quick and decisive; do not over-explore."
    ),
    "standard": (
        "THOROUGHNESS=standard: do 2-3 gather rounds — search, fetch the best [✓] sources in full, "
        "then one follow-up round to close the biggest gaps."
    ),
    "deep": (
        "THOROUGHNESS=deep: be exhaustive — 3+ gather rounds, corroborate every key claim across "
        "MULTIPLE independent sources, and chase secondary leads before returning."
    ),
}


def thoroughness_directive(level: str) -> str:
    """The gather-depth instruction for a thoroughness level (falls back to 'standard')."""
    return _THOROUGHNESS.get((level or "").strip().lower(), _THOROUGHNESS["standard"])


# Standing objective appended to every subagent (code-kept) — keeps gathering oriented at Stage 3.
_MISSION_LINE = (
    "(This research feeds a Stage-3 PoC builder — surface BUILD-RELEVANT detail an engineer needs to "
    "start building: architecture, concrete tech/versions, reference code, and how to run it.)"
)


# --- Routing descriptions (when the lead picks a subagent). Not overridable — they're dispatch hints. ---
_DESCRIPTIONS = {
    "code-scout": (
        "Find and gather REAL implementations of the subject. Use when you need to know what working "
        "code exists, what it looks like, and which repos are the reference implementations."
    ),
    "landscape": (
        "Map the alternatives to the subject and gather each alternative's attributes. Use to answer "
        "'what else exists and how does it compare' — does NOT build the final comparison matrix."
    ),
    "maturity": (
        "Assess the subject's limitations and production-readiness. Use for failure modes, gotchas, "
        "known bugs, license/cost, maturity signals, and who runs it in production."
    ),
    "focused-investigator": (
        "A general focused researcher for an ad-hoc deep pass the fixed roster doesn't cover — e.g. a "
        "benchmarks/eval investigation, a security pass, or a deep dive on one flagged limitation. "
        "Spawn this with a specific instruction when reflection reveals a topic-specific gap."
    ),
}

# --- Default BODIES (persona + method). Overridable via config/prompts/<name>.md. ---
_BODIES = {
    "code-scout": (
        "You are code-scout. Investigation: locate the best real implementations of the subject and "
        "gather actual code.\n"
        "Method: use github_search_repos to find candidate repos; github_repo for maturity (stars, "
        "license, activity); github_readme + web_search/fetch_url to understand usage; hf_search_models "
        "and pypi_package when relevant."
    ),
    "landscape": (
        "You are landscape. Investigation: identify the competing tools/approaches to the subject and "
        "collect structured attributes for each.\n"
        "Method: web_search + github_search_repos/github_repo + hf_search_models/hf_search_datasets + "
        "pypi_package to find and characterize alternatives. For EACH alternative gather: name, one-line "
        "what-it-is, maturity (stars/license/activity), key differentiators vs the subject, and URL."
    ),
    "maturity": (
        "You are maturity. Investigation: how production-ready is the subject, and what are its real "
        "limitations?\n"
        "Method: github_repo (activity, archived, open_issues), github_search_issues (search 'bug', "
        "'limitation', 'production', 'broken', 'regression' — read the real issues), pypi_package "
        "(release cadence, license, python support), hf_model_card if it's a model. Use web_search for "
        "production war-stories/postmortems (these are usually [✗] blocked → snippet-only, mark them "
        "unverified). Distinguish vendor-sanitized claims (README/model-card) from practitioner reality "
        "(issues/forums)."
    ),
    "focused-investigator": (
        "You are a focused investigator. Investigate EXACTLY what the task instruction asks — nothing "
        "more. Use any tools (web_search, fetch_url, github_*/hf_*/pypi_*)."
    ),
}


def _requirements(name: str, *, repos: int, files: int) -> str:
    """Code-kept tail appended to every subagent (grounding + required outputs + the code-count knob)."""
    if name == "code-scout":
        return (
            f"For the TOP {repos} implementations, SAVE up to {files} representative source files each "
            "into `code/<owner-repo>/<filename>` using write_file — fetch raw files via fetch_url on "
            "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>.\n"
            "For EACH saved repo, capture its BUILDABILITY for a PoC: the entry point(s)/main module, how "
            "to install and run it, and whether it ships a runnable example or quickstart — this feeds the "
            "Stage-3 build plan.\n"
            "You have TWO required file outputs before returning (write BOTH with write_file): "
            "(1) representative source files under `code/<owner-repo>/`, and (2) `notes/code-scout.md` "
            "with your full findings (repos evaluated, files saved, key implementation notes, buildability "
            "per repo). Do not return until notes/code-scout.md exists.\n"
            "Then RETURN a concise summary: the key repos (full_name, ★, license, url), which files you "
            "saved (paths under code/), buildability per repo, and notable implementation details / "
            "patterns. Do not paste large code into the summary — it's on disk."
        )
    if name == "landscape":
        return (
            "Before returning, write your full per-alternative details to `notes/landscape.md` via "
            "write_file.\n"
            "RETURN a structured per-alternative list (one block per alternative with the fields above). "
            "The lead builds the comparison matrix from your data — you do not write comparison.md."
        )
    if name == "maturity":
        return (
            "Before returning, write your full assessment (all signals, issues WITH their URLs, evidence) "
            "to `notes/maturity.md` via write_file.\n"
            "RETURN: maturity signals (version/activity/adoption), concrete limitations + failure modes "
            "WITH evidence, license/cost, production-usage evidence, and a HIGH/MED/LOW confidence tag per "
            "claim."
        )
    # focused-investigator
    return (
        "Before returning, write your findings to `notes/focused-<short-slug>.md` (derive a short slug "
        "from your task) via write_file.\n"
        "RETURN a concise, sourced summary answering the specific question you were given."
    )


SUBAGENT_NAMES = ("code-scout", "landscape", "maturity", "focused-investigator")


def _assemble_subagent(body: str, name: str, *, thoroughness: str, repos: int, files: int) -> str:
    """Wrap a subagent BODY with the code-kept parts (grounding + thoroughness + requirements + mission).
    Single source of truth for the assembly order.
    """
    depth = thoroughness_directive(thoroughness)
    reqs = _requirements(name, repos=repos, files=files)
    return f"{body}\n{_GROUNDING}\n{depth}\n{reqs}\n{_MISSION_LINE}"


def subagent_default_body(name: str) -> str:
    """The built-in body for a subagent (what config/prompts/<name>.md replaces)."""
    return _BODIES[name]


def subagent_appended_preview(
    name: str, *, thoroughness: str = "standard", code_max_repos: int = 3, code_files_per_repo: int = 3
) -> str:
    """Read-only display of a subagent's code-kept wrapper, with an editable-body marker (for the UI)."""
    return _assemble_subagent(
        "«— your editable body (config/prompts/<name>.md) goes here —»",
        name,
        thoroughness=thoroughness,
        repos=max(1, int(code_max_repos)),
        files=max(1, int(code_files_per_repo)),
    )


def build_subagents(
    *,
    thoroughness: str = "standard",
    code_max_repos: int = 3,
    code_files_per_repo: int = 3,
) -> list[dict]:
    """Build the per-run subagent roster: overridable body + code-kept requirements, knobs injected.

    thoroughness: light|standard|deep gather-depth directive appended to every subagent.
    code_max_repos / code_files_per_repo: code-scout's gather breadth.
    """
    repos = max(1, int(code_max_repos))
    files = max(1, int(code_files_per_repo))

    roster = []
    for name in SUBAGENT_NAMES:
        body = load_prompt(name, _BODIES[name])  # config/prompts/<name>.md overrides the body
        roster.append(
            {
                "name": name,
                "description": _DESCRIPTIONS[name],
                "system_prompt": _assemble_subagent(
                    body, name, thoroughness=thoroughness, repos=repos, files=files
                ),
            }
        )
    return roster
