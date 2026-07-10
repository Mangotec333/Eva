"""
EVA State Ledger — offline test suite (Stub transports, zero network).

Covers: append-only immutability (the trigger), correction events, coined_term
first-class entity + traction query, derived views, project-map generation from
the ledger, stale-state detection (batch.ai drop), and the idempotent seed.

Run:  python -m pytest modules/eva-state/
"""

from __future__ import annotations

import os
import sqlite3

import pytest

import memory
import project_map
import seed as seed_mod
from service import StateService, StubStateTransport

# Force offline stubs everywhere.
os.environ["EVA_STATE_OFFLINE"] = "1"


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "memory.db")
    memory.init_db(path)
    return path


@pytest.fixture()
def svc(db):
    return StateService(db_path=db, transport=StubStateTransport(), offline=True)


# ---------------------------------------------------------------------------
# Append-only immutability (the trigger)
# ---------------------------------------------------------------------------

def test_ledger_blocks_identity_update(db):
    eid = memory.append_event(event_type="task_created", entity_type="task",
                              entity_id="t1", summary="do a thing", path=db)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE events SET summary = 'tampered' WHERE event_id = ?", (eid,))
            conn.commit()
    finally:
        conn.close()


def test_ledger_blocks_delete(db):
    eid = memory.append_event(event_type="task_created", entity_type="task",
                              entity_id="t1", summary="x", path=db)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM events WHERE event_id = ?", (eid,))
            conn.commit()
    finally:
        conn.close()


def test_ledger_allows_status_transition(db):
    """Only the lifecycle status column may change in place."""
    eid = memory.append_event(event_type="blocker_added", entity_type="blocker",
                              entity_id="b1", summary="stuck",
                              status=memory.STATUS_BLOCKED, path=db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE events SET status = ? WHERE event_id = ?",
                     (memory.STATUS_DONE, eid))
        conn.commit()
    finally:
        conn.close()
    assert memory.get_event(eid, db)["status"] == memory.STATUS_DONE


# ---------------------------------------------------------------------------
# Correction events
# ---------------------------------------------------------------------------

def test_correction_supersedes_original(db):
    orig = memory.append_event(event_type="project_status_changed",
                               entity_type="deal", entity_id="batch-ai",
                               project="Acquisition Pipeline",
                               summary="Open — LOI sent, awaiting broker",
                               status=memory.STATUS_OPEN, path=db)
    corr = memory.correct_event(orig, summary="batch.ai DROPPED — walked away 2026-06-05",
                                status=memory.STATUS_DROPPED, path=db)
    assert memory.get_event(orig, db)["status"] == memory.STATUS_SUPERSEDED
    correction = memory.get_event(corr, db)
    assert correction["event_type"] == "correction_event"
    assert correction["supersedes_event_id"] == orig
    assert correction["corrects_event_id"] == orig
    # Both rows still exist — nothing deleted (append-only history preserved).
    assert len(memory.list_events(entity_id="batch-ai", path=db)) == 2


def test_correct_unknown_event_raises(db):
    with pytest.raises(ValueError):
        memory.correct_event("does-not-exist", summary="nope", path=db)


def test_project_state_view_reflects_correction(db):
    orig = memory.append_event(event_type="project_status_changed",
                               entity_type="deal", entity_id="batch-ai",
                               project="Acquisition Pipeline", summary="Open",
                               status=memory.STATUS_OPEN, path=db)
    memory.correct_event(orig, summary="dropped", status=memory.STATUS_DROPPED, path=db)
    states = {r["project"]: r for r in memory.project_state(db)}
    assert states["Acquisition Pipeline"]["status"] == memory.STATUS_DROPPED


# ---------------------------------------------------------------------------
# Coined terms (first-class entity)
# ---------------------------------------------------------------------------

def test_coined_term_created(svc):
    ev = svc.coin_term("ScissorHands", domain="Football / defensive technique",
                       definition="two defenders pressing a star striker",
                       first_published_surface="Twitter (manual)",
                       first_published_date="2026-07-10")
    assert ev["entity_type"] == "coined_term"
    assert ev["entity_id"] == "scissorhands"
    assert ev["event_type"] == "coined_term_created"
    assert ev["payload"]["term"] == "ScissorHands"


