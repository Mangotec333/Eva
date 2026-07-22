"""Personal vs. business separation is structural, not a query-time flag.

These tests prove the two sides are backed by different database files and that
data ingested into one side is completely invisible to the other.
"""

import os

from ingest import run_ingestion
from store import DB_PATHS, TreasurerStore, open_side


def test_open_side_uses_distinct_db_files(tmp_path, monkeypatch):
    p_db = tmp_path / "treasurer_personal.db"
    b_db = tmp_path / "treasurer_business.db"
    monkeypatch.setitem(DB_PATHS, "personal", str(p_db))
    monkeypatch.setitem(DB_PATHS, "business", str(b_db))

    ps = open_side("personal")
    bs = open_side("business")
    try:
        assert ps.db_path != bs.db_path
        run_ingestion(ps, provider_name="mock")
        run_ingestion(bs, provider_name="mock")
    finally:
        ps.close()
        bs.close()

    # Two separate files physically exist on disk.
    assert os.path.exists(p_db)
    assert os.path.exists(b_db)
    assert p_db.stat().st_size > 0
    assert b_db.stat().st_size > 0


def test_sides_cannot_see_each_others_data(tmp_path, monkeypatch):
    monkeypatch.setitem(DB_PATHS, "personal", str(tmp_path / "p.db"))
    monkeypatch.setitem(DB_PATHS, "business", str(tmp_path / "b.db"))

    ps = open_side("personal")
    bs = open_side("business")
    try:
        run_ingestion(ps, provider_name="mock")
        run_ingestion(bs, provider_name="mock")

        p_insts = {a["institution"] for a in ps.list_accounts()}
        b_insts = {a["institution"] for a in bs.list_accounts()}
        assert p_insts == {"Chase", "Amex"}
        assert b_insts == {"Mercury", "Chase Ink"}
        # No overlap, and neither side sees the other's transactions.
        assert p_insts.isdisjoint(b_insts)
        assert all(t["side"] == "personal" for t in ps.list_transactions())
        assert all(t["side"] == "business" for t in bs.list_transactions())
    finally:
        ps.close()
        bs.close()


def test_reopening_a_side_sees_only_its_own_persisted_rows(tmp_path, monkeypatch):
    monkeypatch.setitem(DB_PATHS, "personal", str(tmp_path / "p.db"))

    ps = open_side("personal")
    try:
        run_ingestion(ps, provider_name="mock")
        n = len(ps.list_transactions())
    finally:
        ps.close()

    # Fresh connection to the same file — data persisted, still personal-only.
    ps2 = open_side("personal")
    try:
        assert len(ps2.list_transactions()) == n
        assert all(t["side"] == "personal" for t in ps2.list_transactions())
    finally:
        ps2.close()


def test_default_db_paths_are_distinct_filenames():
    assert os.path.basename(DB_PATHS["personal"]) == "treasurer_personal.db"
    assert os.path.basename(DB_PATHS["business"]) == "treasurer_business.db"
    assert DB_PATHS["personal"] != DB_PATHS["business"]
