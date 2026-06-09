# Stage 2 → Stage 3 Contract

How the **PoC Builder (Stage 3, future)** consumes the output of this Deep Research stage (Stage 2).

> **Scope:** Stage 2 only *emits* this contract; it does **not** build Stage 3. This document is the
> stable interface so Stage 3 can be built later (in a separate repo, sharing the deepagents substrate)
> against a fixed shape.

---

## 1. What a research run produces

`run_research(...)` returns `(report_markdown, DeepResearchArtifact)` and persists a **run folder**:

```
artifacts/<run_id>/
├── 00_INDEX.md       # human reading guide: this run's files in pipeline order (start here)
├── vNN.json          # the DeepResearchArtifact (machine-readable contract) — Stage 3's primary input
├── report.md         # full prose report (human-facing)
├── comparison.md     # subject-vs-alternatives matrix (multi-agent runs)
├── code/             # real source files gathered by code-scout: code/<owner-repo>/<file>
│   └── <owner-repo>/...
├── scope.md          # the run's research scope (sharp question + success criteria + assumptions)
├── reflection.md     # gaps, confidence tiers, confirm/contradict verdict on seed opinions
├── notes/            # per-subagent raw findings (code-scout.md / landscape.md / maturity.md / focused-*.md)
├── coverage.json     # fetch ledger summary (what was reachable vs blocked)
└── run_meta.json · ledger.json   # resume bookkeeping (not part of the Stage-3 contract)
```

`<run_id>` = `dra-<YYYYMMDD>-<HHMMSS>-<rand6>` (UTC, sortable), optionally suffixed `-l` (lean) or `-m`
(multi-agent). The `vNN.json` and all companion files are **co-located** in the same folder, so Stage 3
locates everything from the artifact's `id`.

**Two ways Stage 3 ingests a run:**
1. **The artifact** (`vNN.json`) — structured, validated, the contract below. *Primary.*
2. **The run folder** — `code/**` (real implementations to template from), `report.md`/`comparison.md`
   (rationale/docs), `notes/**` (provenance). *Supplementary.*

---

## 2. The `DeepResearchArtifact` (the machine-readable contract)

Pydantic v2 model (`ai_engineer_research.artifact.schema`). Flat (≤3 levels) for cross-model
reliability. Every `Finding.evidence_ids` entry is validated to resolve to a real `Source.id`.

### Top-level

| field | type | meaning |
|---|---|---|
| `id` | str | run/artifact id (`dra-…`); stable across refinement versions |
| `version` | int | 1, 2, … (refinement bumps this under the same `id`) |
| `parent_id` | str \| null | prior version ref (`<id>@vN`) when refined; else null |
| `generated_at` | str | UTC ISO-8601 |
| `model_versions` | dict | provenance — `roles` (lead/extract role names) + `coverage` manifest (see §4) |
| `topic` | str | the research topic |
| `brief` | str | the assembled brief (caller brief + Stage-1 wiki seed) |
| `seed_pages` | list[str] | Stage-1 wiki page ids used as seed |
| `findings` | list[Finding] | atomic, cited claims |
| `recommended_architectures` | list[Architecture] | suggested designs |
| `tech_stack` | list[TechStackItem] | layered tech choices + alternatives |
| `reference_repos` | list[ReferenceRepo] | real repos worth building from |
| `implementation_steps` | list[ImplementationStep] | ordered build plan |
| `open_questions` | list[str] | unresolved questions |
| `sources` | list[Source] | the verifiable source set (URLs actually fetched / API-derived) |
| `report_markdown` | str | full `report.md` content (also on disk) |

### Nested models

- **Source**: `id` (`src-NNN`), `url`, `title?`, `origin` (`"web"`|`"vault"`|`"code"`).
- **Finding**: `claim`, `evidence_ids: [Source.id]` (validated to resolve), `confidence` (0..1).
- **TechStackItem**: `layer`, `choice`, `rationale`, `alternatives: [str]`.
- **Architecture**: `name`, `summary`, `components: [str]`, `diagram_hint?`.
- **ReferenceRepo**: `name`, `url`, `license?`, `why_relevant`.
- **ImplementationStep**: `order` (int), `action`, `tools: [str]`, `est_effort?` (`S`|`M`|`L`/hours).

