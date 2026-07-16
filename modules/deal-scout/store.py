"""
EVA Deal Scout — ``DealStore`` persistence abstraction.

``DealStore`` is the swappable interface the whole pipeline talks to.  The only
implementation today is ``SQLiteDealStore`` (owned local SQLite, stdlib
``sqlite3`` — no external / 3rd-party DB, no async driver required).  A future
``MongoDealStore`` can implement the same surface without touching callers.

Design notes
------------
* Dedupe of raw deals is by ``(source, dedupe_key)`` where ``dedupe_key`` is the
  listing_id when present, else the url.  ``upsert_raw_deal`` updates the mutable
  columns of an existing row instead of inserting a duplicate.
* Every write stamps ``created_at`` / ``updated_at`` (and ``sourced_at`` /
  ``scored_at`` on the relevant tables).
* Scoring reads rows back out of the DB — the pipeline never scores transient
  JSON, only persisted ``raw_deals`` rows.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

from migrations import run_migrations
from pipeline_models import (
    DealSnapshot,
    RawDeal,
    ScoredDeal,
    SourceRun,
    TrendReport,
    now_iso,
)

DEFAULT_DB_PATH = "eva-deal-scout.db"


def _new_id() -> str:
    return str(uuid.uuid4())


def _dedupe_key(source: str, listing_id: str, url: str) -> str:
    """Stable dedupe key: prefer listing_id, fall back to url, then a uuid."""
    if listing_id:
        return listing_id.strip()
    if url:
        return url.strip().rstrip("/")
    return _new_id()


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class DealStore(ABC):
    """Swappable persistence surface for the sourcing/scoring pipeline."""

    @abstractmethod
    def migrate(self) -> list[int]: ...

    @abstractmethod
    def start_source_run(self, source: str, adapter: str = "", mode: str = "source") -> SourceRun: ...

    @abstractmethod
    def finish_source_run(self, run: SourceRun) -> None: ...

    @abstractmethod
    def upsert_raw_deal(self, deal: RawDeal) -> tuple[RawDeal, bool]: ...

    @abstractmethod
    def add_snapshot(self, snap: DealSnapshot) -> DealSnapshot: ...

    @abstractmethod
    def get_raw_deal(self, raw_deal_id: str) -> Optional[RawDeal]: ...

    @abstractmethod
    def list_raw_deals(self, *, is_closed: Optional[bool] = None, source: Optional[str] = None) -> list[RawDeal]: ...

    @abstractmethod
    def list_unscored_open_deals(self) -> list[RawDeal]: ...

    @abstractmethod
    def save_scored_deal(self, scored: ScoredDeal) -> ScoredDeal: ...

    @abstractmethod
    def list_scored_deals(self) -> list[ScoredDeal]: ...

    @abstractmethod
    def save_trend_report(self, report: TrendReport) -> TrendReport: ...

    @abstractmethod
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

class SQLiteDealStore(DealStore):
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    # -- schema ----------------------------------------------------------
    def migrate(self) -> list[int]:
        return run_migrations(self.conn)

    # -- source runs -----------------------------------------------------
    def start_source_run(self, source: str, adapter: str = "", mode: str = "source") -> SourceRun:
        run = SourceRun(id=_new_id(), source=source, adapter=adapter or source, mode=mode)
        self.conn.execute(
            """
            INSERT INTO source_runs (id, source, adapter, mode, status, deals_found,
                deals_new, deals_updated, snapshots_added, error, started_at,
                finished_at, created_at, updated_at)
            VALUES (:id, :source, :adapter, :mode, :status, :deals_found, :deals_new,
                :deals_updated, :snapshots_added, :error, :started_at, :finished_at,
                :created_at, :updated_at)
            """,
            run.model_dump(),
        )
        self.conn.commit()
        return run

    def finish_source_run(self, run: SourceRun) -> None:
        run.updated_at = now_iso()
        if not run.finished_at:
            run.finished_at = run.updated_at
        self.conn.execute(
            """
            UPDATE source_runs SET status=:status, deals_found=:deals_found,
                deals_new=:deals_new, deals_updated=:deals_updated,
                snapshots_added=:snapshots_added, error=:error,
                finished_at=:finished_at, updated_at=:updated_at
            WHERE id=:id
            """,
            run.model_dump(),
        )
        self.conn.commit()

    def list_source_runs(self) -> list[SourceRun]:
        cur = self.conn.execute("SELECT * FROM source_runs ORDER BY started_at DESC")
        return [SourceRun(**dict(r)) for r in cur.fetchall()]

    # -- raw deals -------------------------------------------------------
    def upsert_raw_deal(self, deal: RawDeal) -> tuple[RawDeal, bool]:
        """Insert or update by (source, dedupe_key). Returns (deal, created)."""
        if not deal.dedupe_key:
            deal.dedupe_key = _dedupe_key(deal.source, deal.listing_id, deal.url)
        cur = self.conn.execute(
            "SELECT * FROM raw_deals WHERE source=? AND dedupe_key=?",
            (deal.source, deal.dedupe_key),
        )
        existing = cur.fetchone()
        ts = now_iso()

        if existing is None:
            if not deal.id:
                deal.id = _new_id()
            deal.created_at = deal.created_at or ts
            deal.updated_at = ts
            deal.sourced_at = deal.sourced_at or ts
            self.conn.execute(
                """
                INSERT INTO raw_deals (id, source_run_id, source, listing_id, url,
                    dedupe_key, name, category, monthly_net, annual_multiple,
                    asking_price, age_years, currency, registration_country,
                    primary_customer_market, seller_location, trust_level,
                    is_closed, market_status, sold_price, sold_at,
                    owner_hours_per_week, incoming_score, gate_status, us_eligible,
                    trust_high, skip_reason, notes, raw_json, sourced_at,
                    created_at, updated_at)
                VALUES (:id, :source_run_id, :source, :listing_id, :url, :dedupe_key,
                    :name, :category, :monthly_net, :annual_multiple, :asking_price,
                    :age_years, :currency, :registration_country,
                    :primary_customer_market, :seller_location, :trust_level,
                    :is_closed, :market_status, :sold_price, :sold_at,
                    :owner_hours_per_week, :incoming_score, :gate_status, :us_eligible,
                    :trust_high, :skip_reason, :notes, :raw_json, :sourced_at,
                    :created_at, :updated_at)
                """,
                self._raw_params(deal),
            )
            self.conn.commit()
            return deal, True

        # Update mutable columns, keep original id/created_at and gate audit
        # (audit is owned by the SCORE stage, not re-sourcing).
        deal.id = existing["id"]
        deal.created_at = existing["created_at"]
        deal.updated_at = ts
        deal.sourced_at = ts
        # Preserve a non-zero incoming_score if the new payload lacks one.
        if not deal.incoming_score and existing["incoming_score"]:
            deal.incoming_score = existing["incoming_score"]
        self.conn.execute(
            """
            UPDATE raw_deals SET source_run_id=:source_run_id, url=:url, name=:name,
                category=:category, monthly_net=:monthly_net,
                annual_multiple=:annual_multiple, asking_price=:asking_price,
                age_years=:age_years, currency=:currency,
                registration_country=:registration_country,
                primary_customer_market=:primary_customer_market,
                seller_location=:seller_location, trust_level=:trust_level,
                is_closed=:is_closed, market_status=:market_status,
                sold_price=:sold_price, sold_at=:sold_at,
                owner_hours_per_week=:owner_hours_per_week,
                incoming_score=:incoming_score, notes=:notes,
                raw_json=:raw_json, sourced_at=:sourced_at, updated_at=:updated_at
            WHERE id=:id
            """,
            self._raw_params(deal),
        )
        self.conn.commit()
        return deal, False

    @staticmethod
    def _raw_params(deal: RawDeal) -> dict:
        d = deal.model_dump()
        d["is_closed"] = 1 if d["is_closed"] else 0
        d["us_eligible"] = 1 if d["us_eligible"] else 0
        d["trust_high"] = 1 if d["trust_high"] else 0
        return d

    @staticmethod
    def _row_to_raw(row: sqlite3.Row) -> RawDeal:
        d = dict(row)
        d["is_closed"] = bool(d.get("is_closed", 0))
        d["us_eligible"] = bool(d.get("us_eligible", 0))
        d["trust_high"] = bool(d.get("trust_high", 0))
        return RawDeal(**d)

    def set_gate_audit(self, raw_deal_id: str, *, gate_status: str, us_eligible: bool,
                       trust_high: bool, skip_reason: str = "") -> None:
        """Record the SCORE-stage gate decision on a raw deal (incl. skips)."""
        self.conn.execute(
            "UPDATE raw_deals SET gate_status=?, us_eligible=?, trust_high=?, "
            "skip_reason=?, updated_at=? WHERE id=?",
            (gate_status, 1 if us_eligible else 0, 1 if trust_high else 0,
             skip_reason, now_iso(), raw_deal_id),
        )
        self.conn.commit()

    def get_raw_deal(self, raw_deal_id: str) -> Optional[RawDeal]:
        cur = self.conn.execute("SELECT * FROM raw_deals WHERE id=?", (raw_deal_id,))
        row = cur.fetchone()
        return self._row_to_raw(row) if row else None

    def list_raw_deals(self, *, is_closed: Optional[bool] = None, source: Optional[str] = None) -> list[RawDeal]:
        clauses, params = [], []
        if is_closed is not None:
            clauses.append("is_closed = ?")
            params.append(1 if is_closed else 0)
        if source:
            clauses.append("source = ?")
            params.append(source)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        cur = self.conn.execute(f"SELECT * FROM raw_deals {where} ORDER BY sourced_at DESC", params)
        return [self._row_to_raw(r) for r in cur.fetchall()]

    def list_unscored_open_deals(self) -> list[RawDeal]:
        """Open (not closed) raw deals with no scored_deals row yet."""
        cur = self.conn.execute(
            """
            SELECT r.* FROM raw_deals r
            LEFT JOIN scored_deals s ON s.raw_deal_id = r.id
            WHERE r.is_closed = 0 AND s.id IS NULL
            ORDER BY r.sourced_at DESC
            """
        )
        return [self._row_to_raw(r) for r in cur.fetchall()]

    # -- snapshots -------------------------------------------------------
    def add_snapshot(self, snap: DealSnapshot) -> DealSnapshot:
        if not snap.id:
            snap.id = _new_id()
        self.conn.execute(
            """
            INSERT INTO deal_snapshots (id, raw_deal_id, source_run_id, market_status,
                asking_price, monthly_net, observed_at, created_at)
            VALUES (:id, :raw_deal_id, :source_run_id, :market_status, :asking_price,
                :monthly_net, :observed_at, :created_at)
            """,
            snap.model_dump(),
        )
        self.conn.commit()
        return snap

    def list_snapshots(self, raw_deal_id: str) -> list[DealSnapshot]:
        cur = self.conn.execute(
            "SELECT * FROM deal_snapshots WHERE raw_deal_id=? ORDER BY observed_at ASC",
            (raw_deal_id,),
        )
        return [DealSnapshot(**dict(r)) for r in cur.fetchall()]

    # -- scored deals ----------------------------------------------------
    def save_scored_deal(self, scored: ScoredDeal) -> ScoredDeal:
        if not scored.id:
            scored.id = _new_id()
        scored.updated_at = now_iso()
        params = scored.model_dump()
        params["us_eligible"] = 1 if params["us_eligible"] else 0
        params["trust_high"] = 1 if params["trust_high"] else 0
        # Upsert on raw_deal_id (unique index).
        self.conn.execute(
            """
            INSERT INTO scored_deals (id, raw_deal_id, source, listing_id, us_eligible,
                trust_high, skip_reason, trust_level, gate_reason, cashflow_score,
                moat_score, ai_proof_score, value_add_score, buy_vs_build_score,
                risk_score, mitigation_score, competitor_analysis_score,
                company_life_score, owner_neglect_score, adobe_platform_risk_score,
                overall_score, score_json, scored_at, created_at, updated_at)
            VALUES (:id, :raw_deal_id, :source, :listing_id, :us_eligible, :trust_high,
                :skip_reason, :trust_level, :gate_reason, :cashflow_score, :moat_score,
                :ai_proof_score, :value_add_score, :buy_vs_build_score, :risk_score,
                :mitigation_score, :competitor_analysis_score, :company_life_score,
                :owner_neglect_score, :adobe_platform_risk_score, :overall_score,
                :score_json, :scored_at, :created_at, :updated_at)
            ON CONFLICT(raw_deal_id) DO UPDATE SET
                us_eligible=excluded.us_eligible, trust_high=excluded.trust_high,
                skip_reason=excluded.skip_reason, trust_level=excluded.trust_level,
                gate_reason=excluded.gate_reason, cashflow_score=excluded.cashflow_score,
                moat_score=excluded.moat_score, ai_proof_score=excluded.ai_proof_score,
                value_add_score=excluded.value_add_score,
                buy_vs_build_score=excluded.buy_vs_build_score,
                risk_score=excluded.risk_score, mitigation_score=excluded.mitigation_score,
                competitor_analysis_score=excluded.competitor_analysis_score,
                company_life_score=excluded.company_life_score,
                owner_neglect_score=excluded.owner_neglect_score,
                adobe_platform_risk_score=excluded.adobe_platform_risk_score,
                overall_score=excluded.overall_score, score_json=excluded.score_json,
                scored_at=excluded.scored_at, updated_at=excluded.updated_at
            """,
            params,
        )
        self.conn.commit()
        return scored

    @staticmethod
    def _row_to_scored(row: sqlite3.Row) -> ScoredDeal:
        d = dict(row)
        d["us_eligible"] = bool(d.get("us_eligible", 0))
        d["trust_high"] = bool(d.get("trust_high", 0))
        return ScoredDeal(**d)

    def list_scored_deals(self) -> list[ScoredDeal]:
        cur = self.conn.execute("SELECT * FROM scored_deals ORDER BY overall_score DESC")
        return [self._row_to_scored(r) for r in cur.fetchall()]

    # -- trend reports ---------------------------------------------------
    def save_trend_report(self, report: TrendReport) -> TrendReport:
        if not report.id:
            report.id = _new_id()
        self.conn.execute(
            """
            INSERT INTO trend_reports (id, title, report_md, stats_json, generated_at, created_at)
            VALUES (:id, :title, :report_md, :stats_json, :generated_at, :created_at)
            """,
            report.model_dump(),
        )
        self.conn.commit()
        return report

    def latest_trend_report(self) -> Optional[TrendReport]:
        cur = self.conn.execute(
            "SELECT * FROM trend_reports ORDER BY generated_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        return TrendReport(**dict(row)) if row else None

    # -- export / compat -------------------------------------------------
    def export_json(self) -> dict[str, Any]:
        """Legacy-compatible export: scored deals plus raw + run metadata."""
        return {
            "source_runs": [r.model_dump() for r in self.list_source_runs()],
            "raw_deals": [r.model_dump() for r in self.list_raw_deals()],
            "scored_deals": [s.model_dump() for s in self.list_scored_deals()],
            "exported_at": now_iso(),
        }

    def close(self) -> None:
        self.conn.close()
