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
    CaseStudy,
    Competitor,
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
    def add_competitor(self, deal_id: str, name: str, what_they_do: str = "",
                       pricing_model: str = "", url: str = "", moat_comparison: str = "",
                       source_url: str = "", category: Optional[str] = None) -> Competitor: ...

    @abstractmethod
    def list_competitors(self, deal_id: str) -> list[Competitor]: ...

    @abstractmethod
    def add_case_study(self, source_url: str, deal_type: str, title: str,
                       deal_id: Optional[str] = None,
                       snapshot: Optional[dict] = None,
                       analysis: Optional[dict] = None,
                       pattern_tags: Optional[list[str]] = None,
                       formula_insight: str = "") -> CaseStudy: ...

    @abstractmethod
    def list_case_studies(self, deal_type: Optional[str] = None) -> list[CaseStudy]: ...

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
                overall_score, build_feasibility, build_time_estimate, moat_build_years,
                buy_vs_build_recommendation, buy_vs_build_rationale, score_json,
                scored_at, created_at, updated_at)
            VALUES (:id, :raw_deal_id, :source, :listing_id, :us_eligible, :trust_high,
                :skip_reason, :trust_level, :gate_reason, :cashflow_score, :moat_score,
                :ai_proof_score, :value_add_score, :buy_vs_build_score, :risk_score,
                :mitigation_score, :competitor_analysis_score, :company_life_score,
                :owner_neglect_score, :adobe_platform_risk_score, :overall_score,
                :build_feasibility, :build_time_estimate, :moat_build_years,
                :buy_vs_build_recommendation, :buy_vs_build_rationale, :score_json,
                :scored_at, :created_at, :updated_at)
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
                overall_score=excluded.overall_score,
                build_feasibility=excluded.build_feasibility,
                build_time_estimate=excluded.build_time_estimate,
                moat_build_years=excluded.moat_build_years,
                buy_vs_build_recommendation=excluded.buy_vs_build_recommendation,
                buy_vs_build_rationale=excluded.buy_vs_build_rationale,
                score_json=excluded.score_json,
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

    # -- competitor intelligence ----------------------------------------
    @staticmethod
    def _competitor_key(name: str) -> str:
        return " ".join(name.strip().lower().split())

    def add_competitor(self, deal_id: str, name: str, what_they_do: str = "",
                       pricing_model: str = "", url: str = "", moat_comparison: str = "",
                       source_url: str = "", category: Optional[str] = None) -> Competitor:
        """Upsert the competitor entity (deduped by name) and link it to a deal.

        The competitor row compounds across deals: re-calling with the same name
        fills in any fields that were previously blank without clobbering
        existing intel.  The deal-specific ``moat_comparison`` is stored on the
        join and refreshed on every call.
        """
        name = name.strip()
        if not name:
            raise ValueError("competitor name is required")
        name_key = self._competitor_key(name)
        ts = now_iso()

        cur = self.conn.execute(
            "SELECT * FROM competitors WHERE name_key=?", (name_key,))
        existing = cur.fetchone()

        if existing is None:
            comp_id = _new_id()
            self.conn.execute(
                """
                INSERT INTO competitors (id, name, name_key, what_they_do,
                    pricing_model, url, category, source_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (comp_id, name, name_key, what_they_do, pricing_model, url,
                 category or "", source_url, ts, ts),
            )
        else:
            comp_id = existing["id"]
            # Compound: only fill blanks, never clobber researched intel.
            self.conn.execute(
                """
                UPDATE competitors SET
                    what_they_do  = CASE WHEN what_they_do='' THEN ? ELSE what_they_do END,
                    pricing_model = CASE WHEN pricing_model='' THEN ? ELSE pricing_model END,
                    url           = CASE WHEN url='' THEN ? ELSE url END,
                    category      = CASE WHEN category='' THEN ? ELSE category END,
                    source_url    = CASE WHEN source_url='' THEN ? ELSE source_url END,
                    updated_at    = ?
                WHERE id=?
                """,
                (what_they_do, pricing_model, url, category or "", source_url,
                 ts, comp_id),
            )

        # Link to the deal (upsert the join; refresh moat_comparison).
        link = self.conn.execute(
            "SELECT id FROM deal_competitors WHERE deal_id=? AND competitor_id=?",
            (deal_id, comp_id),
        ).fetchone()
        if link is None:
            self.conn.execute(
                """
                INSERT INTO deal_competitors (id, deal_id, competitor_id,
                    moat_comparison, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_new_id(), deal_id, comp_id, moat_comparison, ts, ts),
            )
        elif moat_comparison:
            self.conn.execute(
                "UPDATE deal_competitors SET moat_comparison=?, updated_at=? WHERE id=?",
                (moat_comparison, ts, link["id"]),
            )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM competitors WHERE id=?", (comp_id,)).fetchone()
        comp = self._row_to_competitor(row)
        comp.moat_comparison = moat_comparison
        return comp

    @staticmethod
    def _row_to_competitor(row: sqlite3.Row) -> Competitor:
        d = dict(row)
        d.pop("name_key", None)
        d.pop("moat_comparison", None)         # entity row carries no link field
        d.pop("link_moat_comparison", None)    # from the list_competitors join
        return Competitor(**d)

    def list_competitors(self, deal_id: str) -> list[Competitor]:
        """Competitors linked to a deal, with each link's moat_comparison."""
        cur = self.conn.execute(
            """
            SELECT c.*, dc.moat_comparison AS link_moat_comparison
            FROM deal_competitors dc
            JOIN competitors c ON c.id = dc.competitor_id
            WHERE dc.deal_id = ?
            ORDER BY dc.created_at ASC
            """,
            (deal_id,),
        )
        out: list[Competitor] = []
        for row in cur.fetchall():
            comp = self._row_to_competitor(row)
            comp.moat_comparison = row["link_moat_comparison"]
            out.append(comp)
        return out

    # -- case studies (4-lens compounding intelligence) ------------------
    def add_case_study(self, source_url: str, deal_type: str, title: str,
                       deal_id: Optional[str] = None,
                       snapshot: Optional[dict] = None,
                       analysis: Optional[dict] = None,
                       pattern_tags: Optional[list[str]] = None,
                       formula_insight: str = "") -> CaseStudy:
        """Insert or update a 4-lens case study, upserted by ``source_url``.

        Re-studying the same URL refreshes the row (and ``updated_at``) instead
        of duplicating; ``created_at`` is preserved on update."""
        ts = now_iso()
        existing = self.conn.execute(
            "SELECT id, created_at FROM case_studies WHERE source_url=?",
            (source_url,),
        ).fetchone()

        study = CaseStudy(
            id=existing["id"] if existing else _new_id(),
            source_url=source_url,
            deal_type=deal_type,
            title=title,
            deal_id=deal_id,
            snapshot=snapshot or {},
            analysis=analysis or {},
            pattern_tags=pattern_tags or [],
            formula_insight=formula_insight,
            created_at=existing["created_at"] if existing else ts,
            updated_at=ts,
        )
        params = {
            "id": study.id,
            "source_url": study.source_url,
            "deal_type": study.deal_type,
            "title": study.title,
            "deal_id": study.deal_id,
            "snapshot": json.dumps(study.snapshot),
            "analysis": json.dumps(study.analysis),
            "pattern_tags": json.dumps(study.pattern_tags),
            "formula_insight": study.formula_insight,
            "created_at": study.created_at,
            "updated_at": study.updated_at,
        }
        if existing is not None:
            self.conn.execute(
                """UPDATE case_studies SET deal_type=:deal_type, title=:title,
                   deal_id=:deal_id, snapshot=:snapshot, analysis=:analysis,
                   pattern_tags=:pattern_tags, formula_insight=:formula_insight,
                   updated_at=:updated_at WHERE id=:id""", params)
        else:
            self.conn.execute(
                """INSERT INTO case_studies (id, source_url, deal_type, title,
                   deal_id, snapshot, analysis, pattern_tags, formula_insight,
                   created_at, updated_at)
                   VALUES (:id, :source_url, :deal_type, :title, :deal_id,
                   :snapshot, :analysis, :pattern_tags, :formula_insight,
                   :created_at, :updated_at)""", params)
        self.conn.commit()
        return study

    @staticmethod
    def _row_to_case_study(row: sqlite3.Row) -> CaseStudy:
        d = dict(row)
        for field, default in (("snapshot", {}), ("analysis", {}), ("pattern_tags", [])):
            try:
                d[field] = json.loads(d.get(field) or json.dumps(default))
            except (json.JSONDecodeError, TypeError):
                d[field] = default
        return CaseStudy(**d)

    def list_case_studies(self, deal_type: Optional[str] = None) -> list[CaseStudy]:
        """List case studies, newest first, optionally filtered by deal_type."""
        where, params = "", []
        if deal_type:
            where, params = "WHERE deal_type = ?", [deal_type]
        cur = self.conn.execute(
            f"SELECT * FROM case_studies {where} ORDER BY created_at DESC", params)
        return [self._row_to_case_study(r) for r in cur.fetchall()]

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
