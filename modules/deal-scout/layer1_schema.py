"""
Eva Layer 1 — Raw Signal Store Schema
======================================
Every communication ingested by Eva lands here first.
Processed=False on ingest. Layer 2 agent picks up and compresses hourly.

Media types: text | voice | calendar | social | deal | document | financial
Directions:  inbound | outbound | internal
Priority:    0 (P0 critical) → 3 (P3 parking lot)
"""

import sqlite3
from datetime import datetime, timezone

LAYER1_DDL = """
CREATE TABLE IF NOT EXISTS layer1_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Source identity
    source          TEXT NOT NULL,          -- Gmail | Slack | LinkedIn | Voice | EmpireFlippers | ...
    media_type      TEXT NOT NULL           -- text | voice | calendar | social | deal | document | financial
                    CHECK(media_type IN ('text','voice','calendar','social','deal','document','financial')),
    direction       TEXT NOT NULL           -- inbound | outbound | internal
                    CHECK(direction IN ('inbound','outbound','internal')),

    -- Relationship links (nullable — matched post-ingest by enrichment agent)
    contact_id      INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    deal_id         INTEGER REFERENCES deals(id) ON DELETE SET NULL,

    -- Timing
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    event_at        TEXT,                   -- original event timestamp (when known)

    -- Payload
    raw_payload     TEXT NOT NULL,          -- full JSON blob from source
    summary         TEXT,                   -- brief human-readable label (set by ingest agent)

    -- Processing state
    processed       INTEGER NOT NULL DEFAULT 0 CHECK(processed IN (0,1)),
    processed_at    TEXT,                   -- set when Layer 2 picks up

    -- Signal metadata
    priority        INTEGER NOT NULL DEFAULT 1 CHECK(priority BETWEEN 0 AND 3),
                                            -- 0=critical, 1=high, 2=normal, 3=low
    tags            TEXT,                   -- JSON array of tags e.g. ["deal","follow-up"]
    thread_id       TEXT,                   -- for threading email/slack convos
    external_id     TEXT,                   -- source-native ID (gmail message_id, slack ts, etc.)

    -- Dedup
    UNIQUE(source, external_id)
);

-- Index: fast lookup of unprocessed signals for Layer 2 agent
CREATE INDEX IF NOT EXISTS idx_layer1_unprocessed
    ON layer1_signals(processed, ingested_at);

-- Index: contact enrichment lookups
CREATE INDEX IF NOT EXISTS idx_layer1_contact
    ON layer1_signals(contact_id, ingested_at DESC);

-- Index: deal enrichment lookups
CREATE INDEX IF NOT EXISTS idx_layer1_deal
    ON layer1_signals(deal_id, ingested_at DESC);

-- Index: source + media_type queries
CREATE INDEX IF NOT EXISTS idx_layer1_source_type
    ON layer1_signals(source, media_type, ingested_at DESC);
"""

# ── Source registry ──────────────────────────────────────────────────────────

