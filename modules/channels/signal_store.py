"""
EVA Channels Hub - Signal Store
Simple JSON file store for engagement signals.
Storage: ~/.eva/channels_signal.json
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

EVA_DIR = Path.home() / ".eva"
SIGNAL_PATH = EVA_DIR / "channels_signal.json"

# ── Mock seed data ─────────────────────────────────────────────────────────────

SEED_SIGNALS = [
    {
        "id": "seed-001",
        "platform": "linkedin",
        "content": "Great insights on acquisition strategy — we're seeing similar trends in our portfolio.",
        "type": "comment",
        "url": "https://www.linkedin.com/feed/update/urn:li:share:7200000000000000001/",
        "engagement": {"likes": 14, "comments": 3},
        "timestamp": "2024-06-01T10:23:00Z",
    },
    {
        "id": "seed-002",
        "platform": "reddit",
        "content": "This matches what the thread on r/EcommerceAcquisitions discussed last week. Solid write-up.",
        "type": "reply",
        "url": "https://www.reddit.com/r/EcommerceAcquisitions/comments/abc123/",
        "engagement": {"likes": 8, "comments": 1},
        "timestamp": "2024-06-02T14:05:00Z",
    },
    {
        "id": "seed-003",
        "platform": "twitter",
        "content": "Retweeted with comment: 'Must-read for anyone in the e-com M&A space.'",
        "type": "reply",
        "url": "https://twitter.com/i/status/1800000000000000001",
        "engagement": {"likes": 22, "comments": 5},
        "timestamp": "2024-06-03T09:47:00Z",
    },
]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_signals() -> list:
    """Load signals from disk, seeding mock data on first run."""
    EVA_DIR.mkdir(parents=True, exist_ok=True)
    if not SIGNAL_PATH.exists():
        logger.info("Signal store not found — seeding with mock signals")
        _save_signals(SEED_SIGNALS)
        return SEED_SIGNALS[:]

    try:
        with open(SIGNAL_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(f"Failed to read signal store: {exc}. Resetting.")
        _save_signals(SEED_SIGNALS)
        return SEED_SIGNALS[:]


def _save_signals(signals: list) -> None:
    EVA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL_PATH, "w") as f:
        json.dump(signals, f, indent=2)


# ── Public API ─────────────────────────────────────────────────────────────────

def add_signal(
    platform: str,
    content: str,
    signal_type: str,
    url: str,
    engagement: Optional[dict] = None,
) -> dict:
    """
    Append a new engagement signal to the store.

    Args:
        platform:     "linkedin" | "reddit" | "twitter" | "facebook"
        content:      Signal content text (comment body, DM excerpt, etc.)
        signal_type:  "comment" | "dm" | "reply"
        url:          Link to the original post/thread
        engagement:   Dict with 'likes' and 'comments' counts

    Returns:
        The saved signal dict.
    """
    signal = {
        "id": str(uuid.uuid4()),
        "platform": platform,
        "content": content,
        "type": signal_type,
        "url": url,
        "engagement": engagement or {"likes": 0, "comments": 0},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    signals = _load_signals()
    signals.append(signal)
    _save_signals(signals)
    logger.info(f"Signal added: {signal['id']} ({platform}/{signal_type})")
    return signal


def get_signals(limit: int = 20) -> list:
    """
    Retrieve the most recent engagement signals.

    Args:
        limit: Maximum number of signals to return (default 20)

    Returns:
        List of signal dicts sorted newest-first.
    """
    signals = _load_signals()
    # Sort by timestamp descending
    signals.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
    return signals[:limit]
