-- ─────────────────────────────────────────────
--  EVA PostgreSQL Schema — Migration 02
--  enrolled_contacts: the "don't ask again" dedup ledger for cold outreach
--  Auto-runs on container boot after 01_schema.sql
-- ─────────────────────────────────────────────

-- One row per contact that has ever been enrolled into a GHL outreach
-- sequence. The Apollo→GHL pipeline checks this table by email BEFORE adding
-- any contact; a hit means "already enrolled — skip". GHL's own
-- upsert-by-email is the second dedup layer behind this one.
CREATE TABLE IF NOT EXISTS enrolled_contacts (
    email           TEXT UNIQUE,                    -- dedup key (lower-cased by writer)
    source          TEXT,                           -- e.g. 'apollo-pe-ma'
    ghl_contact_id  TEXT,                           -- GHL contact id from upsert
    enrolled_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enrolled_email  ON enrolled_contacts(email);
CREATE INDEX IF NOT EXISTS idx_enrolled_source ON enrolled_contacts(source);
