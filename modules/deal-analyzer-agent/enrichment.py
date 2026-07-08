"""
EVA Deal Analyzer Agent — enrichment DATA LAYER (Eva-side)
==========================================================

This module is the CONTRACT + apply/cache layer for market enrichment. It does
NOT gather external data. The actual research (Statista / CB Insights /
Similarweb) happens OUTSIDE Eva — on the Perplexity side — because those
connectors are not in Eva's local runtime. Eva-side, this module:

  1. Defines the enrichment CONTRACT (EnrichmentData + NicheDynamics + SourceRef).
  2. Applies enrichment onto a deal (apply_enrichment) into the exact kwargs dict
     that scoring_v7.analyze_deal_v7(deal, enrichment=...) consumes.
  3. Caches enrichment BY NICHE (NicheCache) so multiple deals in the same niche
     do not trigger repeated (paid) external research. TTL = 14 days.
  4. Documents the EXACT external-gatherer interface (fetch_enrichment_stub).
  5. Exposes a CLI so a human can see the contract working end-to-end offline.

Pure stdlib + pydantic. NO network, NO LLM, NO external connectors here.

CLI:
    python enrichment.py --niche "b2b analytics saas"
    python enrichment.py --niche "amazon fba pet supplies" --deal '{"name": "...", ...}'
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from models import VALID_RESEARCH_LEVELS

# Enrichment (flat kwargs payload) already lives in models.py; EnrichmentData is
# the richer data-layer record that wraps it with provenance + caching metadata.
from models import Enrichment  # re-exported for callers that want the flat form

CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), "enrichment_cache.db")
DEFAULT_TTL_DAYS = 14


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_niche(niche: str) -> str:
    """Canonical cache key: trimmed, collapsed-whitespace, lowercase."""
    return " ".join((niche or "").strip().lower().split())


# ===========================================================================
# CONTRACT MODELS
# ===========================================================================

class SourceRef(BaseModel):
    """A single provenance record for an enriched figure."""
    url: str = ""
    label: str = ""                                  # e.g. "Statista: US SaaS market 2025"
    retrieved_at: str = ""                           # ISO timestamp


class NicheDynamics(BaseModel):
    """Competitive/market dynamics for a niche (the CB Insights / Similarweb slice)."""
    niche: str = ""
    growth_rate_pct: float = 0.0                     # niche YoY growth %
    fragmentation_score: float = 0.0                 # 0-100, higher = more fragmented
    named_competitors: list = Field(default_factory=list)     # [str]
    estimated_market_share: Optional[float] = None   # subject's own share, 0-100
    source_urls: list = Field(default_factory=list)  # [SourceRef]
    confidence: float = 0.0                          # 0-100 confidence in this slice


class EnrichmentData(BaseModel):
    """The full enrichment record for a niche — the data-layer contract.

    A superset of models.Enrichment: it adds provenance (source_urls), the
    research tier (research_level), an overall confidence, the niche key, and the
    enrichment timestamp so it can be cached and audited. `to_enrichment_kwargs()`
    projects it down to the flat dict analyze_deal_v7 accepts.
    """
    niche: str = ""

    # --- TAM (Statista) -----------------------------------------------------
    tam_usd: float = 0.0
    sam_usd: float = 0.0
    market_growth_rate_pct: float = 0.0
    tam_source_url: str = ""
    tam_confidence_score: float = 0.0                # 0-100

    # --- Niche dynamics (CB Insights / Similarweb) --------------------------
    niche_growth_score: float = 0.0                  # 0-100
    market_fragmentation_score: float = 0.0          # 0-100
    named_competitors: list = Field(default_factory=list)     # [str]
    estimated_market_share: Optional[float] = None   # 0-100

    # --- provenance + meta --------------------------------------------------
    source_urls: list = Field(default_factory=list)  # [SourceRef]
    research_level: str = "L0"                        # "L0" | "L1" | "L2"
    confidence_overall: float = 0.0                  # 0-100
    enriched_at: str = ""                            # ISO timestamp

    def to_enrichment_kwargs(self) -> dict:
        """Project to the flat enrichment kwargs dict for analyze_deal_v7.

        Only fields the scoring engine reads are emitted; zero/empty fields are
        dropped so absent enrichment degrades gracefully (e.g. no tam_usd keeps
        tam_score at 0 rather than forcing a 0-TAM through the engine).
        """
        kwargs: dict[str, Any] = {}
        if self.tam_usd > 0:
            kwargs["tam_usd"] = self.tam_usd
        if self.sam_usd > 0:
            kwargs["sam_usd"] = self.sam_usd
        if self.market_growth_rate_pct:
            kwargs["market_growth_rate_pct"] = self.market_growth_rate_pct
        if self.tam_source_url:
            kwargs["tam_source_url"] = self.tam_source_url
        if self.tam_confidence_score:
            kwargs["tam_confidence_score"] = self.tam_confidence_score
        if self.niche_growth_score:
            kwargs["niche_growth_score"] = self.niche_growth_score
        if self.market_fragmentation_score:
            kwargs["market_fragmentation_score"] = self.market_fragmentation_score
        if self.named_competitors:
            kwargs["named_competitors"] = list(self.named_competitors)
        if self.estimated_market_share is not None:
            kwargs["estimated_market_share"] = self.estimated_market_share
        return kwargs


# ===========================================================================
# APPLY
# ===========================================================================

def apply_enrichment(deal: Any, enrichment: Any) -> dict:
    """Merge an EnrichmentData record onto a deal, returning the enrichment-kwargs
    dict that is ready to pass to analyze_deal_v7(deal, enrichment=<this>).

    `deal` may be a DealV7, a dict, or None (only used to backfill the niche when
    the enrichment record has none). `enrichment` may be an EnrichmentData, a
    dict, or a models.Enrichment. Types are validated/coerced; research_level is
    defaulted to "L0" when absent or invalid.

    Non-destructive: it does not mutate the deal or the enrichment record.
    """
    data = _coerce_enrichment(enrichment)

    if not data.niche:
        data.niche = normalize_niche(_deal_field(deal, "name", ""))

    if data.research_level not in VALID_RESEARCH_LEVELS:
        data.research_level = "L0"

    return data.to_enrichment_kwargs()


def _coerce_enrichment(enrichment: Any) -> EnrichmentData:
    """Accept EnrichmentData / dict / models.Enrichment and return EnrichmentData."""
    if isinstance(enrichment, EnrichmentData):
        return enrichment.model_copy(deep=True)
    if isinstance(enrichment, Enrichment):
        payload = enrichment.model_dump(exclude_none=True)
        return EnrichmentData(**{k: v for k, v in payload.items()
                                 if k in EnrichmentData.model_fields})
    if isinstance(enrichment, dict):
        return EnrichmentData(**{k: v for k, v in enrichment.items()
                                 if k in EnrichmentData.model_fields})
    raise TypeError(f"Unsupported enrichment type: {type(enrichment).__name__}")


def _deal_field(deal: Any, field: str, default: Any = None) -> Any:
    if deal is None:
        return default
    if isinstance(deal, dict):
        return deal.get(field, default)
    return getattr(deal, field, default)


# ===========================================================================
# NICHE CACHE (sqlite, TTL = 14 days)
# ===========================================================================

class NicheCache:
    """SQLite cache of EnrichmentData keyed by normalized niche.

    Rationale: enrichment research is economically expensive (paid connectors on
    the Perplexity side). Deals cluster by niche, so caching by niche lets many
    deals share one research pass. Entries expire after `ttl_days` (default 14)
    so market data does not go stale.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS niche_cache (
        niche       TEXT PRIMARY KEY,     -- normalized (lowercase) niche key
        data_json   TEXT NOT NULL,        -- EnrichmentData.model_dump_json()
        enriched_at TEXT NOT NULL,        -- ISO timestamp of the cache write
        ttl_days    INTEGER NOT NULL      -- freshness window for this entry
    );
    """

    def __init__(self, path: str = CACHE_DB_PATH, ttl_days: int = DEFAULT_TTL_DAYS):
        self.path = path
        self.ttl_days = ttl_days
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript(self._SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def get(self, niche: str) -> Optional[EnrichmentData]:
        """Return cached EnrichmentData if present AND fresh (< ttl_days), else None."""
        key = normalize_niche(niche)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT data_json, enriched_at, ttl_days FROM niche_cache WHERE niche = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        if self._is_expired(row["enriched_at"], row["ttl_days"]):
            return None
        return EnrichmentData(**json.loads(row["data_json"]))

    def put(self, niche: str, data: EnrichmentData) -> None:
        """Store/refresh EnrichmentData for a niche, stamping enriched_at = now."""
        key = normalize_niche(niche)
        data = data.model_copy(deep=True)
        data.niche = key
        data.enriched_at = _now().isoformat()
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(
                """
                INSERT INTO niche_cache (niche, data_json, enriched_at, ttl_days)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(niche) DO UPDATE SET
                    data_json=excluded.data_json,
                    enriched_at=excluded.enriched_at,
                    ttl_days=excluded.ttl_days
                """,
                (key, data.model_dump_json(), data.enriched_at, self.ttl_days),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _is_expired(enriched_at: str, ttl_days: int) -> bool:
        try:
            stamp = datetime.fromisoformat(enriched_at)
        except (TypeError, ValueError):
            return True
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return _now() - stamp > timedelta(days=ttl_days)


# ===========================================================================
# EXTERNAL-GATHERER CONTRACT (STUB — implemented OUTSIDE Eva)
# ===========================================================================

def fetch_enrichment_stub(niche: str) -> EnrichmentData:
    """CONTRACT STUB — the external gatherer must implement THIS interface.

    Given a niche string, the external gatherer (Perplexity-side, NOT Eva) must
    return an EnrichmentData JSON by calling the following connectors and mapping
    each result onto the fields below:

        CONNECTOR      ->  EnrichmentData field(s)
        ---------------------------------------------------------------------
        Statista       ->  tam_usd, sam_usd, market_growth_rate_pct,
                           tam_source_url, tam_confidence_score
                           (market size / total addressable market / CAGR)
        CB Insights    ->  named_competitors, estimated_market_share,
                           niche_growth_score
                           (competitor set, funding, subject market share)
        Similarweb     ->  market_fragmentation_score, niche_growth_score
                           (traffic distribution / demographics / how spread
                            demand is across players => fragmentation)

        cross-cutting  ->  source_urls (one SourceRef per connector call),
                           research_level (L1 once named_competitors +
                           estimated_market_share are present; else L0),
                           confidence_overall (blend of per-connector confidence)

    This Eva-side stub performs NO network calls. It returns an empty L0 record
    marked as unresearched so the rest of the pipeline degrades gracefully and
    the human can SEE the contract shape. Wire the real gatherer externally and
    have it hand back EnrichmentData JSON matching this schema.
    """
    key = normalize_niche(niche)
    return EnrichmentData(
        niche=key,
        research_level="L0",
        confidence_overall=0.0,
        enriched_at=_now().isoformat(),
        source_urls=[
            SourceRef(
                url="",
                label="UNRESEARCHED — external gatherer (Statista/CB Insights/"
                      "Similarweb) not implemented in Eva runtime",
                retrieved_at=_now().isoformat(),
            ).model_dump()
        ],
    )


def get_or_fetch(niche: str, cache: Optional[NicheCache] = None) -> tuple[EnrichmentData, str]:
    """Return (EnrichmentData, origin) for a niche.

    origin is "cache" on a fresh hit, else "stub" (the external gatherer would be
    invoked here in production). A stub result is intentionally NOT cached — only
    real research should populate the cache.
    """
    cache = cache or NicheCache()
    cached = cache.get(niche)
    if cached is not None:
        return cached, "cache"
    return fetch_enrichment_stub(niche), "stub"


# ===========================================================================
# CLI
# ===========================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Show what enrichment WOULD be applied for a niche (cache or stub).",
    )
    p.add_argument("--niche", required=True, help="Niche string, e.g. 'b2b analytics saas'")
    p.add_argument("--deal", default="", help="Optional deal as a JSON string")
    p.add_argument("--cache-db", default=CACHE_DB_PATH, help="Path to the niche cache DB")
    p.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS, help="Cache TTL in days")
    return p


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    cache = NicheCache(path=args.cache_db, ttl_days=args.ttl_days)
    data, origin = get_or_fetch(args.niche, cache=cache)

    deal = None
    if args.deal.strip():
        try:
            deal = json.loads(args.deal)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --deal is not valid JSON: {exc}")
            return 2

    applied = apply_enrichment(deal, data)

    print(f"niche (normalized) : {normalize_niche(args.niche)}")
    print(f"enrichment origin  : {origin}")
    print(f"research_level     : {data.research_level}")
    print(f"confidence_overall : {data.confidence_overall}")
    print("\n--- EnrichmentData (full contract record) ---")
    print(json.dumps(json.loads(data.model_dump_json()), indent=2))
    print("\n--- enrichment kwargs that WOULD be applied to analyze_deal_v7 ---")
    print(json.dumps(applied, indent=2, default=str))
    if not applied:
        print("(empty — nothing to apply; niche is unresearched. Run the external "
              "gatherer, then NicheCache.put() the result to populate the cache.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
