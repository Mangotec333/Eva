"""
EVA Social-Scheduler — the ET schedule + day-1 content queue.

The publisher runs 5 posts/day at fixed America/New_York wall-clock times,
regardless of the Mac's own timezone (Mac is America/Los_Angeles). All slot
math is done in ``zoneinfo("America/New_York")`` so DST is handled for free.

This module is pure/stdlib: it knows the schedule and the day-1 seed content,
and answers "which queue slots are due at time T?". It does not touch the
network — the service layer drives publishing.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# 5 daily slots (ET wall-clock, per spec).
SLOTS = ["08:00", "11:00", "14:00", "15:00", "17:00"]

# Analytics sync runs hourly during the working day (8am–6pm ET).
ANALYTICS_WINDOW_ET = (8, 18)

CTA_COMMENT = 'DM or comment "Eva-acquisition" to try it for free'

# Day-1 pre-seed. Each pairs a card image + posts to BOTH LinkedIn + X, then a
# CTA comment/reply. Card 1 (eva_linkedin_today.png) is already posted and is
# deliberately excluded. Image paths are basenames resolved against the card
# dir at publish time (see service.card_path); the launchd service points that
# at the Eva assets directory on the Mac.
DAY1_QUEUE = [
    {
        "slot": "08:00",
        "image": "eva_linkedin_card_2.png",
        "headline": "The deal isn't the moat. The dataset is.",
        "text": (
            "The deal isn't the moat. The dataset is.\n\n"
            "Anyone can scrape listings. No one else has your outcomes — the "
            "deals you passed, why, and what happened next. That's what Eva "
            "learns on. eva-acquisition.mangotec.ai/whitepaper"
        ),
    },
    {
        "slot": "11:00",
        "image": "eva_pe_card.png",
        "headline": "Deal flow is a myth. Filtering isn't.",
        "text": (
            "Deal flow is a myth. Filtering isn't.\n\n"
            "Everyone sees the same listings. The fund that wins is the one "
            "that filters 10,000 down to 3 before lunch. "
            "eva-acquisition.mangotec.ai/whitepaper"
        ),
    },
    {
        "slot": "14:00",
        "image": "eva_linkedin_card_3.png",
        "headline": "Every founder needs a second founder who never sleeps.",
        "text": (
            "Every founder needs a second founder who never sleeps.\n\n"
            "Eva scans overnight, scores at dawn, hands me 3 deals by coffee. "
            "I bring the judgment. She brings the volume. "
            "eva-acquisition.mangotec.ai/whitepaper"
        ),
    },
    {
        "slot": "15:00",
        "image": "eva_analyst_card.png",
        "headline": "80% reading. 20% closing.",
        "text": (
            "80% reading. 20% closing.\n\n"
            "Your analysts spend the week reading listings. 20% on deals that "
            "move the fund. That ratio is backwards. Eva flips it. "
            "eva-acquisition.mangotec.ai/whitepaper"
        ),
    },
    {
        "slot": "17:00",
        "image": "eva_linkedin_card_4.png",
        "headline": "You don't scale by doing more. You teach the machine.",
        "text": (
            "You don't scale by doing more. You teach the machine.\n\n"
            "Every listing I read, Eva reads with me. Every deal I pass, she "
            "remembers. The system gets sharper while I sleep. "
            "eva-acquisition.mangotec.ai/whitepaper"
        ),
    },
]


def now_et(now: datetime | None = None) -> datetime:
    """Current time in America/New_York (tz-aware)."""
    if now is None:
        return datetime.now(ET)
    if now.tzinfo is None:
        return now.replace(tzinfo=ET)
    return now.astimezone(ET)


def slot_datetime(date_str: str, slot: str) -> datetime:
    """The ET-aware datetime for a (YYYY-MM-DD, HH:MM) slot."""
    return datetime.strptime(f"{date_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)


def is_slot_due(date_str: str, slot: str, now: datetime | None = None) -> bool:
    """Has the ET slot time arrived (now_et >= slot datetime)?"""
    return now_et(now) >= slot_datetime(date_str, slot)


def today_et_date(now: datetime | None = None) -> str:
    return now_et(now).strftime("%Y-%m-%d")


def in_analytics_window(now: datetime | None = None) -> bool:
    """Is the current ET hour within the 8am–6pm sync window?"""
    lo, hi = ANALYTICS_WINDOW_ET
    return lo <= now_et(now).hour < hi


__all__ = [
    "ET", "SLOTS", "ANALYTICS_WINDOW_ET", "CTA_COMMENT", "DAY1_QUEUE",
    "now_et", "slot_datetime", "is_slot_due", "today_et_date",
    "in_analytics_window",
]
