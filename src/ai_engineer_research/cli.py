"""CLI for the headless researcher: `ai-engineer-research "<topic>" [--brief ...] [--seed-page X ...]`."""
from __future__ import annotations

import argparse
import logging
import sys


def _pick_unfinished() -> str | None:
    """Print a numbered list of unfinished/resumable runs and let the user pick one. Returns its id."""
    from .manage import list_unfinished

    rows = list_unfinished()
    if not rows:
        print("No unfinished runs to resume.")
        return None
    if not sys.stdin.isatty():
        print("Unfinished runs (pass --resume <id> to resume one):")
        for r in rows:
            print(f"  {r['id']}  {r['topic'][:70]!r}")
        return None
    print(f"\n{len(rows)} unfinished run(s):")
    for i, r in enumerate(rows, 1):
        tag = "" if r["folder_exists"] else "  [folder missing]"
        print(f"  [{i}] {r['id']}  {r['topic'][:70]!r}{tag}")
    sel = input("\nResume which? [number, or q to cancel]: ").strip().lower()
    if not sel or sel == "q":
        print("Cancelled.")
        return None
    if not sel.isdigit() or not (1 <= int(sel) <= len(rows)):
        print("Invalid selection.")
        return None
    return rows[int(sel) - 1]["id"]


def _maybe_clarify(topic: str, brief: str, *, no_clarify: bool) -> str:
    """Ask clarifying questions before research and fold the answers into the brief.

    Default-on, but silently skipped when --no-clarify, AER_CLARIFY=0, or stdin isn't a TTY (so Docker
    batch runs never hang on input). A future UI calls clarify_questions()/fold_answers() directly.
    """
    if no_clarify or not sys.stdin.isatty():
        return brief
    from .config import load_config

    cfg = load_config()
    if not cfg.clarify:
        return brief
    from .clarify import clarify_questions, fold_answers

    questions = clarify_questions(topic, brief, cfg)
    if not questions:
        return brief
    print("\nA few clarifying questions to sharpen the scope (press Enter to skip any):")
    qa = [(q, input(f"  • {q}\n    > ").strip()) for q in questions]
    return fold_answers(brief, qa)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stage-2 deep researcher (M1 lean agentic loop).")
    ap.add_argument("topic", nargs="?", help="research topic (omit when using --resume)")
    ap.add_argument("--brief", default="", help="freeform context/brief")
    ap.add_argument("--seed-page", action="append", default=[], metavar="PAGE_ID",
                    help="Stage-1 wiki page id to seed from (repeatable)")
    ap.add_argument("--parent-id", default=None, help="refine an existing artifact (lineage)")
    ap.add_argument("--resume", nargs="?", const="", default=None, metavar="RUN_ID",
                    help="resume a truncated run by id; pass --resume with NO id to pick from a list")
    # Management of unfinished (checkpointed) runs.
    ap.add_argument("--list", action="store_true", help="list unfinished/resumable runs and exit")
    ap.add_argument("--resume-all", action="store_true", help="resume every unfinished run, then exit")
    ap.add_argument("--clean", action="store_true",
                    help="delete ALL unfinished runs' checkpoints (add --with-folders to also delete run dirs)")
    ap.add_argument("--with-folders", action="store_true", help="with --clean: also delete the run folders")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt for --clean")
    ap.add_argument("--no-clarify", action="store_true",
                    help="skip the pre-research clarifying questions (also via AER_CLARIFY=0)")
    ap.add_argument("-v", "--verbose", action="store_true", help="INFO logging")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # --- Management commands (short-circuit; no topic required) ---
    if args.list:
        from .manage import list_unfinished

        rows = list_unfinished()
        if not rows:
            print("No unfinished runs.")
            return 0
        print(f"{len(rows)} unfinished run(s):")
        for r in rows:
            tag = "" if r["folder_exists"] else "  [folder missing]"
            print(f"  {r['id']}  {r['topic'][:60]!r}{tag}")
        print("\nResume one:  ai-engineer-research --resume <id>")
        print("Resume all:  ai-engineer-research --resume-all")
        print("Delete all:  ai-engineer-research --clean [--with-folders]")
        return 0

    if args.clean:
        from .manage import list_unfinished, clean_unfinished

        rows = list_unfinished()
        if not rows:
            print("No unfinished runs to clean.")
            return 0
        what = "checkpoints AND run folders" if args.with_folders else "checkpoints"
        print(f"\n{len(rows)} unfinished run(s) to delete ({what}):")
        for r in rows:
            tag = "" if r["folder_exists"] else "  [folder missing]"
            print(f"  {r['id']}  {r['topic'][:70]!r}{tag}")
        if not args.yes:
            if not sys.stdin.isatty():
                print(f"Refusing to delete {what} for {len(rows)} run(s) without --yes (non-interactive).")
                return 1
            resp = input(f"Delete {what} for {len(rows)} unfinished run(s)? [y/N] ").strip().lower()
            if resp not in ("y", "yes"):
                print("Aborted.")
                return 1
        res = clean_unfinished(delete_folders=args.with_folders)
        print(f"Deleted {res['threads_deleted']} checkpoint(s)"
              + (f" and {res['folders_deleted']} folder(s)" if args.with_folders else "") + ".")
        return 0

    if args.resume_all:
        from .manage import resume_all_unfinished

        res = resume_all_unfinished()
        print(f"Resumed {len(res['resumed'])} run(s); {len(res['failed'])} failed.")
        if res["failed"]:
            print("Failed:", ", ".join(res["failed"]))
        return 1 if res["failed"] else 0

    if args.resume is not None:
        target = args.resume or _pick_unfinished()  # "" (bare --resume) → interactive picker
        if not target:
            return 0
        from .core import resume_research

        report, artifact = resume_research(target)
    else:
        if not args.topic:
            ap.error("topic is required (or use --resume RUN_ID)")
        from .core import run_research

        brief = _maybe_clarify(args.topic, args.brief, no_clarify=args.no_clarify)
        report, artifact = run_research(
            args.topic,
            brief,
            seed_pages=args.seed_page or None,
            parent_id=args.parent_id,
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
