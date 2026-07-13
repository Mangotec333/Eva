"""
EVA GHL Agent — the 7-touch acquisition sequence (voice-DNA copy)
=================================================================

The Eva Acquisition campaign: 7 touches over 21 days, fired when a contact is
tagged ``eva-acquisition``. Copy is written to Eva's voice DNA — short sentences,
one idea per line, breathing room, quiet confidence, never sell (demonstrate).

Banned words are enforced against ``content-engine/voice_dna.py`` when it is
importable, else a built-in fallback list. ``validate_touches()`` is called by
the test suite so bad copy fails offline.

The booking link is a placeholder (``{booking_link}``) substituted at build time
from the calendar the funnel build creates. Touches 3-7 carry a book-a-call /
reply CTA, per the directive.

Each touch is a plain dict:
    {order, day, channel, name, subject, body}
``channel`` is "email" or "sms". SMS touches have an empty subject.
"""

from __future__ import annotations

from typing import Optional

CAMPAIGN_NAME = "Eva Acquisition — 7-touch (21-day)"
TRIGGER_TAG = "eva-acquisition"
LANDING_URL = "eva-acquisition.mangotec.ai"
BOOKING_PLACEHOLDER = "{booking_link}"

# Fallback banned list — kept in sync with content-engine/voice_dna.py defaults.
_FALLBACK_BANNED = [
    "game-changer", "revolutionary", "excited to announce", "thrilled",
    "leverage", "synergy", "ecosystem", "empower", "journey", "passionate",
    "cutting-edge", "unlock", "thought leadership", "paradigm",
    "transformative", "innovative", "seamless", "robust", "learnings",
    "deep dive", "circle back", "move the needle", "bandwidth",
]


def _banned_words() -> list[str]:
    """Prefer the shared content-engine banned list; fall back if unavailable."""
    try:
        import voice_dna  # type: ignore

        words = voice_dna._profile.get("voice", {}).get("banned_words", [])
        if words:
            return words
    except Exception:
        pass
    return _FALLBACK_BANNED


# ---------------------------------------------------------------------------
# The sequence
# ---------------------------------------------------------------------------

