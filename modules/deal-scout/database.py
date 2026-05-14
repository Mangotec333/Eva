"""
EVA Deal Scout — async SQLite layer via aiosqlite (v2).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

DB_PATH = "eva-deal-scout.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

CREATE_DEALS_SQL = """
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
    notes                   TEXT NOT NULL DEFAULT '',

    -- Stage pipeline
    stage                   TEXT NOT NULL DEFAULT 'tracking',

    -- Archive
    is_archived             INTEGER NOT NULL DEFAULT 0,
    archive_reason          TEXT NOT NULL DEFAULT '',
    archived_at             TEXT NOT NULL DEFAULT '',

    -- Buy vs Build
    buy_vs_build_decision   TEXT NOT NULL DEFAULT 'buy',
    buy_vs_build_reason     TEXT NOT NULL DEFAULT '',

    -- Availability
    market_status           TEXT NOT NULL DEFAULT 'available',
    listing_price_original  REAL NOT NULL DEFAULT 0,

    -- Scores
    cashflow_score          REAL NOT NULL DEFAULT 0,
    moat_score              REAL NOT NULL DEFAULT 0,
    ai_proof_score          REAL NOT NULL DEFAULT 0,
    value_add_score         REAL NOT NULL DEFAULT 0,
    buy_vs_build_score      REAL NOT NULL DEFAULT 0,
    risk_score              REAL NOT NULL DEFAULT 0,
    overall_score           REAL NOT NULL DEFAULT 0,

    -- Financial analysis
    down_payment            REAL NOT NULL DEFAULT 0,
    seller_finance_amount   REAL NOT NULL DEFAULT 0,
    monthly_debt_service    REAL NOT NULL DEFAULT 0,
    net_monthly_cashflow    REAL NOT NULL DEFAULT 0,
    heloc_used              REAL NOT NULL DEFAULT 0,
    heloc_interest_monthly  REAL NOT NULL DEFAULT 0,
    net_after_heloc         REAL NOT NULL DEFAULT 0,

    -- Timestamps
    discovered_at           TEXT NOT NULL DEFAULT '',
    stage_changed_at        TEXT NOT NULL DEFAULT '',
    closed_at               TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
)
"""

CREATE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS deal_history (
    id          TEXT PRIMARY KEY,
    deal_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    from_value  TEXT NOT NULL DEFAULT '',
    to_value    TEXT NOT NULL DEFAULT '',
    field_name  TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (deal_id) REFERENCES deals(id)
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
        "name": "EF #87872 Digital Media Services",
        "category": "Services",
        "monthly_net": 11478.0,
        "annual_multiple": 1.9,
        "asking_price": 261414.0,
        "age_years": 6.0,
        "stage": "in_progress",
        "market_status": "available",
        "buy_vs_build_decision": "buy",
        "buy_vs_build_score": 8.0,
        "buy_vs_build_reason": "6yr client relationships + delivery reputation impossible to replicate quickly. Buying the operational playbook.",
        "ai_proof_score": 84.0,
        "value_add_score": 90.0,
        "overall_score": 7.78,
        "notes": "EF #87872 — digital media services business",
    },
    {
        "source": "flippa",
        "listing_id": "12166327",
        "url": "https://flippa.com/listing/12166327",
        "name": "Flippa #12166327 Education Tutoring",
        "category": "Education",
        "monthly_net": 7195.0,
        "annual_multiple": 1.8,
        "asking_price": 155412.0,
        "age_years": 6.0,
        "stage": "in_progress",
        "market_status": "available",
        "buy_vs_build_decision": "buy",
        "buy_vs_build_score": 9.0,
        "buy_vs_build_reason": "6yr EdTech trust, student/tutor network, USA SEO authority. Takes years to replicate. $31K down leaves HELOC headroom.",
        "ai_proof_score": 82.0,
        "value_add_score": 80.0,
        "overall_score": 6.77,
        "notes": "Flippa #12166327 — education / tutoring marketplace",
    },
    {
        "source": "flippa",
        "listing_id": "12032980",
        "url": "https://flippa.com/listing/12032980",
        "name": "Flippa #12032980 Real Estate Comparison",
        "category": "Content",
        "monthly_net": 13500.0,
        "annual_multiple": 1.6,
        "asking_price": 259200.0,
        "age_years": 5.0,
        "stage": "tracking",
        "market_status": "available",
        "buy_vs_build_decision": "buy",
        "buy_vs_build_score": 9.0,
        "buy_vs_build_reason": "France/EUR RE SEO authority takes 3-5yr to build. Highest cash flow but no relationship moat.",
        "ai_proof_score": 68.0,
        "value_add_score": 80.0,
        "overall_score": 7.15,
        "notes": "Flippa #12032980 — real estate comparison / content site",
    },
    {
        "source": "flippa",
        "listing_id": "12278661",
        "url": "https://flippa.com/listing/12278661",
        "name": "Flippa #12278661 WordPress Plugin 13yr",
        "category": "SaaS",
        "monthly_net": 7581.0,
        "annual_multiple": 3.0,
        "asking_price": 273916.0,
        "age_years": 13.0,
        "stage": "tracking",
        "market_status": "available",
        "buy_vs_build_decision": "buy",
        "buy_vs_build_score": 10.0,
        "buy_vs_build_reason": "Strongest moat on the list — 13yr WP listing + user base. But 3x multiple is expensive and WP market declining. Tracking only.",
        "ai_proof_score": 61.0,
        "value_add_score": 60.0,
        "overall_score": 6.94,
        "notes": "Flippa #12278661 — long-running WordPress plugin business",
    },
    {
        "source": "empire_flippers",
        "listing_id": "89115",
        "url": "https://empireflippers.com/listing/89115",
        "name": "EF #89115 Digital Products Art",
        "category": "Digital Products",
        "monthly_net": 11338.0,
        "annual_multiple": 1.9,
        "asking_price": 258547.0,
        "age_years": 2.0,
        "stage": "tracking",
        "market_status": "available",
        "is_archived": True,
        "archive_reason": "AI-proof score 38/100. AI-generated art commoditization will disrupt this within 12 months. Same AI wave that drove 42% growth will erase margins.",
        "buy_vs_build_decision": "build",
        "buy_vs_build_score": 3.0,
        "buy_vs_build_reason": "AI can replicate the product catalog in days. No relationship or authority moat. Better to build a better version with EVA than pay 1.9x for a fading asset.",
        "ai_proof_score": 38.0,
        "value_add_score": 70.0,
        "overall_score": 4.49,
        "notes": "EF #89115 — digital art product downloads; short track record",
    },
]


# ---------------------------------------------------------------------------
# DB context manager
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
    """Return an async context manager yielding an aiosqlite.Connection."""
    return _DBContext(DB_PATH)


# ---------------------------------------------------------------------------
# Init and seeding
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create the schema and seed if empty."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(CREATE_DEALS_SQL)
        await db.execute(CREATE_HISTORY_SQL)
        await db.commit()

        # Only seed when table is empty
        cursor = await db.execute("SELECT COUNT(*) FROM deals")
        row = await cursor.fetchone()
        count = row[0]
        if count == 0:
            await _seed(db)


async def _seed(db: aiosqlite.Connection) -> None:
    """Insert the 5 pre-seeded EVA deals with all v2 fields."""
    from analyzer import analyze_deal
    from models import Deal

    ts = _now()
    for seed in SEED_DEALS:
        deal_id = str(uuid.uuid4())
        is_archived = seed.get("is_archived", False)
        archived_at = ts if is_archived else ""
        stage = seed.get("stage", "tracking")

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
            listing_price_original=seed["asking_price"],
            age_years=seed["age_years"],
            stage=stage,
            notes=seed.get("notes", ""),
            is_archived=is_archived,
            archive_reason=seed.get("archive_reason", ""),
            archived_at=archived_at,
            buy_vs_build_decision=seed.get("buy_vs_build_decision", "buy"),
            buy_vs_build_score=seed.get("buy_vs_build_score", 0.0),
            buy_vs_build_reason=seed.get("buy_vs_build_reason", ""),
            market_status=seed.get("market_status", "available"),
            ai_proof_score=seed.get("ai_proof_score", 0.0),
            value_add_score=seed.get("value_add_score", 0.0),
            overall_score=seed.get("overall_score", 0.0),
            discovered_at=ts,
            stage_changed_at=ts if stage != "tracking" else "",
            created_at=ts,
            updated_at=ts,
        )

        # Run scorer — it will preserve buy_vs_build_score if >0 and overall_score if we
        # set it; since overall_score is set above we preserve it via a post-override
        scored = analyze_deal(partial)
        # Restore the manually-seeded overall_score
        if seed.get("overall_score", 0.0) > 0:
            scored.overall_score = seed["overall_score"]
        # Restore buy_vs_build_score (analyze_deal already preserves non-zero)
        await _insert_deal(db, scored)

        # Log "created" history event
        await _insert_history(db, {
            "deal_id": deal_id,
            "event_type": "created",
            "from_value": "",
            "to_value": "tracking",
            "field_name": "stage",
            "reason": "Initial seed",
            "note": "",
        })

        # Log "stage_change" if stage != "tracking"
        if stage != "tracking":
            await _insert_history(db, {
                "deal_id": deal_id,
                "event_type": "stage_change",
                "from_value": "tracking",
                "to_value": stage,
                "field_name": "stage",
                "reason": "Initial seed stage assignment",
                "note": "",
            })

        # Log "archive" event for deal #5
        if is_archived:
            await _insert_history(db, {
                "deal_id": deal_id,
                "event_type": "archive",
                "from_value": "",
                "to_value": "archived",
                "field_name": "is_archived",
                "reason": seed.get("archive_reason", ""),
                "note": "",
            })

    await db.commit()


async def _insert_history(db: aiosqlite.Connection, event: dict) -> None:
    await db.execute(
        """
        INSERT INTO deal_history (id, deal_id, event_type, from_value, to_value,
            field_name, reason, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            event["deal_id"],
            event["event_type"],
            event.get("from_value", ""),
            event.get("to_value", ""),
            event.get("field_name", ""),
            event.get("reason", ""),
            event.get("note", ""),
            _now(),
        ),
    )


