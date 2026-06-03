"""Seed-builder: a Stage-1 wiki page -> a research seed/brief for the Stage-2 researcher.

The curated wiki (`ai-engineer-wiki`) is mounted READ-ONLY (duplicated copy). A selected page
`wiki/<Page>.md` carries exactly the signal we want to seed research with:
  - a one-sentence definition + prose body (what the concept IS),
  - `## Opinions` — ATTRIBUTED prior claims. We surface these as *hypotheses to verify or refute*,
    not facts to parrot (the "challenge the seed" behavior; see DECISIONS M1 decision C),
  - `## Sources` — real talk URLs (starting points for gathering),
  - inline `[Page-Name](Page-Name.md)` cross-links — the 1-hop neighbourhood.
`## Notes` (user notes) are deliberately ignored.

Pure stdlib (no model, no heavy deps) so it is unit-testable offline against the real wiki.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# In-container default: the duplicated read-only wiki mount. Override for local testing.
DEFAULT_WIKI_ROOT = os.environ.get("AER_WIKI_ROOT", "vault_data/wiki")

_H1 = re.compile(r"^#\s+(.+?)\s*$")
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_URL = re.compile(r"https?://[^\s)\]]+")
_WIKILINK = re.compile(r"\]\(([A-Za-z0-9][A-Za-z0-9\-]*)\.md\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")

_SPECIAL_SECTIONS = {"opinions", "sources", "notes"}


def _urls(text: str) -> list[str]:
    """All http(s) URLs, order-preserving + de-duplicated (wiki writes `[url](url)`)."""
    seen: list[str] = []
    for u in _URL.findall(text):
        u = u.rstrip(".,;")
        if u not in seen:
            seen.append(u)
    return seen


@dataclass
class Opinion:
    claim: str          # the bolded summary (the hypothesis to test)
    text: str           # full bullet text (claim + context + attribution)
    urls: list[str] = field(default_factory=list)


@dataclass
class SourceRef:
    text: str
    urls: list[str] = field(default_factory=list)


@dataclass
class Seed:
    page_id: str                 # e.g. "12-Factor-Agents"
    title: str                   # H1
    definition: str              # first paragraph
    body: str                    # prose body, minus Opinions/Sources/Notes
    opinions: list[Opinion] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    related_pages: list[str] = field(default_factory=list)  # 1-hop cross-link page ids


def _split_sections(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Return (intro_lines, [(heading, content_lines), ...]) splitting on level-2 headings."""
    intro: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    cur_heading: str | None = None
    cur_lines: list[str] = []
    for line in text.splitlines():
        m = _H2.match(line)
        if m:
            if cur_heading is None:
                intro = cur_lines
            else:
                sections.append((cur_heading, cur_lines))
            cur_heading = m.group(1).strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_heading is None:
        intro = cur_lines
    else:
        sections.append((cur_heading, cur_lines))
    return intro, sections


def _first_paragraph(lines: list[str]) -> str:
    para: list[str] = []
    for ln in lines:
        if _H1.match(ln):
            continue
        if ln.strip() == "":
            if para:
                break
            continue
        para.append(ln.strip())
    return " ".join(para).strip()


def _bullets(lines: list[str]) -> list[str]:
    """Group a markdown list into top-level bullets (continuation/indented lines folded in)."""
    bullets: list[str] = []
    for ln in lines:
        if re.match(r"^\s*[-*]\s+", ln):
            bullets.append(ln.strip()[2:].strip())
        elif ln.strip() and bullets and (ln.startswith(" ") or ln.startswith("\t")):
            bullets[-1] += " " + ln.strip()
    return bullets


