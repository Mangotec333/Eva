-- ============================================================
-- EVA DEAL INTELLIGENCE DATABASE
-- SQLite + FTS5 + sqlite-vec
-- Version 1.0 | June 2026
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- CORE DEALS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS deals (
    -- Identity
    id              TEXT PRIMARY KEY,          -- slug: "batch-ai", "mission-villa"
    name            TEXT NOT NULL UNIQUE,
    alias           TEXT,                      -- alternate names, comma-separated
    platform        TEXT,                      -- "Empire Flippers", "Flippa", "Quietlight", "Direct"

    -- Classification
    asset_type      TEXT,                      -- "saas", "content-site", "rcfe", "ecomm", "hr-data"
    market          TEXT,                      -- geography or niche
    tier            INTEGER DEFAULT 2,         -- 1=primary, 2=watch, 3=radar, 0=dead
    status          TEXT DEFAULT 'active',     -- "active", "loi-sent", "in-dd", "closed", "dead", "watch"

    -- Deal Terms
    asking_price    REAL,
    purchase_price  REAL,                      -- negotiated / final
    multiple        REAL,                      -- price/annual-profit
    down_payment    REAL,
    loan_amount     REAL,
    loan_rate       REAL,                      -- decimal: 0.10 = 10%
    loan_term_yrs   INTEGER,
    loan_payment_mo REAL,                      -- monthly debt service

    -- Financials (Monthly)
    gross_revenue_mo    REAL,
    operating_exp_mo    REAL,
    ebitda_mo           REAL,
    total_debt_mo       REAL,                  -- all debt service combined
    noi_mo              REAL,                  -- net operating income/month
    noi_annual          REAL,                  -- = noi_mo * 12
    noi_peak_mo         REAL,                  -- best historical monthly NOI (for SaaS)
    mrr                 REAL,                  -- current MRR (SaaS only)
    mrr_peak            REAL,                  -- peak MRR (SaaS only)

    -- Cap Rate (RCFE/Real Estate)
    cap_rate        REAL,                      -- decimal: 0.058 = 5.8%

    -- Risk
    risk_score      REAL DEFAULT 5.0,          -- 0.0 (safe) to 10.0 (dangerous)
    risk_flags      TEXT DEFAULT '[]',         -- JSON array of strings

    -- Deal Timeline
    loi_date        TEXT,                      -- ISO 8601
    dd_days         INTEGER,                   -- due diligence window
    close_date      TEXT,
    exclusivity_days INTEGER,
    holdback_pct    REAL,                      -- decimal: 0.30 = 30% holdback
    holdback_days   INTEGER,                   -- days until holdback released
    transition_days INTEGER,
    transition_hrs_wk REAL,

    -- Contacts
    seller_name     TEXT,
    seller_email    TEXT,
    broker_name     TEXT,
    broker_platform TEXT,

    -- Eva Metadata
    eva_score       REAL,                      -- Eva composite deal score 0-100
    eva_notes       TEXT,                      -- Eva's running notes on deal
    watchlist_added TEXT,                      -- ISO 8601 timestamp
    last_updated    TEXT DEFAULT (datetime('now')),

    -- Source tracking
    source_url      TEXT,
    source_doc_id   TEXT,                      -- Google Drive file ID

    -- Overflow
    extra_fields    TEXT DEFAULT '{}'          -- JSON blob for non-standard fields
);

-- ============================================================
-- FTS5 VIRTUAL TABLE (keyword search — zero-cost, built-in)
-- ============================================================
CREATE VIRTUAL TABLE IF NOT EXISTS deals_fts USING fts5(
    name,
    alias,
    platform,
    market,
    asset_type,
    status,
    eva_notes,
    risk_flags,
    content='deals',
    content_rowid='rowid'
);

-- Auto-sync triggers
CREATE TRIGGER IF NOT EXISTS deals_fts_insert AFTER INSERT ON deals BEGIN
    INSERT INTO deals_fts(rowid, name, alias, platform, market, asset_type, status, eva_notes, risk_flags)
    VALUES (new.rowid, new.name, new.alias, new.platform, new.market,
            new.asset_type, new.status, new.eva_notes, new.risk_flags);
END;

CREATE TRIGGER IF NOT EXISTS deals_fts_update AFTER UPDATE ON deals BEGIN
    DELETE FROM deals_fts WHERE rowid = old.rowid;
    INSERT INTO deals_fts(rowid, name, alias, platform, market, asset_type, status, eva_notes, risk_flags)
    VALUES (new.rowid, new.name, new.alias, new.platform, new.market,
            new.asset_type, new.status, new.eva_notes, new.risk_flags);
END;

CREATE TRIGGER IF NOT EXISTS deals_fts_delete AFTER DELETE ON deals BEGIN
    DELETE FROM deals_fts WHERE rowid = old.rowid;
END;

-- Auto-update last_updated timestamp
CREATE TRIGGER IF NOT EXISTS deals_updated AFTER UPDATE ON deals BEGIN
    UPDATE deals SET last_updated = datetime('now') WHERE id = new.id;
END;

-- ============================================================
-- INDEXES (structured query performance)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_deals_tier       ON deals(tier);
CREATE INDEX IF NOT EXISTS idx_deals_status     ON deals(status);
CREATE INDEX IF NOT EXISTS idx_deals_asset_type ON deals(asset_type);
CREATE INDEX IF NOT EXISTS idx_deals_market     ON deals(market);
CREATE INDEX IF NOT EXISTS idx_deals_multiple   ON deals(multiple);
CREATE INDEX IF NOT EXISTS idx_deals_cap_rate   ON deals(cap_rate);
CREATE INDEX IF NOT EXISTS idx_deals_noi_mo     ON deals(noi_mo);
CREATE INDEX IF NOT EXISTS idx_deals_risk_score ON deals(risk_score);
CREATE INDEX IF NOT EXISTS idx_deals_mrr        ON deals(mrr);

-- ============================================================
-- DEAL EVENTS LOG (price cuts, status changes, notes)
-- ============================================================
CREATE TABLE IF NOT EXISTS deal_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id     TEXT NOT NULL REFERENCES deals(id),
    event_type  TEXT NOT NULL,   -- "price_cut", "status_change", "note", "loi_sent", "dd_started"
    old_value   TEXT,
    new_value   TEXT,
    note        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_deal_id  ON deal_events(deal_id);
CREATE INDEX IF NOT EXISTS idx_events_type     ON deal_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created  ON deal_events(created_at);
