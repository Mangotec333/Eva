-- ─────────────────────────────────────────────
--  EVA PostgreSQL Schema
--  Layer 1: Operational Store
--  Auto-runs on first container boot
-- ─────────────────────────────────────────────

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── DEALS ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS deals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          TEXT NOT NULL,                  -- 'empire_flippers' | 'flippa' | 'vestedbb' | 'manual'
    title           TEXT,
    url             TEXT,
    asking_price    NUMERIC,
    monthly_revenue NUMERIC,
    monthly_profit  NUMERIC,
    niche           TEXT,
    status          TEXT DEFAULT 'new',             -- 'new' | 'reviewing' | 'passed' | 'active'
    notes           JSONB DEFAULT '{}',
    raw_data        JSONB DEFAULT '{}',
    embedding       vector(1536),                   -- synced to Qdrant Layer 2
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── CONTACTS ───────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT,
    email           TEXT,
    phone           TEXT,
    company         TEXT,
    role            TEXT,
    source          TEXT,                           -- 'linkedin' | 'email' | 'manual'
    deal_id         UUID REFERENCES deals(id),
    notes           JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── CALENDAR EVENTS ────────────────────────────
CREATE TABLE IF NOT EXISTS calendar_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gcal_id         TEXT UNIQUE,
    title           TEXT,
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    attendees       JSONB DEFAULT '[]',
    zoom_link       TEXT,
    deal_id         UUID REFERENCES deals(id),
    is_high_stakes  BOOLEAN DEFAULT FALSE,          -- triggers nap protocol flag
    notes           JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── EMAIL SIGNALS ──────────────────────────────
CREATE TABLE IF NOT EXISTS email_signals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gmail_id        TEXT UNIQUE,
    subject         TEXT,
    sender          TEXT,
    received_at     TIMESTAMPTZ,
    signal_type     TEXT,                           -- 'deal_flow' | 'meeting' | 'follow_up' | 'newsletter'
    deal_id         UUID REFERENCES deals(id),
    summary         TEXT,
    raw_snippet     TEXT,
    embedding       vector(1536),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── ANGEL LOGS ─────────────────────────────────
CREATE TABLE IF NOT EXISTS angel_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    angel_id        TEXT NOT NULL,                  -- 'sentinel' | 'yaksha' | 'picker' | 'triage' etc
    run_at          TIMESTAMPTZ DEFAULT NOW(),
    status          TEXT,                           -- 'success' | 'error' | 'skipped'
    output          JSONB DEFAULT '{}',
    duration_ms     INTEGER,
    error           TEXT
);

-- ── NARRATIONS (Triage inputs) ─────────────────
CREATE TABLE IF NOT EXISTS narrations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_text        TEXT NOT NULL,
    routed_to       TEXT,                           -- 'deals' | 'parking_lot' | 'action_queue' | 'signature_talk'
    priority        TEXT DEFAULT 'normal',          -- 'critical' | 'high' | 'normal' | 'low'
    status          TEXT DEFAULT 'pending',         -- 'pending' | 'actioned' | 'tabled'
    embedding       vector(1536),                   -- synced to Qdrant for semantic recall
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── MORNING BRIEFS ─────────────────────────────
CREATE TABLE IF NOT EXISTS morning_briefs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brief_date      DATE UNIQUE,
    calendar_json   JSONB DEFAULT '[]',
    deals_json      JSONB DEFAULT '[]',
    actions_json    JSONB DEFAULT '[]',
    nap_blocks      JSONB DEFAULT '[]',             -- pre-call nap windows
    exercise_block  JSONB DEFAULT '{}',
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── SHOPIFY METRICS ────────────────────────────
CREATE TABLE IF NOT EXISTS shopify_metrics (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recorded_at     TIMESTAMPTZ DEFAULT NOW(),
    store           TEXT DEFAULT 'jack',
    orders_count    INTEGER DEFAULT 0,
    revenue         NUMERIC DEFAULT 0,
    top_products    JSONB DEFAULT '[]',
    alerts          JSONB DEFAULT '[]'
);

-- ── INDEXES ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_deals_status       ON deals(status);
CREATE INDEX IF NOT EXISTS idx_deals_source       ON deals(source);
CREATE INDEX IF NOT EXISTS idx_deals_created      ON deals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_deal      ON contacts(deal_id);
CREATE INDEX IF NOT EXISTS idx_calendar_start     ON calendar_events(start_time);
CREATE INDEX IF NOT EXISTS idx_calendar_stakes    ON calendar_events(is_high_stakes);
CREATE INDEX IF NOT EXISTS idx_email_type         ON email_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_angel_logs_id      ON angel_logs(angel_id, run_at DESC);
CREATE INDEX IF NOT EXISTS idx_narrations_status  ON narrations(status, priority);
CREATE INDEX IF NOT EXISTS idx_brief_date         ON morning_briefs(brief_date DESC);

-- ── AUTO-UPDATE updated_at ──────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER deals_updated_at    BEFORE UPDATE ON deals    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER contacts_updated_at BEFORE UPDATE ON contacts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
