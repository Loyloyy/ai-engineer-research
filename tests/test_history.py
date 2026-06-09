"""history.py read-only views over artifacts/<id>/ — no model, no network.

ARTIFACTS_ROOT is the relative Path("artifacts"), so we chdir into a tmp dir and build a fake run there.
"""
import json

from ai_engineer_research.artifact import DeepResearchArtifact, save


def _make_run(root, run_id="dra-20260610-120000-abc123-m", topic="self-hosted RAG"):
    art = DeepResearchArtifact(
        id=run_id,
        version=1,
        generated_at="2026-06-10T12:00:00+00:00",
        topic=topic,
        report_markdown="# Report\n\nSome findings [1].\n\n## Sources\n1. [x](https://github.com/o/r)\n",
    )
    save(art, root=root)  # writes root/<id>/v01.json
    run_dir = root / run_id
    (run_dir / "report.md").write_text(art.report_markdown, encoding="utf-8")
    (run_dir / "coverage.json").write_text(json.dumps({"fetched_ok": 3, "blocked_or_failed": 1}))
    notes = run_dir / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "code-scout.md").write_text("notes here")
    return run_id


def test_list_runs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    rid = _make_run(tmp_path / "artifacts")
    from ai_engineer_research.webui import history

    runs = history.list_runs()
    ids = [r["id"] for r in runs]
    assert rid in ids
    row = next(r for r in runs if r["id"] == rid)
    assert row["mode"] == "multi-agent"
    assert row["topic"] == "self-hosted RAG"


def test_run_detail_and_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    rid = _make_run(tmp_path / "artifacts")
    from ai_engineer_research.webui import history

    detail = history.run_detail(rid)
    assert detail is not None
    assert detail["artifact"]["topic"] == "self-hosted RAG"
    assert detail["coverage"]["fetched_ok"] == 3
    names = {f["name"] for f in detail["files"]}
    assert "report.md" in names and "notes/code-scout.md" in names


def test_run_detail_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    from ai_engineer_research.webui import history

    assert history.run_detail("nope-does-not-exist") is None


def test_resolve_run_file_confined(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    rid = _make_run(tmp_path / "artifacts")
    from ai_engineer_research.webui import history

    assert history.resolve_run_file(rid, "report.md") is not None
    assert history.resolve_run_file(rid, "notes/code-scout.md") is not None
    # path traversal escaping the run dir, and missing files, are rejected
    assert history.resolve_run_file(rid, "../../etc/passwd") is None
    assert history.resolve_run_file(rid, "nonexistent.md") is None
