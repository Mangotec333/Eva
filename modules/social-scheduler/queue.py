"""
EVA Social-Scheduler — the content queue (built on the local sqlite store).

The queue is Eva's own: day-1 is pre-seeded from ``scheduler.DAY1_QUEUE`` and
future days are drafted into the same table by content-engine. Two guarantees:

  * **Dedupe by headline hash** — a headline already in the queue is never
    re-enqueued (``store.enqueue`` enforces the UNIQUE hash), so a posted
    headline never repeats.
  * **30-day rolling window** — ``prune`` drops stale *unposted* queue rows
    older than the window; published history is preserved in ``post_history``.
"""

from __future__ import annotations

from datetime import timedelta

import scheduler
import store


def seed_day1(scheduled_date: str | None = None, path: str | None = None) -> dict:
    """Pre-seed the 5 day-1 posts for ``scheduled_date`` (ET today by default).

    Idempotent via headline-hash dedupe: re-seeding the same day adds nothing.
    """
    date_str = scheduled_date or scheduler.today_et_date()
    added, skipped = [], []
    for item in scheduler.DAY1_QUEUE:
        row = store.enqueue(
            headline=item["headline"],
            text=item["text"],
            image_path=item["image"],
            platforms=["linkedin", "x"],
            cta=scheduler.CTA_COMMENT,
            scheduled_date=date_str,
            slot=item["slot"],
            path=path,
        )
        (skipped if row.get("duplicate") else added).append(row["id"])
    return {"ok": True, "scheduled_date": date_str,
            "added": added, "skipped_duplicates": skipped}


def add_post(*, headline: str, text: str, image_path: str = "",
             scheduled_date: str, slot: str,
             platforms: list[str] | None = None,
             path: str | None = None) -> dict:
    """Add a single future post (content-engine calls this). Deduped."""
    return store.enqueue(
        headline=headline, text=text, image_path=image_path,
        platforms=platforms or ["linkedin", "x"], cta=scheduler.CTA_COMMENT,
        scheduled_date=scheduled_date, slot=slot, path=path)


def due_items(now=None, path: str | None = None) -> list[dict]:
    """Queued items whose ET slot time has arrived, soonest first."""
    out = []
    for item in store.list_queue(status=store.STATUS_QUEUED, path=path):
        if scheduler.is_slot_due(item["scheduled_date"], item["slot"], now=now):
            out.append(item)
    return out


def submitted_items(path: str | None = None) -> list[dict]:
    """Items already sent to the Slack gate, awaiting approval + publish."""
    return store.list_queue(status=store.STATUS_SUBMITTED, path=path)


def prune(window_days: int = 30, now=None, path: str | None = None) -> int:
    """Drop still-queued items older than the rolling window."""
    cutoff = scheduler.now_et(now).date() - timedelta(days=window_days)
    return store.prune_queue(cutoff.strftime("%Y-%m-%d"), path=path)


__all__ = ["seed_day1", "add_post", "due_items", "submitted_items", "prune"]