def load_seed(page_id: str, wiki_root: str | Path = DEFAULT_WIKI_ROOT) -> Seed:
    """Parse `<wiki_root>/<page_id>.md` into a Seed. page_id is the filename stem (no .md)."""
    page_id = page_id[:-3] if page_id.endswith(".md") else page_id
    path = Path(wiki_root) / f"{page_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"wiki page not found: {path}")
    text = path.read_text(encoding="utf-8")

    intro, sections = _split_sections(text)
    h1 = next((m.group(1).strip() for ln in intro if (m := _H1.match(ln))), page_id)
    definition = _first_paragraph(intro)

    # Body = intro prose (minus the H1 line) + every non-special section, in order.
    body_parts = ["\n".join(ln for ln in intro if not _H1.match(ln)).strip()]
    opinions: list[Opinion] = []
    sources: list[SourceRef] = []
    for heading, lines in sections:
        key = heading.strip().lower()
        if key == "opinions":
            for b in _bullets(lines):
                claim_m = _BOLD.search(b)
                opinions.append(
                    Opinion(
                        claim=(claim_m.group(1).strip() if claim_m else b.split(".")[0].strip()),
                        text=b,
                        urls=_urls(b),
                    )
                )
        elif key == "sources":
            for b in _bullets(lines):
                sources.append(SourceRef(text=b, urls=_urls(b)))
        elif key == "notes":
            continue  # user notes — never seed from these
        else:
            body_parts.append(f"## {heading}\n" + "\n".join(lines).strip())

    related = []
    for stem in _WIKILINK.findall(text):
        if stem != page_id and stem.lower() != "index" and stem not in related:
            related.append(stem)

    return Seed(
        page_id=page_id,
        title=h1,
        definition=definition,
        body="\n\n".join(p for p in body_parts if p).strip(),
        opinions=opinions,
        sources=sources,
        related_pages=related,
    )


def build_brief(seeds: list[Seed], topic: str | None = None) -> str:
    """Render one or more Seeds into a research brief string for the lead agent.

    Opinions are framed as hypotheses to TEST; sources as starting points. The agent uses this to
    derive its scope (sharp question + success criteria) — see DECISIONS M1 decisions B/C.
    """
    if not seeds:
        return ""
    primary = seeds[0]
    topic = topic or primary.title
    out: list[str] = [
        f"# Research seed: {topic}",
        "",
        "> **How to use this seed.** It is a DELIBERATELY CONCISE Stage-1 distillation (the source wiki "
        "favors brevity). Treat it as a STARTING POINT, not a scope ceiling — your research must go "
        "substantially deeper and broader: mechanisms, real working code, limitations, alternatives, "
        "trade-offs vs those alternatives, and production-readiness, grounded in multiple independent "
        "sources. Be comprehensive, not padded — every claim earns its tokens; no filler, no restating "
        "the seed back.",
        "",
    ]

    for i, s in enumerate(seeds):
        label = "Seed concept" if i == 0 else f"Related seed: {s.title}"
        out += [f"## {label} (Stage-1 wiki page: {s.page_id})", ""]
        # Full body for the primary (it already leads with the definition); definition-only for extras.
        out += [s.body if (i == 0 and s.body) else s.definition, ""]
        if s.opinions:
            out += [
                "### Prior opinions — TEST these (verify or refute with evidence; do NOT parrot)",
                *[f"- {o.text}" for o in s.opinions],
                "",
            ]
        if s.sources:
            out += [
                "### Starting sources (Stage-1, real talk URLs)",
                *[f"- {sr.text}" for sr in s.sources],
                "",
            ]
        if s.related_pages:
            out += [
                "### Related wiki pages (1-hop — browse for adjacent context)",
                "- " + ", ".join(s.related_pages),
                "",
            ]
    return "\n".join(out).strip() + "\n"


def seed_brief(
    page_ids: list[str], wiki_root: str | Path = DEFAULT_WIKI_ROOT, topic: str | None = None
) -> tuple[str, list[Seed]]:
    """Convenience: load page_ids -> (brief_string, [Seed, ...]). Missing pages are skipped + logged."""
    import logging

    seeds: list[Seed] = []
    for pid in page_ids:
        try:
            seeds.append(load_seed(pid, wiki_root))
        except FileNotFoundError as e:
            logging.getLogger(__name__).warning("seed page skipped: %s", e)
    return build_brief(seeds, topic=topic), seeds