SOURCES = {
    # TEXT
    "gmail":           {"media_type": "text",       "priority": 0, "status": "live"},
    "slack":           {"media_type": "text",       "priority": 0, "status": "live"},
    "linkedin_dm":     {"media_type": "text",       "priority": 1, "status": "planned"},
    "sms":             {"media_type": "text",       "priority": 1, "status": "planned"},
    "whatsapp":        {"media_type": "text",       "priority": 2, "status": "parked"},
    "meta_messenger":  {"media_type": "text",       "priority": 2, "status": "parked"},

    # VOICE
    "eva_voice":       {"media_type": "voice",      "priority": 0, "status": "live"},
    "phone_call":      {"media_type": "voice",      "priority": 1, "status": "planned"},
    "voicemail":       {"media_type": "voice",      "priority": 1, "status": "planned"},
    "zoom":            {"media_type": "voice",      "priority": 2, "status": "parked"},

    # CALENDAR
    "google_calendar": {"media_type": "calendar",   "priority": 0, "status": "live"},
    "calendly":        {"media_type": "calendar",   "priority": 1, "status": "planned"},

    # SOCIAL
    "linkedin_feed":   {"media_type": "social",     "priority": 1, "status": "planned"},
    "twitter_x":       {"media_type": "social",     "priority": 2, "status": "parked"},
    "meta_social":     {"media_type": "social",     "priority": 2, "status": "parked"},
    "youtube":         {"media_type": "social",     "priority": 3, "status": "parked"},

    # DEAL SIGNALS
    "empire_flippers": {"media_type": "deal",       "priority": 0, "status": "live"},
    "acquire_com":     {"media_type": "deal",       "priority": 1, "status": "planned"},
    "flippa":          {"media_type": "deal",       "priority": 1, "status": "planned"},
    "loopnet":         {"media_type": "deal",       "priority": 2, "status": "parked"},

    # DOCUMENTS
    "google_drive":    {"media_type": "document",   "priority": 0, "status": "live"},
    "gmail_attachment":{"media_type": "document",   "priority": 0, "status": "live"},
    "direct_upload":   {"media_type": "document",   "priority": 1, "status": "planned"},
    "notion":          {"media_type": "document",   "priority": 2, "status": "planned"},

    # FINANCIAL
    "shopify":         {"media_type": "financial",  "priority": 1, "status": "planned"},
    "stripe":          {"media_type": "financial",  "priority": 1, "status": "planned"},
    "plaid":           {"media_type": "financial",  "priority": 2, "status": "parked"},
}


# ── Helper: ingest a signal ───────────────────────────────────────────────────

def ingest_signal(
    db_path: str,
    source: str,
    raw_payload: dict,
    direction: str = "inbound",
    contact_id: int = None,
    deal_id: int = None,
    event_at: str = None,
    summary: str = None,
    thread_id: str = None,
    external_id: str = None,
    tags: list = None,
) -> int | None:
    """
    Insert a raw signal into Layer 1. Returns row id or None on dedup skip.
    Uses INSERT OR IGNORE to silently skip duplicate (source, external_id) pairs.
    """
    import json

    meta = SOURCES.get(source, {})
    media_type = meta.get("media_type", "text")
    priority = meta.get("priority", 1)

    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(
            """
            INSERT OR IGNORE INTO layer1_signals
                (source, media_type, direction, contact_id, deal_id,
                 event_at, raw_payload, summary, priority, tags, thread_id, external_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                source, media_type, direction,
                contact_id, deal_id,
                event_at,
                json.dumps(raw_payload),
                summary,
                priority,
                json.dumps(tags or []),
                thread_id,
                external_id,
            )
        )
        con.commit()
        return cur.lastrowid if cur.rowcount else None
    finally:
        con.close()


# ── Helper: fetch unprocessed signals for Layer 2 ────────────────────────────

def fetch_unprocessed(db_path: str, limit: int = 100) -> list[dict]:
    import json
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT * FROM layer1_signals
            WHERE processed = 0
            ORDER BY priority ASC, ingested_at ASC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def mark_processed(db_path: str, signal_ids: list[int]):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = sqlite3.connect(db_path)
    try:
        con.executemany(
            "UPDATE layer1_signals SET processed=1, processed_at=? WHERE id=?",
            [(now, sid) for sid in signal_ids]
        )
        con.commit()
    finally:
        con.close()


# ── Init ─────────────────────────────────────────────────────────────────────

def init_layer1(db_path: str):
    """Create Layer 1 table and indexes if they don't exist."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(LAYER1_DDL)
        con.commit()
        print(f"[Eva Layer 1] Initialized at {db_path}")
    finally:
        con.close()


if __name__ == "__main__":
    import os
    db = os.path.expanduser("~/Eva/data/eva-core.db")
    init_layer1(db)
    print(f"[Eva Layer 1] Sources registered: {len(SOURCES)}")
    live = [k for k, v in SOURCES.items() if v['status'] == 'live']
    planned = [k for k, v in SOURCES.items() if v['status'] == 'planned']
    print(f"  Live    ({len(live)}): {', '.join(live)}")
    print(f"  Planned ({len(planned)}): {', '.join(planned)}")
