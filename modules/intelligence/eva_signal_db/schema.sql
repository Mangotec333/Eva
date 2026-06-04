-- ============================================================
-- EVA SIGNAL INTELLIGENCE DATABASE
-- Living knowledge layer — signals, learnings, opinions
-- Version 1.0 | June 2026
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- SIGNALS TABLE
-- One row per insight. Never deleted — only closed or versioned.
-- ============================================================
CREATE TABLE IF NOT EXISTS signals (
    id              TEXT PRIMARY KEY,           -- UUID

    -- Classification
    signal_type     TEXT NOT NULL,              -- 'learning' | 'trend' | 'opinion' | 'hormozi' | 'unusual_whiz' | 'hn' | 'deal_signal' | 'market' | 'personal'
    source          TEXT NOT NULL,              -- 'morning_brief' | 'hormozi' | 'unusual_whiz' | 'hacker_news' | 'google_trends' | 'manual' | 'deal_scout'
    source_detail   TEXT,                       -- specific email subject, HN story title, trend name, etc.

    -- Content
    title           TEXT NOT NULL,              -- short label: "SaaS multiples compressing in 2026"
    body            TEXT NOT NULL,              -- full signal text, the learning or insight
    raw_source_text TEXT,                       -- verbatim quote from source (Hormozi line, Callan passage, etc.)

    -- Context tags
    domain          TEXT DEFAULT '[]',          -- JSON array: ['saas', 'rcfe', 'ai', 'finance', 'personal', 'deal-sourcing']
    applies_to      TEXT DEFAULT '[]',          -- JSON array of ARC entities: ['batch-ai', 'mission-villa', 'eva', 'storeys', 'general']

    -- Confidence & opinion
    confidence      REAL DEFAULT 0.7,           -- 0.0–1.0: how strongly held
    stance          TEXT DEFAULT 'belief',      -- 'belief' | 'hypothesis' | 'observation' | 'contrarian'
    is_actionable   INTEGER DEFAULT 0,          -- 1 if this drives a decision or behavior change

    -- Lifecycle
    status          TEXT DEFAULT 'active',      -- 'active' | 'validated' | 'invalidated' | 'superseded' | 'expired'
    opened_at       TEXT NOT NULL DEFAULT (datetime('now')),  -- when first captured
    valid_until     TEXT,                       -- NULL = open-ended; set for time-sensitive signals
    closed_at       TEXT,                       -- when status changed from active
    close_reason    TEXT,                       -- 'outcome_proved' | 'outcome_disproved' | 'new_evidence' | 'time_expired' | 'manual'

    -- Validation
    last_validated_at   TEXT,                   -- last time this was reviewed
    next_validation_at  TEXT,                   -- scheduled review date (default: +30 days from opened_at)
    validation_count    INTEGER DEFAULT 0,      -- how many times reviewed
    outcome_note        TEXT,                   -- what actually happened vs what was believed

    -- Version chain
    superseded_by   TEXT REFERENCES signals(id), -- if this was updated, points to the new version
    version         INTEGER DEFAULT 1,

    -- Morning brief linkage
    brief_date      TEXT,                       -- date of morning brief that surfaced this
    brief_snippet   TEXT,                       -- the specific line from the brief

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Auto-update timestamp
CREATE TRIGGER IF NOT EXISTS signals_updated AFTER UPDATE ON signals BEGIN
    UPDATE signals SET updated_at = datetime('now') WHERE id = new.id;
END;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_status      ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_type        ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_source      ON signals(source);
CREATE INDEX IF NOT EXISTS idx_signals_opened      ON signals(opened_at);
CREATE INDEX IF NOT EXISTS idx_signals_next_val    ON signals(next_validation_at);
CREATE INDEX IF NOT EXISTS idx_signals_applies     ON signals(applies_to);

-- FTS5 for keyword search across title + body + raw source
CREATE VIRTUAL TABLE IF NOT EXISTS signals_fts USING fts5(
    title, body, raw_source_text, source_detail,
    content='signals', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS signals_fts_insert AFTER INSERT ON signals BEGIN
    INSERT INTO signals_fts(rowid, title, body, raw_source_text, source_detail)
    VALUES (new.rowid, new.title, new.body, new.raw_source_text, new.source_detail);
END;
CREATE TRIGGER IF NOT EXISTS signals_fts_update AFTER UPDATE ON signals BEGIN
    DELETE FROM signals_fts WHERE rowid = old.rowid;
    INSERT INTO signals_fts(rowid, title, body, raw_source_text, source_detail)
    VALUES (new.rowid, new.title, new.body, new.raw_source_text, new.source_detail);
END;
CREATE TRIGGER IF NOT EXISTS signals_fts_delete AFTER DELETE ON signals BEGIN
    DELETE FROM signals_fts WHERE rowid = old.rowid;
END;

-- ============================================================
-- SIGNAL VALIDATION LOG
-- Every time a signal is reviewed, record what changed
-- ============================================================
CREATE TABLE IF NOT EXISTS signal_validations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT NOT NULL REFERENCES signals(id),
    validated_at    TEXT DEFAULT (datetime('now')),
    validator       TEXT DEFAULT 'eva',         -- 'eva' | 'vineet' | 'monthly_cron'
    verdict         TEXT NOT NULL,              -- 'still_true' | 'partially_true' | 'false' | 'outdated' | 'needs_more_data'
    evidence        TEXT,                       -- what data/event informed this verdict
    new_confidence  REAL,                       -- updated confidence if changed
    action_taken    TEXT                        -- 'kept_active' | 'closed' | 'superseded' | 'confidence_updated'
);

CREATE INDEX IF NOT EXISTS idx_val_signal_id ON signal_validations(signal_id);
CREATE INDEX IF NOT EXISTS idx_val_date      ON signal_validations(validated_at);

-- ============================================================
-- ACTIVE SIGNALS VIEW — what Eva shows in morning brief
-- ============================================================
CREATE VIEW IF NOT EXISTS active_signals AS
SELECT
    id, signal_type, source, title, body,
    domain, applies_to, confidence, stance,
    is_actionable, status, opened_at,
    valid_until, next_validation_at,
    validation_count, brief_date, version
FROM signals
WHERE status = 'active'
ORDER BY
    is_actionable DESC,
    confidence DESC,
    opened_at DESC;

-- ============================================================
-- DUE FOR VALIDATION VIEW — signals needing monthly review
-- ============================================================
CREATE VIEW IF NOT EXISTS signals_due_for_validation AS
SELECT
    id, signal_type, source, title, confidence,
    opened_at, last_validated_at, next_validation_at,
    validation_count, status
FROM signals
WHERE status = 'active'
  AND (
      next_validation_at IS NULL
      OR next_validation_at <= date('now')
  )
ORDER BY next_validation_at ASC, confidence ASC;

-- ============================================================
-- OPINION LEDGER VIEW — beliefs/stances that have changed
-- Tracks intellectual honesty — when we changed our mind
-- ============================================================
CREATE VIEW IF NOT EXISTS opinion_ledger AS
SELECT
    s_old.title        AS original_belief,
    s_old.body         AS original_text,
    s_old.confidence   AS original_confidence,
    s_old.opened_at    AS believed_since,
    s_old.closed_at    AS belief_closed,
    s_old.close_reason AS why_closed,
    s_old.outcome_note AS what_actually_happened,
    s_new.title        AS new_belief,
    s_new.body         AS new_text,
    s_new.confidence   AS new_confidence
FROM signals s_old
LEFT JOIN signals s_new ON s_new.id = s_old.superseded_by
WHERE s_old.status IN ('invalidated', 'superseded')
ORDER BY s_old.closed_at DESC;
