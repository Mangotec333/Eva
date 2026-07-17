"""Baseline offline tests for knowledge config + api health (no network)."""

import pytest

from knowledge_config import KnowledgeConfig as cfg


def test_doc_path_valid_docs():
    for doc in cfg.VALID_DOCS:
        assert cfg.doc_path(doc).name.endswith(".md")


def test_doc_path_unknown_raises():
    with pytest.raises(ValueError):
        cfg.doc_path("does-not-exist")


def test_as_dict_shape():
    d = cfg.as_dict()
    assert d["version"] == cfg.VERSION
    assert d["valid_docs"] == cfg.VALID_DOCS
    assert "sprint" in d and "goal" in d["sprint"]


def test_api_health_endpoint():
    import knowledge_api
    from fastapi.testclient import TestClient

    client = TestClient(knowledge_api.app)
    resp = client.get("/knowledge/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
