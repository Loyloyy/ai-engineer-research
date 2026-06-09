"""config_api param validation — the allow-list that keeps secrets out of pipeline.yaml.

`_validate_and_merge` is pure (yaml only), so it runs without fastapi.
"""
import pytest
import yaml

from ai_engineer_research.webui import config_api


@pytest.fixture
def tmp_pipeline(monkeypatch, tmp_path):
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump({"research": {"thoroughness": "standard"}, "artifact": {"enabled": True}}))
    monkeypatch.setattr(config_api, "_PIPELINE_YAML", p)
    return p


def test_merge_allowed_keys(tmp_pipeline):
    merged = config_api._validate_and_merge({"research": {"thoroughness": "deep", "max_investigators": 4}})
    assert merged["research"]["thoroughness"] == "deep"
    assert merged["research"]["max_investigators"] == 4
    # untouched existing keys survive the merge
    assert merged["artifact"]["enabled"] is True


def test_unknown_section_rejected(tmp_pipeline):
    with pytest.raises(ValueError):
        config_api._validate_and_merge({"secrets": {"OPENAI_API_KEY": "x"}})


def test_unknown_key_rejected(tmp_pipeline):
    # A model endpoint/key must never be smuggled into the tracked yaml.
    with pytest.raises(ValueError):
        config_api._validate_and_merge({"research": {"api_base": "http://evil"}})


def test_bad_type_rejected(tmp_pipeline):
    with pytest.raises(ValueError):
        config_api._validate_and_merge({"research": {"max_investigators": "lots"}})


def test_bad_thoroughness_value_rejected(tmp_pipeline):
    with pytest.raises(ValueError):
        config_api._validate_and_merge({"research": {"thoroughness": "extreme"}})


def test_editable_params_filters_to_allowlist(tmp_pipeline, monkeypatch):
    # Even if the yaml carries an extra (non-editable) key, it isn't surfaced to the UI.
    p = tmp_pipeline
    data = yaml.safe_load(p.read_text())
    data["research"]["search_url"] = "http://searxng:8080"
    p.write_text(yaml.safe_dump(data))
    editable = config_api._editable_params()
    assert "search_url" not in editable["research"]
    assert "thoroughness" in editable["research"]
