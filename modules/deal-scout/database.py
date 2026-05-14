"""
EVA Deal Scout — async SQLite layer via aiosqlite.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

DB_PATH = "eva-deal-scout.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS deals (
    id                      TEXT PRIMARY KEY,
    source                  TEXT NOT NULL DEFAULT 'manual',
    listing_id              TEXT NOT NULL DEFAULT '',
    url                     TEXT NOT NULL DEFAULT '',
    name                    TEXT NOT NULL,
    category                TEXT NOT NULL DEFAULT 'SaaS',
    monthly_net             REAL NOT NULL DEFAULT 0,
    annual_multiple         REAL NOT NULL DEFAULT 0,
    asking_price            REAL NOT NULL DEFAULT 0,
    age_years               REAL NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'tracking',
    notes                   TEXT NOT NULL DEFAULT '',

    cashflow_score          REAL NOT NULL DEFAULT 0,
    moat_score              REAL NOT NULL DEFAULT 0,
    ai_proof_score          REAL NOT NULL DEFAULT 0,
    value_add_score         REAL NOT NULL DEFAULT 0,
    buy_vs_build_score      REAL NOT NULL DEFAULT 0,
    risk_score              REAL NOT NULL DEFAULT 0,
    overall_score           REAL NOT NULL DEFAULT 0,

    down_payment            REAL NOT NULL DEFAULT 0,
    seller_finance_amount   REAL NOT NULL DEFAULT 0,
    monthly_debt_service    REAL NOT NULL DEFAULT 0,
    net_monthly_cashflow    REAL NOT NULL DEFAULT 0,
    heloc_used              REAL NOT NULL DEFAULT 0,
    heloc_interest_monthly  REAL NOT NULL DEFAULT 0,
    net_after_heloc         REAL NOT NULL DEFAULT 0,

    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
)
"""

# ---------------------------------------------------------------------------
# Seed data (5 deals from the EVA session)
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SEED_DEALS = [
    {
        "source": "empire_flippers",
        "listing_id": "87872",
        "url": "https://empireflippers.com/listing/87872",
        "name": "Digital Media Services",
        "category": "Services",
        "monthly_net": 11478.0,
        "annual_multiple": 1.9,
        "asking_price": 261438.96,   # 11478 * 12 * 1.9
        "age_years": 6.0,
        "status": "pursuing",
        "notes": "EF #87872 — digital media services business",
        "ai_proof_score": 84.0,
        "value_add_score": 90.0,
    },
    {
        "source": "flippa",
        "listing_id": "12166327",
        "url": "https://flippa.com/listing/12166327",
        "name": "Education Tutoring Platform",
        "category": "Education",
        "monthly_net": 7195.0,
        "annual_multiple": 1.8,
        "asking_price": 155412.0,    # 7195 * 12 * 1.8
        "age_years": 6.0,
        "status": "pursuing",
        "notes": "Flippa #12166327 — education / tutoring marketplace",
        "ai_proof_score": 82.0,
        "value_add_score": 80.0,
    },
    {
        "source": "flippa",
        "listing_id": "12032980",
        "url": "https://flippa.com/listing/12032980",
        "name": "Real Estate Comparison Site",
        "category": "Content",
        "monthly_net": 13500.0,
        "annual_multiple": 1.6,
        "asking_price": 259200.0,    # 13500 * 12 * 1.6
        "age_years": 5.0,
        "status": "tracking",
        "notes": "Flippa #12032980 — real estate comparison / content site",
        "ai_proof_score": 68.0,
        "value_add_score": 80.0,
    },
    {
        "source": "flippa",
        "listing_id": "12278661",
        "url": "https://flippa.com/listing/12278661",
        "name": "WordPress Plugin SaaS",
        "category": "SaaS",
        "monthly_net": 7581.0,
        "annual_multiple": 3.0,
        "asking_price": 272916.0,    # 7581 * 12 * 3.0
        "age_years": 13.0,
        "status": "tracking",
        "notes": "Flippa #12278661 — long-running WordPress plugin business",
        "ai_proof_score": 61.0,
        "value_add_score": 60.0,
    },
    {
        "source": "empire_flippers",
        "listing_id": "89115",
        "url": "https://empireflippers.com/listing/89115",
        "name": "Digital Products Art Business",
        "category": "Digital Products",
        "monthly_net": 11338.0,
        "annual_multiple": 1.9,
        "asking_price": 258106.8,    # 11338 * 12 * 1.9
        "age_years": 2.0,
        "status": "passed",
        "notes": "EF #89115 — digital art product downloads; short track record",
        "ai_proof_score": 38.0,
        "value_add_score": 70.0,
    },
]

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

