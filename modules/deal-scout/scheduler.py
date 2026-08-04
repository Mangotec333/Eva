"""
EVA Deal Scout — automated sourcing cycle + APScheduler wiring.

Makes Deal Scout capable of running as a fully automated, scheduled sourcing
pipeline with no manual listing-ID input required: every cycle (a) discovers
currently-active EF listings, (b) scores whatever is newly pending, and
(c) evaluates the real_estate box over newly-scored deals.

``run_pipeline_cycle`` is pure orchestration over injectable/pre-built
dependencies (a ``DealStore`` plus optional overrides for each step), so it is
fully unit-testable with fakes — no network access required. The actual
APScheduler wiring (``build_scheduler`` / ``start_scheduler``) is a thin layer
on top that FastAPI's lifespan uses to run this on an interval in production.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from box_evaluator import BOX_TYPE_REAL_ESTATE
from ef_active_listings import ingest_ef_active_listings
from pipeline import score_pending
from store import DealStore

logger = logging.getLogger("deal_scout.scheduler")

DEFAULT_CYCLE_HOURS = 6
CYCLE_HOURS_ENV_VAR = "DEAL_SCOUT_CYCLE_HOURS"
PIPELINE_CYCLE_JOB_ID = "deal_scout_pipeline_cycle"


def cycle_hours_from_env(default: int = DEFAULT_CYCLE_HOURS) -> float:
    """Read the scheduling interval (hours) from ``DEAL_SCOUT_CYCLE_HOURS``.

    Falls back to ``default`` when unset or unparsable so a bad env value
    never prevents the service from starting.
    """
    raw = os.environ.get(CYCLE_HOURS_ENV_VAR)
    if not raw:
        return float(default)
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "invalid %s=%r, falling back to default of %s hours",
            CYCLE_HOURS_ENV_VAR, raw, default,
        )
        return float(default)
    if hours <= 0:
        logger.warning(
            "%s=%s must be positive, falling back to default of %s hours",
            CYCLE_HOURS_ENV_VAR, hours, default,
        )
        return float(default)
    return hours


# ---------------------------------------------------------------------------
# One automated sourcing cycle: discover -> score -> box-evaluate
# ---------------------------------------------------------------------------

def run_pipeline_cycle(
    store: DealStore,
    per_page: int = 100,
    *,
    discover_fn: Callable[..., dict[str, Any]] = ingest_ef_active_listings,
    score_fn: Callable[..., dict[str, Any]] = score_pending,
    box_type: str = BOX_TYPE_REAL_ESTATE,
    **discover_kwargs: Any,
) -> dict[str, Any]:
    """Run one full automated sourcing cycle against ``store``.

    Steps (each wrapped so a failure in one does not kill the rest of the
    cycle — the error is captured in the summary's ``errors`` list instead):

      1. Discover currently-active EF listings (``ef_active_listings``).
      2. Score every pending open raw deal (``pipeline.score_pending``).
      3. Evaluate the ``real_estate`` box over every deal scored in step 2.

    ``discover_fn`` / ``score_fn`` are injectable seams for tests (and for
    swapping in other discovery sources later); production code should never
    need to pass them explicitly. Any extra ``discover_kwargs`` (e.g.
    ``fetch_page`` in tests, or ``max_pages`` in production) are forwarded to
    ``discover_fn``.

    Returns a summary dict:
        {
          "sourced": int,        # new+updated active listings discovered
          "scored": int,         # deals scored this cycle
          "box_passed": int,     # newly-scored deals that passed the box
          "box_evaluated": int,  # newly-scored deals the box was run on
          "errors": [{"step": ..., "error": ...}, ...],
          "discover": {...} | None,
          "score": {...} | None,
          "box_type": box_type,
        }
    """
    summary: dict[str, Any] = {
        "sourced": 0,
        "scored": 0,
        "box_passed": 0,
        "box_evaluated": 0,
        "errors": [],
        "discover": None,
        "score": None,
        "box_type": box_type,
    }

    # Step (a): discover currently-active listings.
    try:
        discover_result = discover_fn(store, per_page=per_page, **discover_kwargs)
        summary["discover"] = discover_result
        summary["sourced"] = int(
            (discover_result or {}).get("new", 0) + (discover_result or {}).get("updated", 0)
        )
    except Exception as exc:  # noqa: BLE001 — one bad step must not kill the cycle
        logger.exception("deal scout cycle: discovery step failed")
        summary["errors"].append({"step": "discover", "error": f"{type(exc).__name__}: {exc}"})

    # Step (b): score whatever is pending (independent of whether discovery
    # succeeded — there may be pending rows from other sources already).
    try:
        score_result = score_fn(store)
        summary["score"] = score_result
        summary["scored"] = int((score_result or {}).get("scored", 0))
        scored_ids = list((score_result or {}).get("scored_raw_ids", []))
    except Exception as exc:  # noqa: BLE001
        logger.exception("deal scout cycle: scoring step failed")
        summary["errors"].append({"step": "score", "error": f"{type(exc).__name__}: {exc}"})
        scored_ids = []

    # Step (c): box-evaluate only the deals newly scored in this cycle.
    for deal_id in scored_ids:
        try:
            ev = store.evaluate_box(deal_id, box_type=box_type)
            summary["box_evaluated"] += 1
            if ev.box_pass:
                summary["box_passed"] += 1
        except Exception as exc:  # noqa: BLE001 — one bad deal must not kill the cycle
            logger.exception("deal scout cycle: box eval failed for deal %s", deal_id)
            summary["errors"].append({
                "step": "box_eval", "deal_id": deal_id,
                "error": f"{type(exc).__name__}: {exc}",
            })

    return summary


# ---------------------------------------------------------------------------
# APScheduler wiring (used by main.py's FastAPI lifespan)
# ---------------------------------------------------------------------------

def build_scheduler(
    store_factory: Callable[[], DealStore],
    *,
    cycle_hours: Optional[float] = None,
    per_page: int = 100,
    job_id: str = PIPELINE_CYCLE_JOB_ID,
):
    """Build (but do not start) an ``AsyncIOScheduler`` running the pipeline cycle.

    ``store_factory`` is called fresh on every tick (mirroring how ``main.py``
    already opens/closes a store per request) so the scheduler never holds a
    long-lived DB connection across ticks. Import of ``apscheduler`` is
    deferred into this function so modules that only need
    ``run_pipeline_cycle`` (e.g. unit tests) never require it to be installed.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    hours = cycle_hours if cycle_hours is not None else cycle_hours_from_env()

    def _tick() -> dict[str, Any]:
        store = store_factory()
        try:
            result = run_pipeline_cycle(store, per_page=per_page)
            logger.info("deal scout scheduled cycle complete: %s", result)
            return result
        finally:
            store.close()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _tick,
        trigger=IntervalTrigger(hours=hours),
        id=job_id,
        name="Deal Scout automated sourcing cycle",
        replace_existing=True,
    )
    return scheduler


def start_scheduler(
    store_factory: Callable[[], DealStore],
    *,
    cycle_hours: Optional[float] = None,
    per_page: int = 100,
    job_id: str = PIPELINE_CYCLE_JOB_ID,
):
    """Build and start the scheduler. Returns the running scheduler instance."""
    scheduler = build_scheduler(
        store_factory, cycle_hours=cycle_hours, per_page=per_page, job_id=job_id,
    )
    scheduler.start()
    return scheduler


__all__ = [
    "DEFAULT_CYCLE_HOURS",
    "CYCLE_HOURS_ENV_VAR",
    "PIPELINE_CYCLE_JOB_ID",
    "cycle_hours_from_env",
    "run_pipeline_cycle",
    "build_scheduler",
    "start_scheduler",
]
