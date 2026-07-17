"""Baseline offline tests for agent-builder slugify + store + read-only catalog."""

import os
import tempfile

os.environ["AGENT_BUILDER_DB"] = os.path.join(tempfile.mkdtemp(), "agent_builder_test.db")

import agent_builder  # noqa: E402
import store  # noqa: E402


def test_slugify_normalizes_names():
    assert agent_builder.slugify("Deal Scout Agent!") == "deal-scout-agent"
    assert agent_builder.slugify("   ") == "new-agent"


def test_catalog_read_only_returns_agents():
    result = agent_builder.catalog(write=False)
    assert result["count"] >= 1
    assert isinstance(result["agents"], list)
    assert all("name" in a and "entrypoint" in a for a in result["agents"])


def test_record_and_get_scaffold_roundtrip():
    rec = store.record_scaffold("Test Agent", "test-agent", 9999,
                                "a test purpose", ["test-agent/store.py"])
    got = store.get_scaffold(rec["id"])
    assert got["name"] == "Test Agent"
    assert got["slug"] == "test-agent"
    assert got["files"] == ["test-agent/store.py"]


def test_record_and_get_sop_roundtrip():
    rec = store.record_sop("Weekly Report", "weekly-report", "manual",
                           "summary", ["step one", "step two"], ["an input"])
    got = store.get_sop(rec["id"])
    assert got["steps"] == ["step one", "step two"]
    assert got["inputs"] == ["an input"]
