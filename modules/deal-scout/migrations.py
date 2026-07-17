"""
EVA Deal Scout — schema migrations for the unified DB-backed pipeline.

Migrations are ordered, idempotent SQL scripts applied against a SQLite
connection.  A ``schema_migrations`` bookkeeping table records which versions
have been applied so ``run_migrations`` can be called repeatedly and safely.

The migration list is intentionally declarative so a future Mongo-backed
``DealStore`` can ignore it entirely and manage its own collections.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable

# ---------------------------------------------------------------------------
# Individual migrations — (version, name, sql)
# ---------------------------------------------------------------------------

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "create_source_runs",
        """
        CREATE TABLE IF NOT EXISTS source_runs (
            id              TEXT PRIMARY KEY,
            source          TEXT NOT NULL,
            adapter         TEXT NOT NULL DEFAULT '',
            mode            TEXT NOT NULL DEFAULT 'source',
            status          TEXT NOT NULL DEFAULT 'running',
            deals_found     INTEGER NOT NULL DEFAULT 0,
            deals_new       INTEGER NOT NULL DEFAULT 0,
            deals_updated   INTEGER NOT NULL DEFAULT 0,
            snapshots_added INTEGER NOT NULL DEFAULT 0,
            error           TEXT NOT NULL DEFAULT '',
            started_at      TEXT NOT NULL DEFAULT '',
            finished_at     TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT '',
            updated_at      TEXT NOT NULL DEFAULT ''
        )
        """,
    ),
    (
        2,
        "create_raw_deals",
        """
        CREATE TABLE IF NOT EXISTS raw_deals (
            id                       TEXT PRIMARY KEY,
            source_run_id            TEXT NOT NULL DEFAULT '',
            source                   TEXT NOT NULL,
            listing_id               TEXT NOT NULL DEFAULT '',
            url                      TEXT NOT NULL DEFAULT '',
            dedupe_key               TEXT NOT NULL DEFAULT '',
            name                     TEXT NOT NULL DEFAULT '',
            category                 TEXT NOT NULL DEFAULT 'SaaS',
            monthly_net              REAL NOT NULL DEFAULT 0,
            annual_multiple          REAL NOT NULL DEFAULT 0,
            asking_price             REAL NOT NULL DEFAULT 0,
            age_years                REAL NOT NULL DEFAULT 0,
            currency                 TEXT NOT NULL DEFAULT 'USD',
            registration_country     TEXT NOT NULL DEFAULT '',
            primary_customer_market  TEXT NOT NULL DEFAULT '',
            seller_location          TEXT NOT NULL DEFAULT '',
            trust_level              TEXT NOT NULL DEFAULT 'low',
            is_closed                INTEGER NOT NULL DEFAULT 0,
            market_status            TEXT NOT NULL DEFAULT 'available',
            sold_price               REAL NOT NULL DEFAULT 0,
            sold_at                  TEXT NOT NULL DEFAULT '',
            owner_hours_per_week     REAL NOT NULL DEFAULT 0,
            notes                    TEXT NOT NULL DEFAULT '',
            raw_json                 TEXT NOT NULL DEFAULT '{}',
            sourced_at               TEXT NOT NULL DEFAULT '',
            created_at               TEXT NOT NULL DEFAULT '',
            updated_at               TEXT NOT NULL DEFAULT ''
        )
        """,
    ),
    (
        3,
        "raw_deals_dedupe_index",
        # Dedupe by (source, dedupe_key) where dedupe_key = listing_id or url.
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_deals_source_key "
        "ON raw_deals (source, dedupe_key)",
    ),
    (
        4,
        "create_deal_snapshots",
        """
        CREATE TABLE IF NOT EXISTS deal_snapshots (
            id             TEXT PRIMARY KEY,
            raw_deal_id    TEXT NOT NULL,
            source_run_id  TEXT NOT NULL DEFAULT '',
            market_status  TEXT NOT NULL DEFAULT 'available',
            asking_price   REAL NOT NULL DEFAULT 0,
            monthly_net    REAL NOT NULL DEFAULT 0,
            observed_at    TEXT NOT NULL DEFAULT '',
            created_at     TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (raw_deal_id) REFERENCES raw_deals(id)
        )
        """,
    ),
    (
        5,
        "create_scored_deals",
        """
        CREATE TABLE IF NOT EXISTS scored_deals (
            id                         TEXT PRIMARY KEY,
            raw_deal_id                TEXT NOT NULL,
            source                     TEXT NOT NULL DEFAULT '',
            listing_id                 TEXT NOT NULL DEFAULT '',
            us_eligible                INTEGER NOT NULL DEFAULT 0,
            trust_level                TEXT NOT NULL DEFAULT 'low',
            gate_reason                TEXT NOT NULL DEFAULT '',
            cashflow_score             REAL NOT NULL DEFAULT 0,
            moat_score                 REAL NOT NULL DEFAULT 0,
            ai_proof_score             REAL NOT NULL DEFAULT 0,
            value_add_score            REAL NOT NULL DEFAULT 0,
            buy_vs_build_score         REAL NOT NULL DEFAULT 0,
            risk_score                 REAL NOT NULL DEFAULT 0,
            mitigation_score           REAL NOT NULL DEFAULT 0,
            competitor_analysis_score  REAL NOT NULL DEFAULT 0,
            company_life_score         REAL NOT NULL DEFAULT 0,
            owner_neglect_score        REAL NOT NULL DEFAULT 0,
            adobe_platform_risk_score  REAL NOT NULL DEFAULT 0,
            overall_score              REAL NOT NULL DEFAULT 0,
            score_json                 TEXT NOT NULL DEFAULT '{}',
            scored_at                  TEXT NOT NULL DEFAULT '',
            created_at                 TEXT NOT NULL DEFAULT '',
            updated_at                 TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (raw_deal_id) REFERENCES raw_deals(id)
        )
        """,
    ),
    (
        6,
        "scored_deals_unique_raw",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_scored_deals_raw "
        "ON scored_deals (raw_deal_id)",
    ),
    (
        7,
        "create_trend_reports",
        """
        CREATE TABLE IF NOT EXISTS trend_reports (
            id            TEXT PRIMARY KEY,
            title         TEXT NOT NULL DEFAULT 'Deal Trend Report',
            report_md     TEXT NOT NULL DEFAULT '',
            stats_json    TEXT NOT NULL DEFAULT '{}',
            generated_at  TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT ''
        )
        """,
    ),
    (
        8,
        "raw_deals_score_and_gate_audit",
        # incoming_score preserves any pre-computed score from the source; the
        # gate audit columns record the SCORE-stage decision on every open deal.
        """
        ALTER TABLE raw_deals ADD COLUMN incoming_score REAL NOT NULL DEFAULT 0;
        ALTER TABLE raw_deals ADD COLUMN gate_status TEXT NOT NULL DEFAULT 'pending';
        ALTER TABLE raw_deals ADD COLUMN us_eligible INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE raw_deals ADD COLUMN trust_high INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE raw_deals ADD COLUMN skip_reason TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        9,
        "scored_deals_gate_audit",
        """
        ALTER TABLE scored_deals ADD COLUMN trust_high INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE scored_deals ADD COLUMN skip_reason TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        10,
        "scored_deals_buy_vs_build",
        # Buy-vs-Build assessment persisted on every scored deal; moat_build_years
        # is the deal-killer for the build path.
        """
        ALTER TABLE scored_deals ADD COLUMN build_feasibility TEXT NOT NULL DEFAULT '';
        ALTER TABLE scored_deals ADD COLUMN build_time_estimate TEXT NOT NULL DEFAULT '';
        ALTER TABLE scored_deals ADD COLUMN moat_build_years REAL NOT NULL DEFAULT 0;
        ALTER TABLE scored_deals ADD COLUMN buy_vs_build_recommendation TEXT NOT NULL DEFAULT '';
        ALTER TABLE scored_deals ADD COLUMN buy_vs_build_rationale TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        11,
        "create_competitor_intelligence",
        # Normalized competitor entities (one row per real-world company, deduped
        # by lowercased name) plus a deal_competitors join so the same competitor
        # (e.g. "CrowdStrike") can link to many deals.  moat_comparison lives on
        # the link because it is deal-specific: how THIS deal stacks up vs the
        # competitor.  competitor-level facts (what_they_do, pricing) compound on
        # the shared entity.
        """
        CREATE TABLE IF NOT EXISTS competitors (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            name_key      TEXT NOT NULL DEFAULT '',
            what_they_do  TEXT NOT NULL DEFAULT '',
            pricing_model TEXT NOT NULL DEFAULT '',
            url           TEXT NOT NULL DEFAULT '',
            category      TEXT NOT NULL DEFAULT '',
            source_url    TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT '',
            updated_at    TEXT NOT NULL DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_competitors_name_key
            ON competitors (name_key);
        CREATE TABLE IF NOT EXISTS deal_competitors (
            id              TEXT PRIMARY KEY,
            deal_id         TEXT NOT NULL,
            competitor_id   TEXT NOT NULL,
            moat_comparison TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT '',
            updated_at      TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (deal_id) REFERENCES raw_deals(id),
            FOREIGN KEY (competitor_id) REFERENCES competitors(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_deal_competitors_pair
            ON deal_competitors (deal_id, competitor_id);
        """,
    ),
    (
        12,
        "create_case_studies",
        # 4-lens deal case studies — Eva's compounding acquisition intelligence.
        # Captures BOTH a deal snapshot AND the 4-lens analysis (both JSON blobs)
        # so a single deal becomes reusable pattern/formula/moat intel.  deal_id
        # is NULLABLE for out-of-box studies (juggernauts, build-vs-buy refs) Eva
        # studies without sourcing them.  Upserted by source_url (unique).
        """
        CREATE TABLE IF NOT EXISTS case_studies (
            id                TEXT PRIMARY KEY,
            source_url        TEXT NOT NULL UNIQUE,
            deal_type         TEXT NOT NULL DEFAULT 'within_box',
            title             TEXT NOT NULL DEFAULT '',
            deal_id           TEXT,
            snapshot          TEXT NOT NULL DEFAULT '{}',
            analysis          TEXT NOT NULL DEFAULT '{}',
            pattern_tags      TEXT NOT NULL DEFAULT '[]',
            formula_insight   TEXT NOT NULL DEFAULT '',
            created_at        TEXT NOT NULL DEFAULT '',
            updated_at        TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (deal_id) REFERENCES raw_deals(id)
        );
        """,
    ),
    (
        13,
        "create_deal_box_evaluations",
        # Post-scoring "deal box" hard-criteria verdicts.  One row per scored
        # deal (upserted by deal_id): the financing breakdown at the current
        # run-rate plus the free-cash-flow / DSCR / trend pass-fail verdict.
        # box_reason and config_snapshot are JSON TEXT blobs so the exact
        # thresholds behind a verdict stay auditable even as the config changes.
        """
        CREATE TABLE IF NOT EXISTS deal_box_evaluations (
            id                TEXT PRIMARY KEY,
            deal_id           TEXT NOT NULL,
            asking            REAL NOT NULL DEFAULT 0,
            monthly_net_used  REAL NOT NULL DEFAULT 0,
            seller_note_pmt   REAL NOT NULL DEFAULT 0,
            heloc_pmt         REAL NOT NULL DEFAULT 0,
            total_debt        REAL NOT NULL DEFAULT 0,
            free_cash_flow    REAL NOT NULL DEFAULT 0,
            dscr              REAL NOT NULL DEFAULT 0,
            trend_pass        INTEGER NOT NULL DEFAULT 0,
            box_pass          INTEGER NOT NULL DEFAULT 0,
            box_reason        TEXT NOT NULL DEFAULT '[]',
            config_snapshot   TEXT NOT NULL DEFAULT '{}',
            created_at        TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (deal_id) REFERENCES raw_deals(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_deal_box_evaluations_deal
            ON deal_box_evaluations (deal_id);
        """,
    ),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TEXT NOT NULL
        )
        """
    )
    cur = conn.execute("SELECT version FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def run_migrations(conn: sqlite3.Connection, log: Callable[[str], None] | None = None) -> list[int]:
    """Apply every pending migration in order.  Returns versions applied."""
    applied = _applied_versions(conn)
    newly: list[int] = []
    for version, name, sql in MIGRATIONS:
        if version in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, _now()),
        )
        newly.append(version)
        if log:
            log(f"applied migration {version}: {name}")
    conn.commit()
    return newly
