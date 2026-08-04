"""Tests for the automated sourcing cycle (``scheduler.run_pipeline_cycle``)
and the APScheduler wiring.

``run_pipeline_cycle`` is tested entirely with fake/injected dependencies — no
network access, no real EF API calls. The APScheduler-dependent pieces
(``build_scheduler`` / FastAPI lifespan wiring in ``main.py``) are exercised
only if ``apscheduler`` (and FastAPI, for the lifespan test) are actually
importable in this environment; otherwise those specific tests are skipped
rather than failing the whole suite, since this sandbox has no internet access
to install them (they are required at deploy time via requirements.txt).
"""

from __future__ import annotations

from box_evaluator import BOX_TYPE_REAL_ESTATE
from pipeline_models import RawDeal
from scheduler import (
    CYCLE_HOURS_ENV_VAR,
    DEFAULT_CYCLE_HOURS,
    cycle_hours_from_env,
    run_pipeline_cycle,
)


# ---------------------------------------------------------------------------
# cycle_hours_from_env
# ---------------------------------------------------------------------------

def test_cycle_hours_defaults_when_unset(monkeypatch):
    monkeypatch.delenv(CYCLE_HOURS_ENV_VAR, raising=False)
    assert cycle_hours_from_env() == float(DEFAULT_CYCLE_HOURS)


def test_cycle_hours_reads_env(monkeypatch):
    monkeypatch.setenv(CYCLE_HOURS_ENV_VAR, "3")
    assert cycle_hours_from_env() == 3.0


def test_cycle_hours_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv(CYCLE_HOURS_ENV_VAR, "not-a-number")
    assert cycle_hours_from_env() == float(DEFAULT_CYCLE_HOURS)


def test_cycle_hours_falls_back_on_non_positive(monkeypatch):
    monkeypatch.setenv(CYCLE_HOURS_ENV_VAR, "0")
    assert cycle_hours_from_env() == float(DEFAULT_CYCLE_HOURS)


# ---------------------------------------------------------------------------
# run_pipeline_cycle — fully fake dependencies, no network
# ---------------------------------------------------------------------------

def _fake_discover_ok(store, per_page=100, **kwargs):
    # Simulate discovering + persisting one new open EF deal directly, the
    # same shape ingest_ef_active_listings would leave behind.
    store.upsert_raw_deal(RawDeal(
        id="", source="empire_flippers", listing_id="cycle-1",
        name="Cycle Candidate", asking_price=600_000, monthly_net=22_000,
        registration_country="US",
        raw_json='{"last_month_net": 22000, "ttm_avg_net": 22000}',
    ))
    return {"new": 1, "updated": 0, "active_found": 1, "pages_fetched": 1}


def test_full_cycle_sources_scores_and_box_evaluates(store):
    result = run_pipeline_cycle(store, discover_fn=_fake_discover_ok)

    assert result["errors"] == []
    assert result["sourced"] == 1
    assert result["scored"] == 1
    assert result["box_evaluated"] == 1
    assert result["box_passed"] == 1          # strong flat cash flow clears the box
    assert result["box_type"] == BOX_TYPE_REAL_ESTATE
    assert result["discover"]["active_found"] == 1
    assert result["score"]["scored"] == 1

    # The box verdict was actually persisted.
    box_deals = store.list_box_deals(box_type=BOX_TYPE_REAL_ESTATE)
    assert len(box_deals) == 1


def test_cycle_counts_box_fail_without_erroring(store):
    def discover_weak(store, per_page=100, **kwargs):
        store.upsert_raw_deal(RawDeal(
            id="", source="empire_flippers", listing_id="weak-1",
            name="Weak Deal", asking_price=600_000, monthly_net=5_000,
            registration_country="US",
            raw_json='{"last_month_net": 5000, "ttm_avg_net": 5000}',
        ))
        return {"new": 1, "updated": 0}

    result = run_pipeline_cycle(store, discover_fn=discover_weak)
    assert result["errors"] == []
    assert result["scored"] == 1
    assert result["box_evaluated"] == 1
    assert result["box_passed"] == 0          # thin cash flow fails the box floors


def test_discover_failure_does_not_kill_the_cycle(store):
    # Seed a pending deal from a totally separate path so scoring still has
    # something to do even though "discovery" blows up.
    store.upsert_raw_deal(RawDeal(
        id="", source="flippa", listing_id="preexisting",
        name="Already Pending", asking_price=80_000, monthly_net=4_000,
        registration_country="US",
    ))

    def discover_boom(store, per_page=100, **kwargs):
        raise RuntimeError("EF API unreachable")

    result = run_pipeline_cycle(store, discover_fn=discover_boom)
    assert result["sourced"] == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0]["step"] == "discover"
    assert "EF API unreachable" in result["errors"][0]["error"]
    # Scoring still ran despite the discovery failure.
    assert result["scored"] == 1


def test_score_failure_does_not_kill_the_cycle(store):
    def score_boom(store, **kwargs):
        raise RuntimeError("scorer exploded")

    result = run_pipeline_cycle(
        store, discover_fn=_fake_discover_ok, score_fn=score_boom)
    assert result["sourced"] == 1                     # discovery still succeeded
    assert result["scored"] == 0
    assert any(e["step"] == "score" for e in result["errors"])
    assert result["box_evaluated"] == 0                # nothing scored to box-eval


def test_cycle_is_a_noop_summary_when_nothing_new(store):
    def discover_empty(store, per_page=100, **kwargs):
        return {"new": 0, "updated": 0, "active_found": 0}

    result = run_pipeline_cycle(store, discover_fn=discover_empty)
    assert result["sourced"] == 0
    assert result["scored"] == 0
    assert result["box_evaluated"] == 0
    assert result["box_passed"] == 0
    assert result["errors"] == []


def test_cycle_forwards_discover_kwargs_and_per_page():
    calls = {}

    class DummyStore:
        def close(self):
            pass

    def discover_capture(store, per_page=100, **kwargs):
        calls["per_page"] = per_page
        calls["kwargs"] = kwargs
        return {"new": 0, "updated": 0}

    def score_noop(store, **kwargs):
        return {"scored": 0, "scored_raw_ids": []}

    run_pipeline_cycle(
        DummyStore(), per_page=25, discover_fn=discover_capture,
        score_fn=score_noop, max_pages=3,
    )
    assert calls["per_page"] == 25
    assert calls["kwargs"] == {"max_pages": 3}