async def _insert_deal(db: aiosqlite.Connection, deal: "Deal") -> None:
    d = deal.model_dump()
    # SQLite stores booleans as integers
    d["is_archived"] = 1 if d["is_archived"] else 0
    await db.execute(
        """
        INSERT INTO deals VALUES (
            :id, :source, :listing_id, :url, :name, :category,
            :monthly_net, :annual_multiple, :asking_price, :age_years,
            :notes,
            :stage, :is_archived, :archive_reason, :archived_at,
            :buy_vs_build_decision, :buy_vs_build_reason,
            :market_status, :listing_price_original,
            :cashflow_score, :moat_score, :ai_proof_score,
            :value_add_score, :buy_vs_build_score, :risk_score, :overall_score,
            :down_payment, :seller_finance_amount, :monthly_debt_service,
            :net_monthly_cashflow, :heloc_used, :heloc_interest_monthly,
            :net_after_heloc,
            :discovered_at, :stage_changed_at, :closed_at,
            :created_at, :updated_at
        )
        """,
        d,
    )


def _row_to_dict(row) -> dict:
    """Convert an aiosqlite.Row to a plain dict, normalising is_archived bool."""
    d = dict(row)
    d["is_archived"] = bool(d.get("is_archived", 0))
    return d


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

async def fetch_all_deals(
    db: aiosqlite.Connection,
    stage: Optional[str] = None,
    archived: Optional[str] = "false",  # "true" | "false" | "all"
    market_status: Optional[str] = None,
) -> list[dict]:
    clauses = []
    params = []

    if archived == "false":
        clauses.append("is_archived = 0")
    elif archived == "true":
        clauses.append("is_archived = 1")
    # "all" → no filter

    if stage:
        clauses.append("stage = ?")
        params.append(stage)

    if market_status:
        clauses.append("market_status = ?")
        params.append(market_status)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    cursor = await db.execute(
        f"SELECT * FROM deals {where} ORDER BY overall_score DESC",
        params,
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def fetch_deal(db: aiosqlite.Connection, deal_id: str) -> Optional[dict]:
    cursor = await db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def insert_deal(db: aiosqlite.Connection, deal: "Deal") -> None:
    await _insert_deal(db, deal)
    await db.commit()


async def insert_deal_with_history(
    db: aiosqlite.Connection,
    deal: "Deal",
    history_event: dict,
) -> None:
    await _insert_deal(db, deal)
    await _insert_history(db, history_event)
    await db.commit()


async def update_deal(db: aiosqlite.Connection, deal: "Deal") -> None:
    d = deal.model_dump()
    d["is_archived"] = 1 if d["is_archived"] else 0
    await db.execute(
        """
        UPDATE deals SET
            source=:source, listing_id=:listing_id, url=:url, name=:name,
            category=:category, monthly_net=:monthly_net,
            annual_multiple=:annual_multiple, asking_price=:asking_price,
            age_years=:age_years, notes=:notes,
            stage=:stage, is_archived=:is_archived,
            archive_reason=:archive_reason, archived_at=:archived_at,
            buy_vs_build_decision=:buy_vs_build_decision,
            buy_vs_build_reason=:buy_vs_build_reason,
            market_status=:market_status,
            listing_price_original=:listing_price_original,
            cashflow_score=:cashflow_score, moat_score=:moat_score,
            ai_proof_score=:ai_proof_score, value_add_score=:value_add_score,
            buy_vs_build_score=:buy_vs_build_score, risk_score=:risk_score,
            overall_score=:overall_score, down_payment=:down_payment,
            seller_finance_amount=:seller_finance_amount,
            monthly_debt_service=:monthly_debt_service,
            net_monthly_cashflow=:net_monthly_cashflow,
            heloc_used=:heloc_used, heloc_interest_monthly=:heloc_interest_monthly,
            net_after_heloc=:net_after_heloc,
            discovered_at=:discovered_at, stage_changed_at=:stage_changed_at,
            closed_at=:closed_at, updated_at=:updated_at
        WHERE id=:id
        """,
        d,
    )
    await db.commit()


async def update_deal_with_history(
    db: aiosqlite.Connection,
    deal: "Deal",
    history_event: dict,
) -> None:
    d = deal.model_dump()
    d["is_archived"] = 1 if d["is_archived"] else 0
    await db.execute(
        """
        UPDATE deals SET
            source=:source, listing_id=:listing_id, url=:url, name=:name,
            category=:category, monthly_net=:monthly_net,
            annual_multiple=:annual_multiple, asking_price=:asking_price,
            age_years=:age_years, notes=:notes,
            stage=:stage, is_archived=:is_archived,
            archive_reason=:archive_reason, archived_at=:archived_at,
            buy_vs_build_decision=:buy_vs_build_decision,
            buy_vs_build_reason=:buy_vs_build_reason,
            market_status=:market_status,
            listing_price_original=:listing_price_original,
            cashflow_score=:cashflow_score, moat_score=:moat_score,
            ai_proof_score=:ai_proof_score, value_add_score=:value_add_score,
            buy_vs_build_score=:buy_vs_build_score, risk_score=:risk_score,
            overall_score=:overall_score, down_payment=:down_payment,
            seller_finance_amount=:seller_finance_amount,
            monthly_debt_service=:monthly_debt_service,
            net_monthly_cashflow=:net_monthly_cashflow,
            heloc_used=:heloc_used, heloc_interest_monthly=:heloc_interest_monthly,
            net_after_heloc=:net_after_heloc,
            discovered_at=:discovered_at, stage_changed_at=:stage_changed_at,
            closed_at=:closed_at, updated_at=:updated_at
        WHERE id=:id
        """,
        d,
    )
    await _insert_history(db, history_event)
    await db.commit()


async def delete_deal(db: aiosqlite.Connection, deal_id: str) -> bool:
    cursor = await db.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
    await db.commit()
    return cursor.rowcount > 0


async def fetch_shortlist(db: aiosqlite.Connection, threshold: float = 7.5) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM deals WHERE overall_score >= ? AND is_archived = 0 ORDER BY overall_score DESC",
        (threshold,),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def fetch_pipeline(db: aiosqlite.Connection) -> dict[str, list[dict]]:
    """Return deals grouped by stage, excluding archived."""
    stages = ["tracking", "in_progress", "nda_signed", "loi_sent", "due_diligence", "closed"]
    result = {s: [] for s in stages}
    cursor = await db.execute(
        "SELECT * FROM deals WHERE is_archived = 0 ORDER BY overall_score DESC"
    )
    rows = await cursor.fetchall()
    for row in rows:
        d = _row_to_dict(row)
        stage = d.get("stage", "tracking")
        if stage in result:
            result[stage].append(d)
    return result


async def fetch_archived(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM deals WHERE is_archived = 1 ORDER BY archived_at DESC"
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def fetch_history(db: aiosqlite.Connection, deal_id: str) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM deal_history WHERE deal_id = ? ORDER BY created_at DESC",
        (deal_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def log_history(db: aiosqlite.Connection, event: dict) -> None:
    await _insert_history(db, event)
    await db.commit()
