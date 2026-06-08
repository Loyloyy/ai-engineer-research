"""CLI for the headless researcher: `ai-engineer-research "<topic>" [--brief ...] [--seed-page X ...]`."""
from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stage-2 deep researcher (M1 lean agentic loop).")
    ap.add_argument("topic", nargs="?", help="research topic (omit when using --resume)")
    ap.add_argument("--brief", default="", help="freeform context/brief")
    ap.add_argument("--seed-page", action="append", default=[], metavar="PAGE_ID",
                    help="Stage-1 wiki page id to seed from (repeatable)")
    ap.add_argument("--parent-id", default=None, help="refine an existing artifact (lineage)")
    ap.add_argument("--resume", default=None, metavar="RUN_ID",
                    help="resume a prior truncated run from its checkpoint (topic/brief recovered)")
    ap.add_argument("--interactive", action="store_true", help="enable the interactive scope gate (M1 later)")
    ap.add_argument("-v", "--verbose", action="store_true", help="INFO logging")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.resume:
        from .core import resume_research

        report, artifact = resume_research(args.resume)
    else:
        if not args.topic:
            ap.error("topic is required (or use --resume RUN_ID)")
        from .core import run_research

        report, artifact = run_research(
            args.topic,
            args.brief,
            seed_pages=args.seed_page or None,
            parent_id=args.parent_id,
            interactive=args.interactive,
        )

    print(f"\n=== artifact {artifact.id} v{artifact.version} ===")
    print(
        f"findings={len(artifact.findings)} tech_stack={len(artifact.tech_stack)} "
        f"repos={len(artifact.reference_repos)} steps={len(artifact.implementation_steps)} "
        f"sources={len(artifact.sources)} open_questions={len(artifact.open_questions)}"
    )
    cov = artifact.model_versions.get("coverage", {})
    if cov:
        elapsed = cov.get("elapsed_s")
        trunc = " [TRUNCATED — partial result]" if cov.get("truncated") else ""
        print(
            f"coverage: fetched_ok={cov.get('fetched_ok')} blocked/failed={cov.get('blocked_or_failed')}"
            + (f" elapsed={elapsed}s" if elapsed is not None else "")
            + trunc
        )
    print(f"\n--- report.md ({len(report)} chars) ---\n{report[:4000]}")
    if not report:
        print("(no report produced)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