TOUCHES: list[dict] = [
    {
        "order": 1,
        "day": 0,
        "channel": "email",
        "name": "Touch 1 — Intro (the manual scanning ends here)",
        "subject": "The manual scanning ends here",
        "body": (
            "You already know the drill.\n"
            "\n"
            "Open the portals. Filter the listings. Copy the numbers.\n"
            "Do it again tomorrow.\n"
            "\n"
            "That work does not have to be yours anymore.\n"
            "\n"
            "Eva watches the deal flow for you.\n"
            "It scores 200 deals so you see the 3 worth closing.\n"
            "The other 197 get filed.\n"
            "\n"
            "See how it works:\n"
            f"{LANDING_URL}\n"
        ),
    },
    {
        "order": 2,
        "day": 2,
        "channel": "email",
        "name": "Touch 2 — The $10K/month net lens",
        "subject": "Only the net matters",
        "body": (
            "Gross rent is a headline.\n"
            "The net is the truth.\n"
            "\n"
            "A deal that reads well can still bleed after taxes, debt, and repairs.\n"
            "\n"
            "Eva runs every deal to one number: what lands in your account each month.\n"
            "\n"
            "Set the target. Say $10K net a month.\n"
            "Eva only shows you the deals that clear it.\n"
            "\n"
            "The rest never reach your inbox.\n"
        ),
    },
    {
        "order": 3,
        "day": 4,
        "channel": "email",
        "name": "Touch 3 — Never miss a hot deal (the buy box)",
        "subject": "Your buy box, watched around the clock",
        "body": (
            "Write down what you actually buy.\n"
            "\n"
            "The market. The price band. The cash-flow floor.\n"
            "That is your buy box.\n"
            "\n"
            "Eva holds it and watches every new listing against it.\n"
            "When one fits, you hear about it the same day.\n"
            "\n"
            "The hot deal does not wait a week for you to check.\n"
            "\n"
            "Want to see your buy box run live?\n"
            f"Book a call: {BOOKING_PLACEHOLDER}\n"
            "Or just reply to this email.\n"
        ),
    },
    {
        "order": 4,
        "day": 7,
        "channel": "sms",
        "name": "Touch 4 — SMS nudge (scored deal this week?)",
        "subject": "",
        "body": (
            "Want to see a scored deal this week? "
            "Eva can run your buy box live. Reply YES and I will set it up."
        ),
    },
    {
        "order": 5,
        "day": 10,
        "channel": "email",
        "name": "Touch 5 — The Monetizing Agent (a second founder)",
        "subject": "A second founder who never sleeps",
        "body": (
            "Finding the deal is half the work.\n"
            "\n"
            "The other half is turning motion into money.\n"
            "\n"
            "Eva's Monetizing Agent works that half.\n"
            "It looks at what you already do and finds the revenue you left on the table.\n"
            "\n"
            "It reads like a second founder.\n"
            "One who reviews the week and points at the cash.\n"
            "\n"
            "You stay the one who decides. Eva does the watching.\n"
            "\n"
            f"Book a call and I will show you: {BOOKING_PLACEHOLDER}\n"
            "Or reply here.\n"
        ),
    },
    {
        "order": 6,
        "day": 14,
        "channel": "email",
        "name": "Touch 6 — Traction signal (illustrative)",
        "subject": "What one week looked like",
        "body": (
            "One operator pointed Eva at a single market.\n"
            "\n"
            "Eva scored 200 deals that week.\n"
            "It flagged three worth closing.\n"
            "One went under contract.\n"
            "\n"
            "You looked at three deals, not two hundred.\n"
            "\n"
            "That is the whole idea.\n"
            "Less scanning. Better deals. Your time back.\n"
            "\n"
            "(Illustrative — your market and numbers will differ.)\n"
            "\n"
            f"See it on your market: {BOOKING_PLACEHOLDER}\n"
            "Or reply to this email.\n"
        ),
    },
    {
        "order": 7,
        "day": 21,
        "channel": "sms",
        "name": "Touch 7 — Final SMS (book a call)",
        "subject": "",
        "body": (
            "Last note from me. If a deal that clears your net target is worth "
            f"15 minutes, book here: {BOOKING_PLACEHOLDER} — or reply and we pick a time."
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render_touches(booking_link: Optional[str] = None) -> list[dict]:
    """Return the touches with the booking-link placeholder substituted.

    If ``booking_link`` is falsy, the placeholder is left in place so the copy
    still reads sensibly (and the funnel build records a manual-link gap).
    """
    link = booking_link or BOOKING_PLACEHOLDER
    rendered = []
    for t in TOUCHES:
        rendered.append({**t, "body": t["body"].replace(BOOKING_PLACEHOLDER, link)})
    return rendered


def check_banned(text: str) -> list[str]:
    """Return any banned words present in ``text`` (case-insensitive)."""
    low = text.lower()
    return [w for w in _banned_words() if w in low]


def validate_touches(touches: Optional[list[dict]] = None) -> dict:
    """Structural + voice validation. Returns a report; ``ok`` is the gate.

    Checks: exactly 7 touches, correct day cadence, channel mix, book-a-call /
    reply CTA present in touches 3-7, and zero banned words anywhere.
    """
    touches = touches or TOUCHES
    problems: list[str] = []

    if len(touches) != 7:
        problems.append(f"expected 7 touches, got {len(touches)}")

    expected_days = [0, 2, 4, 7, 10, 14, 21]
    expected_channels = ["email", "email", "email", "sms", "email", "email", "sms"]
    for i, t in enumerate(touches):
        if i < len(expected_days) and t["day"] != expected_days[i]:
            problems.append(f"touch {t['order']}: day {t['day']} != {expected_days[i]}")
        if i < len(expected_channels) and t["channel"] != expected_channels[i]:
            problems.append(
                f"touch {t['order']}: channel {t['channel']} != {expected_channels[i]}")
        if t["channel"] == "email" and not t.get("subject"):
            problems.append(f"touch {t['order']}: email missing subject")
        banned = check_banned(f"{t.get('subject','')} {t['body']}")
        if banned:
            problems.append(f"touch {t['order']}: banned words {banned}")

    # CTA (book a call / reply) required in touches 3-7.
    for t in touches:
        if t["order"] >= 3:
            low = t["body"].lower()
            if "book" not in low and "reply" not in low:
                problems.append(f"touch {t['order']}: missing book/reply CTA")

    return {"ok": not problems, "problems": problems, "count": len(touches)}


__all__ = [
    "CAMPAIGN_NAME",
    "TRIGGER_TAG",
    "LANDING_URL",
    "TOUCHES",
    "render_touches",
    "check_banned",
    "validate_touches",
]