### Example (abridged)
```json
{
  "id": "dra-20260603-153908-7b8a9d", "version": 1, "parent_id": null,
  "generated_at": "2026-06-03T15:41:02+00:00",
  "model_versions": {"roles": {"lead": "strategic", "extract": "smart"},
                     "coverage": {"fetched_ok": 13, "blocked_or_failed": 10, "blocked_hosts": ["medium.com"]}},
  "topic": "LangChain deepagents …", "brief": "…", "seed_pages": ["DeepAgents"],
  "sources": [{"id": "src-016", "url": "https://github.com/langchain-ai/deepagents/issues/573", "origin": "web"}],
  "findings": [{"claim": "Subagents lack checkpoint persistence …", "evidence_ids": ["src-016"], "confidence": 0.95}],
  "reference_repos": [{"name": "langchain-ai/deepagents", "url": "https://github.com/langchain-ai/deepagents",
                       "license": "MIT", "why_relevant": "the reference implementation"}],
  "tech_stack": [{"layer": "orchestration", "choice": "LangGraph", "rationale": "…", "alternatives": ["CrewAI"]}],
  "implementation_steps": [{"order": 1, "action": "scaffold create_deep_agent(...)", "tools": ["deepagents"], "est_effort": "S"}]
}
```

---

## 3. Loading it

```python
from ai_engineer_research.artifact import load, list_artifacts
art = load("dra-20260603-153908-7b8a9d")          # latest version
art = load("dra-...", version=1)                  # a specific version
runs = list_artifacts()                            # [{id, latest_version, topic}, ...]
```
Or read `artifacts/<id>/vNN.json` directly (it's plain JSON validating against the schema above).

---

## 4. `model_versions` — provenance

```json
{"roles": {"lead": "<role>", "extract": "<role>"},
 "coverage": {"fetch_attempts": N, "fetched_ok": N, "blocked_or_failed": N,
              "by_outcome": {...}, "fetched_hosts": [...], "blocked_hosts": [...]}}
```
`roles` are role *names* (never concrete model ids — `.env`-driven). `coverage` is the per-run grounding
boundary: which hosts were reachable vs blocked. **Stage 3 should treat `coverage.blocked_hosts` as a
caveat** — analysis grounded only in reachable primary sources; some practitioner/long-tail sources were
unreachable (see the run's `report.md` → `## Coverage & confidence`).

---

## 5. How Stage 3 consumes this (field → PoC generation)

| Stage-3 need | Reads from |
|---|---|
| What to build / structure | `recommended_architectures` (+ `report.md` for detail) |
| Dependencies / stack | `tech_stack` (layer → choice), plus `reference_repos` for versions/licenses |
| Templates / real code to adapt | `code/**` (actual files) + `reference_repos` (name/url/license) |
| Build plan | `implementation_steps` (ordered, with `tools` + `est_effort`) |
| Rationale / docs (technical + high-level) | `report.md`, `comparison.md`, `findings` (cited) |
| What to avoid / risks | `maturity`-derived `findings` (limitations) + `open_questions` |
| Confidence / caveats to surface | `findings[].confidence`, `model_versions.coverage` |
| Attribution in generated docs | `sources` (resolve `evidence_ids` → URL/title) |

Suggested Stage-3 flow: pick a `reference_repo` + its `code/**` as the template base → use `tech_stack`
for deps → follow `implementation_steps` → generate HTML docs from `report.md`/`comparison.md` with
confidence/coverage caveats from `model_versions.coverage`.

---

## 6. Stability guarantees

**Stable (Stage 3 may rely on these):**
- The `run_research(...) -> (report_markdown, DeepResearchArtifact)` signature.
- The `DeepResearchArtifact` field names/types in §2 (additive changes only; existing fields won't be
  removed or retyped without a major version bump).
- The run-folder filenames in §1 (`vNN.json`, `report.md`, `comparison.md`, `code/`, `scope.md`,
  `reflection.md`, `notes/`, `coverage.json`).
- Citation invariant: every `Finding.evidence_id` resolves to a `Source` in the same artifact.

**Advisory (may evolve):**
- Prose structure inside `report.md` / `comparison.md` / `notes/*.md`.
- The exact `model_versions` sub-keys beyond `roles` and `coverage`.
- Subagent roster (currently code-scout / landscape / maturity + dynamic spawns).

---

## 7. Out of scope

Stage 3 (PoC + HTML-docs generation from templates) is **not built here**. This document is the contract
only. Stage 3 will live in its own repo and may share this deepagents substrate.
