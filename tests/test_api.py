"""FastAPI surface via TestClient — container-only (skips where fastapi/sse-starlette aren't installed).

Covers the routes that don't need a live model: history list/detail, prompt + param editing, the 409
busy mapping, and the start-run happy path (with the manager monkeypatched so no run actually launches).
"""
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sse_starlette")

from fastapi.testclient import TestClient  # noqa: E402

from ai_engineer_research.artifact import DeepResearchArtifact, save  # noqa: E402
from ai_engineer_research.webui import app as app_module  # noqa: E402
from ai_engineer_research.webui.runner import RunBusy  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Isolate artifacts (chdir) + prompt overrides (env) + pipeline.yaml (monkeypatch) into tmp.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    monkeypatch.setenv("AER_PROMPTS_DIR", str(tmp_path / "prompts"))
    from ai_engineer_research.webui import config_api

    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text("research:\n  thoroughness: standard\nartifact:\n  enabled: true\n")
    monkeypatch.setattr(config_api, "_PIPELINE_YAML", pipeline)
    return TestClient(app_module.create_app())


def _make_run(root, run_id="dra-20260610-120000-abc123-l", topic="rag"):
    art = DeepResearchArtifact(
        id=run_id, version=1, generated_at="2026-06-10T12:00:00+00:00", topic=topic,
        report_markdown="# R\n",
    )
    save(art, root=root)
    (root / run_id / "report.md").write_text("# R\n")
    return run_id


def test_history_endpoints(client, tmp_path):
    rid = _make_run(tmp_path / "artifacts")
    runs = client.get("/api/runs").json()["runs"]
    assert any(r["id"] == rid for r in runs)
    detail = client.get(f"/api/runs/{rid}").json()
    assert detail["artifact"]["topic"] == "rag"
    assert client.get("/api/runs/does-not-exist").status_code == 404
    # file serving — served file 200, missing file 404. (Path-traversal confinement is unit-tested at
    # the function level in test_history.py::test_resolve_run_file_confined; asserting it through the HTTP
    # client here is unreliable because httpx normalizes `../` out of the URL before the request is sent.)
    assert client.get(f"/api/runs/{rid}/files/report.md").status_code == 200
    assert client.get(f"/api/runs/{rid}/files/nope.md").status_code == 404


def test_prompts_roundtrip(client):
    names = [p["name"] for p in client.get("/api/prompts").json()["prompts"]]
    assert "lead_lean" in names and "clarify" in names
    # editing writes the body; the code-kept appended text is read-only/preview
    got = client.get("/api/prompts/lead_lean").json()
    assert got["has_override"] is False and got["appended_readonly"]
    put = client.put("/api/prompts/lead_lean", json={"body": "MY CUSTOM LEAD BODY"})
    assert put.status_code == 200
    again = client.get("/api/prompts/lead_lean").json()
    assert again["has_override"] is True and again["body"] == "MY CUSTOM LEAD BODY"
    assert client.get("/api/prompts/bogus").status_code == 404


def test_params_roundtrip_and_validation(client):
    assert client.get("/api/params").json()["params"]["research"]["thoroughness"] == "standard"
    ok = client.put("/api/params", json={"params": {"research": {"thoroughness": "deep"}}})
    assert ok.status_code == 200
    assert client.get("/api/params").json()["params"]["research"]["thoroughness"] == "deep"
    # a secret-looking / unknown key is rejected
    bad = client.put("/api/params", json={"params": {"research": {"api_key": "x"}}})
    assert bad.status_code == 400


def test_start_run_and_409(client, monkeypatch):
    calls = {}

    def fake_start(topic, brief="", **kw):
        calls["topic"] = topic
        return "dra-fake-l"

    monkeypatch.setattr(app_module.manager, "start", fake_start)
    r = client.post("/api/runs", json={"topic": "hello"})
    assert r.status_code == 200 and r.json()["run_id"] == "dra-fake-l"
    assert calls["topic"] == "hello"

    def busy_start(*a, **k):
        raise RunBusy("dra-other")

    monkeypatch.setattr(app_module.manager, "start", busy_start)
    assert client.post("/api/runs", json={"topic": "again"}).status_code == 409