class _DBContext:
    """Async context manager that opens/closes an aiosqlite connection."""

    def __init__(self, path: str):
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def __aenter__(self) -> aiosqlite.Connection:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def __aexit__(self, *args):
        if self._conn:
            await self._conn.close()


def get_db() -> "_DBContext":
    """Return an async context manager yielding an aiosqlite.Connection.

    Usage::

        async with db.get_db() as conn:
            rows = await db.fetch_all_deals(conn)
    """
    return _DBContext(DB_PATH)


async def init_db() -> None:
    """Create the schema and seed if empty."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(CREATE_TABLE_SQL)
        await db.commit()

        # Only seed when table is empty
        cursor = await db.execute("SELECT COUNT(*) FROM deals")
        row = await cursor.fetchone()
        count = row[0]
        if count == 0:
            await _seed(db)


async def _seed(db: aiosqlite.Connection) -> None:
    """Insert the 5 pre-seeded EVA deals and run the scorer on each."""
    # Import here to avoid circular import at module load time
    from analyzer import analyze_deal
    from models import Deal

    ts = _now()
    for seed in SEED_DEALS:
        deal_id = str(uuid.uuid4())
        # Build a partial Deal so the scorer can populate financials
        partial = Deal(
            id=deal_id,
            source=seed["source"],
            listing_id=seed["listing_id"],
            url=seed["url"],
            name=seed["name"],
            category=seed["category"],
            monthly_net=seed["monthly_net"],
            annual_multiple=seed["annual_multiple"],
            asking_price=seed["asking_price"],
            age_years=seed["age_years"],
            status=seed["status"],
            notes=seed["notes"],
            ai_proof_score=seed.get("ai_proof_score", 0.0),
            value_add_score=seed.get("value_add_score", 70.0),
            created_at=ts,
            updated_at=ts,
        )
        scored = analyze_deal(partial)
        await _insert_deal(db, scored)

    await db.commit()


async def _insert_deal(db: aiosqlite.Connection, deal: "Deal") -> None:
    await db.execute(
        """
        INSERT INTO deals VALUES (
            :id, :source, :listing_id, :url, :name, :category,
            :monthly_net, :annual_multiple, :asking_price, :age_years,
            :status, :notes,
            :cashflow_score, :moat_score, :ai_proof_score,
            :value_add_score, :buy_vs_build_score, :risk_score, :overall_score,
            :down_payment, :seller_finance_amount, :monthly_debt_service,
            :net_monthly_cashflow, :heloc_used, :heloc_interest_monthly,
            :net_after_heloc, :created_at, :updated_at
        )
        """,
        deal.model_dump(),
    )


async def fetch_all_deals(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM deals ORDER BY overall_score DESC"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def fetch_deal(db: aiosqlite.Connection, deal_id: str) -> Optional[dict]:
    cursor = await db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def insert_deal(db: aiosqlite.Connection, deal: "Deal") -> None:
    await _insert_deal(db, deal)
    await db.commit()


async def update_deal(db: aiosqlite.Connection, deal: "Deal") -> None:
    d = deal.model_dump()
    await db.execute(
        """
        UPDATE deals SET
            source=:source, listing_id=:listing_id, url=:url, name=:name,
            category=:category, monthly_net=:monthly_net,
            annual_multiple=:annual_multiple, asking_price=:asking_price,
            age_years=:age_years, status=:status, notes=:notes,
            cashflow_score=:cashflow_score, moat_score=:moat_score,
            ai_proof_score=:ai_proof_score, value_add_score=:value_add_score,
            buy_vs_build_score=:buy_vs_build_score, risk_score=:risk_score,
            overall_score=:overall_score, down_payment=:down_payment,
            seller_finance_amount=:seller_finance_amount,
            monthly_debt_service=:monthly_debt_service,
            net_monthly_cashflow=:net_monthly_cashflow,
            heloc_used=:heloc_used, heloc_interest_monthly=:heloc_interest_monthly,
            net_after_heloc=:net_after_heloc, updated_at=:updated_at
        WHERE id=:id
        """,
        d,
    )
    await db.commit()


async def delete_deal(db: aiosqlite.Connection, deal_id: str) -> bool:
    cursor = await db.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
    await db.commit()
    return cursor.rowcount > 0


async def fetch_shortlist(db: aiosqlite.Connection, threshold: float = 7.5) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM deals WHERE overall_score >= ? ORDER BY overall_score DESC",
        (threshold,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
