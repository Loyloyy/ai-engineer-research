# Prompt overrides (optional)

Drop a markdown file here to **replace the body of a built-in prompt** — no code change, takes effect on
the next run. With no files here, the app uses the defaults baked into the code.

## How it works

An override replaces only the **body** (persona + method) of a prompt. The code still appends the
**non-negotiable parts** so a custom prompt can't break a run:

- grounding rules (cite only fetched / structured-API sources; mark snippets `(unverified)`),
- required file outputs (`report.md`, `comparison.md`, `notes/<agent>.md`, `code/**`),
- the injected knobs — thoroughness directive, fan-out budget, code-count (`AER_CODE_*`).

So write your override as the agent's **role + approach**; leave the rules/outputs to the code.

## File names (all optional)

| File | Replaces the body of |
|------|----------------------|
| `lead_lean.md` | the lean single-agent lead (`SYSTEM_PROMPT`) |
| `lead_multi.md` | the multi-agent lead / orchestrator (`M2_LEAD_PROMPT`) |
| `code-scout.md` | the code-scout subagent |
| `landscape.md` | the landscape subagent |
| `maturity.md` | the maturity subagent |
| `focused-investigator.md` | the ad-hoc focused-investigator subagent |

Relocate this directory with `AER_PROMPTS_DIR=/some/other/dir` in `.env`. An empty or unreadable file is
ignored (falls back to the default, with a logged warning). Defaults live in `src/ai_engineer_research/`
(`agent.py` for the leads, `subagents.py` for the subagents).

> These override files are **not secret** — keep them tracked in git so prompt changes are reviewable.
> (Secrets/host specifics still belong only in `.env`.)