def test_coined_term_referenced_and_view(svc):
    svc.coin_term("ScissorHands", domain="Football")
    svc.reference_term("ScissorHands", surface="Twitter",
                       engagement={"total": 120})
    svc.reference_term("ScissorHands", surface="LinkedIn",
                       engagement={"total": 80})
    terms = {t["term"]: t for t in svc.coined_terms()}
    sh = terms["ScissorHands"]
    assert sh["reference_count"] == 2
    assert sh["total_engagement"] == 200.0
    assert sh["last_referenced"] is not None


def test_coined_terms_queryable_by_traction(svc):
    svc.coin_term("ScissorHands", domain="Football")
    svc.coin_term("VoiceLock", domain="Writing")
    svc.reference_term("ScissorHands", surface="Twitter", engagement={"total": 300})
    svc.reference_term("ScissorHands", surface="LinkedIn", engagement={"total": 300})
    svc.reference_term("VoiceLock", surface="Blog", engagement={"total": 10})
    terms = svc.coined_terms()  # ordered by reference_count desc, engagement desc
    assert terms[0]["term"] == "ScissorHands"
    # The high-traction term is queryable as the leader.
    top = max(terms, key=lambda t: t["total_engagement"])
    assert top["term"] == "ScissorHands"


def test_coined_term_traction_surfaces_in_today(svc):
    svc.coin_term("ScissorHands", domain="Football")
    svc.reference_term("ScissorHands", surface="Twitter", engagement={"total": 500})
    today = svc.today()
    kinds = {p["kind"] for p in today["priorities"]}
    assert "coined_term_traction" in kinds
    assert any(s["term"] == "ScissorHands" for s in today["coined_term_signals"])


# ---------------------------------------------------------------------------
# Derived views: blockers, deadlines, today
# ---------------------------------------------------------------------------

def test_open_blockers_view(svc):
    svc.record(event_type="blocker_added", entity_type="blocker",
               entity_id="eva-panel", project="Hosted Interfaces",
               summary="4 crons 404", status=memory.STATUS_BLOCKED)
    blockers = svc.open_blockers()
    assert len(blockers) == 1
    assert blockers[0]["entity_id"] == "eva-panel"
    # And it shows up as a top priority in today.
    prio = svc.today()["priorities"]
    assert any(p["kind"] == "blocker" and p["priority"] == 100 for p in prio)


def test_deadline_task_in_today(svc):
    svc.record(event_type="task_created", entity_type="task",
               entity_id="storeys-fund", project="Storeys", summary="fund formation",
               status=memory.STATUS_OPEN, payload={"deadline": "2026-09-30"})
    prio = svc.today()["priorities"]
    assert any(p["kind"] == "deadline" for p in prio)


def test_pending_approvals_view(svc):
    svc.record(event_type="approval_requested", entity_type="approval",
               entity_id="brief-42", summary="approve the Sunday brief")
    assert len(svc.pending_approvals()) == 1
    svc.record(event_type="approval_granted", entity_type="approval",
               entity_id="brief-42", summary="approved")
    assert len(svc.pending_approvals()) == 0


def test_agent_health_view(svc):
    svc.record(event_type="agent_run_completed", entity_type="agent",
               entity_id="monetizing-agent", summary="scan ok",
               status=memory.STATUS_DONE)
    health = svc.agent_health()
    assert any(h["agent"] == "monetizing-agent" for h in health)


# ---------------------------------------------------------------------------
# Event filtering
# ---------------------------------------------------------------------------

def test_event_filtering(svc):
    svc.record(event_type="decision_made", project="A", summary="d1")
    svc.record(event_type="task_created", project="B", summary="t1")
    assert len(svc.events(project="A")) == 1
    assert len(svc.events(event_type="task_created")) == 1
    assert len(svc.events()) == 2


# ---------------------------------------------------------------------------
# Project-map generation from the ledger
# ---------------------------------------------------------------------------

