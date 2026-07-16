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
