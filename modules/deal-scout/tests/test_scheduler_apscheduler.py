"""APScheduler-dependent wiring tests for ``scheduler.build_scheduler``.

Split out from ``test_scheduler.py`` so an environment without ``apscheduler``
installed (e.g. this network-isolated dev sandbox) skips only these tests via
``pytest.importorskip`` instead of losing collection of the whole module.
``apscheduler`` ships in requirements.txt and is expected to be present on the
live deploy host.
"""

from __future__ import annotations

import pytest

apscheduler = pytest.importorskip(
    "apscheduler", reason="apscheduler not installed in this environment")

from scheduler import (  # noqa: E402
    CYCLE_HOURS_ENV_VAR,
    PIPELINE_CYCLE_JOB_ID,
    build_scheduler,
)


def test_build_scheduler_registers_the_pipeline_job(store):
    sched = build_scheduler(lambda: store, cycle_hours=6)
    try:
        jobs = sched.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == PIPELINE_CYCLE_JOB_ID
    finally:
        sched.shutdown(wait=False)


def test_build_scheduler_uses_env_cycle_hours_by_default(store, monkeypatch):
    monkeypatch.setenv(CYCLE_HOURS_ENV_VAR, "12")
    sched = build_scheduler(lambda: store)
    try:
        job = sched.get_job(PIPELINE_CYCLE_JOB_ID)
        assert job is not None
        assert job.trigger.interval.total_seconds() == 12 * 3600
    finally:
        sched.shutdown(wait=False)