def test_project_map_built_from_ledger(svc, db):
    svc.record(event_type="project_status_changed", entity_type="module",
               entity_id="logger", project="Modules", track="core",
               summary="sensing layer", status=memory.STATUS_LIVE)
    tree = svc.project_map()
    assert tree["projects"]
    modules = [p for p in tree["projects"] if p["project"] == "Modules"][0]
    assert modules["item_count"] >= 1
    leaf = modules["tracks"][0]["items"][0]
    assert leaf["badge"] == "Production-Live"


def test_render_map_writes_json_and_html(svc, tmp_path, monkeypatch):
    monkeypatch.setattr(project_map, "JSON_PATH", str(tmp_path / "project_map.json"))
    monkeypatch.setattr(project_map, "HTML_PATH", str(tmp_path / "project_map.html"))
    svc.record(event_type="project_status_changed", entity_type="module",
               entity_id="logger", project="Modules", summary="x",
               status=memory.STATUS_LIVE)
    result = svc.render_map(write_json=True, write_html=True)
    assert os.path.exists(result["json_path"])
    assert os.path.exists(result["html_path"])
    html = open(result["html_path"]).read()
    assert "logger" in html
    assert "eva-state ledger" in html


def test_render_map_publish_gated_by_stub_transport(db, tmp_path, monkeypatch):
    transport = StubStateTransport()
    svc = StateService(db_path=db, transport=transport, offline=True)
    monkeypatch.setattr(project_map, "JSON_PATH", str(tmp_path / "project_map.json"))
    monkeypatch.setattr(project_map, "HTML_PATH", str(tmp_path / "project_map.html"))
    svc.record(event_type="project_status_changed", entity_type="module",
               entity_id="logger", project="Modules", summary="x",
               status=memory.STATUS_LIVE)
    result = svc.render_map(write_json=True, write_html=True, publish=True)
    assert result["publish"]["ok"] is True
    assert result["publish"]["stub"] is True
    assert len(transport.published) == 1


# ---------------------------------------------------------------------------
# Seed + Kalpawriksha import (idempotent) + stale-state detection
# ---------------------------------------------------------------------------

def test_import_project_map_creates_events(db):
    result = seed_mod.import_project_map(db)
    assert len(result["created"]) > 0
    # logger is a Production-Live module in the source map.
    logger_events = memory.list_events(entity_type="module", entity_id="logger", path=db)
    assert logger_events
    assert logger_events[0]["status"] == memory.STATUS_LIVE


def test_seed_all_idempotent(db):
    first = seed_mod.seed_all(db)
    total_after_first = first["total_events"]
    second = seed_mod.seed_all(db)
    # Running again must not create duplicate events.
    assert second["total_events"] == total_after_first


def test_seed_drops_batch_ai(db):
    seed_mod.seed_all(db)
    batch_events = memory.list_events(entity_type="deal", path=db)
    batch = [e for e in batch_events if "batch" in e["entity_id"].lower()]
    # There is the original (now superseded) + the correction.
    statuses = {e["status"] for e in batch}
    assert memory.STATUS_SUPERSEDED in statuses
    corrections = [e for e in batch if e["event_type"] == "correction_event"]
    assert corrections and corrections[0]["status"] == memory.STATUS_DROPPED
    # And the Acquisition Pipeline no longer shows batch.ai as open.
    acq = [r for r in memory.project_state(db)
           if r["project"] == "Acquisition Pipeline"]
    assert all(r["status"] != memory.STATUS_OPEN or "batch" not in (r["summary"] or "").lower()
               for r in acq)


def test_seed_includes_scissorhands_and_lost_state(db):
    seed_mod.seed_all(db)
    sh = memory.list_events(entity_type="coined_term", entity_id="scissorhands", path=db)
    assert sh and sh[0]["event_type"] == "coined_term_created"
    # A couple of the lost-state entities.
    assert memory.list_events(entity_id="monetizing-agent", path=db)
    assert memory.list_events(entity_id="eva-panel-backend", path=db)
    assert memory.list_events(entity_id="book-agent-scaffold", path=db)


def test_seed_eva_panel_is_open_blocker(db):
    seed_mod.seed_all(db)
    svc = StateService(db_path=db, offline=True)
    blockers = svc.open_blockers()
    assert any(b["entity_id"] == "eva-panel-backend" for b in blockers)
