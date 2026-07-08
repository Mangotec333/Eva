"""
Offline test suite for the EVA Projects module (spec section 8).

No network, no running server. Every test builds a fresh service backed by a
throwaway SQLite file, so runs are fully isolated. Runs two ways:

    python test_projects.py      # standalone runner, prints PASS/FAIL
    pytest test_projects.py      # if pytest is installed
"""

from __future__ import annotations

import json
import os
import tempfile

from database import Store
from service import SEED_TREE, ProjectError, ProjectsService

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "map.html")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> ProjectsService:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-projects-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    return ProjectsService(store=Store(path))


def _flatten_titles(tree) -> list:
    out = []
    for n in tree:
        out.append(n["title"])
        out.extend(_flatten_titles(n.get("children", [])))
    return out


def _render_map(svc: ProjectsService) -> str:
    """Mirror main._render_map without importing FastAPI (keeps tests offline)."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        template = fh.read()
    return template.replace(
        "__TREE_JSON__", json.dumps(svc.get_tree(), default=str, ensure_ascii=False)
    )


# ---------------------------------------------------------------------------
# Spec section 8 tests
# ---------------------------------------------------------------------------

def test_import_builds_tree_and_reimport_is_idempotent():
    svc = _fresh_service()
    result = svc.import_tree(SEED_TREE, actor="test")

    total = len(_flatten_titles(svc.get_tree()))
    assert result["created"] == total
    assert result["roots"] == len(SEED_TREE)

    tree = svc.get_tree()
    assert [n["title"] for n in tree] == [n["title"] for n in SEED_TREE]

    # Re-import the exact same document -> no duplicates, same node count.
    before = svc.store.count_nodes()
    svc.import_tree(SEED_TREE, actor="test")
    after = svc.store.count_nodes()
    assert before == after
    assert [n["title"] for n in svc.get_tree()] == [n["title"] for n in SEED_TREE]


def test_seed_is_idempotent_on_title():
    svc = _fresh_service()
    first = svc.seed(actor="test")
    assert len(first["created"]) == len(SEED_TREE)
    assert first["skipped"] == []

    second = svc.seed(actor="test")
    assert second["created"] == []
    assert len(second["skipped"]) == len(SEED_TREE)

    # Node count is unchanged after a second seed.
    assert len(svc.get_tree()) == len(SEED_TREE)


def test_delete_cascades_to_children():
    svc = _fresh_service()
    root = svc.create_node({"title": "Root A"})
    child = svc.create_node({"title": "Child A", "parent_id": root["id"]})
    grandchild = svc.create_node({"title": "Grandchild A", "parent_id": child["id"]})

    assert svc.store.count_nodes() == 3

    result = svc.delete_node(root["id"], actor="test")
    assert result["count"] == 3
    assert set(result["deleted"]) == {root["id"], child["id"], grandchild["id"]}

    # The whole subtree is gone.
    assert svc.store.count_nodes() == 0
    assert svc.store.get_node(child["id"]) is None
    assert svc.store.get_node(grandchild["id"]) is None


def test_move_reparents_correctly():
    svc = _fresh_service()
    a = svc.create_node({"title": "A"})
    b = svc.create_node({"title": "B"})
    child = svc.create_node({"title": "Child", "parent_id": a["id"]})

    moved = svc.move_node(child["id"], b["id"], actor="test")
    assert moved["parent_id"] == b["id"]

    tree = {n["title"]: n for n in svc.get_tree()}
    assert [c["title"] for c in tree["A"]["children"]] == []
    assert [c["title"] for c in tree["B"]["children"]] == ["Child"]


def test_move_prevents_child_of_own_descendant():
    svc = _fresh_service()
    root = svc.create_node({"title": "Root"})
    mid = svc.create_node({"title": "Mid", "parent_id": root["id"]})
    leaf = svc.create_node({"title": "Leaf", "parent_id": mid["id"]})

    # Cannot move Root under its own descendant (Mid or Leaf).
    for target in (mid["id"], leaf["id"]):
        raised = False
        try:
            svc.move_node(root["id"], target, actor="test")
        except ProjectError as exc:
            raised = True
            assert exc.code == "cycle"
        assert raised, "moving a node under its own descendant must be blocked"

    # And a node cannot be its own parent.
    raised = False
    try:
        svc.move_node(root["id"], root["id"], actor="test")
    except ProjectError:
        raised = True
    assert raised


def test_ledger_is_append_only():
    svc = _fresh_service()
    node = svc.create_node({"title": "Ledger test"})
    rows = svc.query_ledger()
    assert len(rows) >= 1
    row_id = rows[0]["id"]

    conn = svc.store._connect()
    try:
        raised_update = False
        try:
            conn.execute(
                "UPDATE project_ledger SET actor = 'tamper' WHERE id = ?", (row_id,)
            )
            conn.commit()
        except Exception:
            raised_update = True
        assert raised_update, "ledger UPDATE must be blocked"

        raised_delete = False
        try:
            conn.execute("DELETE FROM project_ledger WHERE id = ?", (row_id,))
            conn.commit()
        except Exception:
            raised_delete = True
        assert raised_delete, "ledger DELETE must be blocked"
    finally:
        conn.close()

    # The create above wrote a node_created event.
    assert any(r["event_type"] == "node_created" for r in svc.query_ledger())
    assert node["id"]


def test_map_html_contains_all_top_level_titles():
    svc = _fresh_service()
    svc.seed(actor="test")
    html = _render_map(svc)
    for spec in SEED_TREE:
        assert spec["title"] in html, f"missing top-level title: {spec['title']}"
    # The tree data is injected (placeholder consumed).
    assert "__TREE_JSON__" not in html


# ---------------------------------------------------------------------------
# Extra coverage
# ---------------------------------------------------------------------------

def test_export_roundtrip_matches_seed_structure():
    svc = _fresh_service()
    svc.seed(actor="test")
    exported = svc.export_tree()
    assert [n["title"] for n in exported] == [n["title"] for n in SEED_TREE]

    # Re-import the exported document into a fresh service -> same titles.
    svc2 = _fresh_service()
    svc2.import_tree(exported, actor="test")
    assert _flatten_titles(svc2.get_tree()) == _flatten_titles(svc.get_tree())


def test_move_ledger_records_event():
    svc = _fresh_service()
    a = svc.create_node({"title": "A"})
    b = svc.create_node({"title": "B"})
    svc.move_node(a["id"], b["id"], actor="test")
    moves = [e for e in svc.query_ledger() if e["event_type"] == "node_moved"]
    assert len(moves) == 1
    assert moves[0]["entity_id"] == a["id"]
    assert moves[0]["details"]["to_parent"] == b["id"]


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _all_tests():
    return [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    passed, failed = 0, 0
    for test in _all_tests():
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
