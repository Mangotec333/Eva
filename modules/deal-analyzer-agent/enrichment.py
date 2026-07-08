"""
EVA Deal Analyzer Agent — enrichment DATA LAYER (Eva-side)
==========================================================

This module is the CONTRACT + apply/cache layer for market enrichment, PLUS the
Eva-side call-out to the research brain. The actual connectors (Statista /
CB Insights / Similarweb) live OUTSIDE Eva — on the Perplexity Computer side —
because they are not in Eva's local runtime. Eva-side, this module:

  1. Defines the enrichment CONTRACT (EnrichmentData + NicheDynamics + SourceRef).
  2. Applies enrichment onto a deal (apply_enrichment) into the exact kwargs dict
     that scoring_v7.analyze_deal_v7(deal, enrichment=...) consumes.
  3. Caches enrichment BY NICHE (NicheCache) so multiple deals in the same niche
     do not trigger repeated (paid) external research. TTL = 14 days.
  4. gather_enrichment(niche): calls the Perplexity transport
     (services/remote/perplexity.py) with a structured research request and maps
     the response into EnrichmentData. Degrades to an L0 record when the transport
     is Noop (not configured) — never crashes.
  5. Exposes a CLI so a human can see the contract working end-to-end offline.

stdlib + pydantic + the Perplexity transport seam. The transport itself does NO
network in the default (Noop/Mock) path, so this module is offline-safe.

CLI:
    python enrichment.py --niche "b2b analytics saas"
    python enrichment.py --niche "amazon fba pet supplies" --deal '{"name": "...", ...}'
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

# The module runs "flat" (cwd = this dir); put the repo root on the path to reach
# the shared services/ package for the Perplexity research transport.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from services.remote.perplexity import (  # noqa: E402  (path bootstrap above)
    NoopPerplexityClient,
    PerplexityClient,
    PerplexityRequest,
    PerplexityStatus,
)

from models import VALID_RESEARCH_LEVELS  # noqa: E402

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


def _empty_l0(niche: str, label: str) -> EnrichmentData:
    """An unresearched L0 record — the safe degrade when research is unavailable."""
    return EnrichmentData(
        niche=normalize_niche(niche),
        research_level="L0",
        confidence_overall=0.0,
        enriched_at=_now().isoformat(),
        source_urls=[SourceRef(url="", label=label, retrieved_at=_now().isoformat()).model_dump()],
    )


def _build_research_request(niche: str) -> PerplexityRequest:
    """Frame the structured research ask for the Perplexity Computer brain.

    The ``context.schema`` field tells the remote gatherer EXACTLY which
    EnrichmentData fields to return and which connector sources each one.
    """
    return PerplexityRequest(
        task_id=f"enrich-{uuid.uuid4().hex[:12]}",
        utterance=(
            f"Research the market niche '{niche}' for an acquisition analysis. "
            "Return TAM/market size and CAGR (Statista); named competitors and the "
            "subject's estimated market share (CB Insights + Similarweb lead "
            "enrichment); and niche growth + fragmentation (Similarweb)."
        ),
        context={
            "purpose": "deal_enrichment",
            # field -> connector contract the remote gatherer must satisfy.
            "schema": {
                "tam_usd": "Statista", "sam_usd": "Statista",
                "market_growth_rate_pct": "Statista",
                "tam_source_url": "Statista", "tam_confidence_score": "Statista",
                "named_competitors": "CB Insights",
                "estimated_market_share": "CB Insights + Similarweb",
                "niche_growth_score": "CB Insights + Similarweb",
                "market_fragmentation_score": "Similarweb",
            },
        },
        constraints={"return": "EnrichmentData-json"},
    )


# field -> the EnrichmentData attribute + connector it comes from. Kept inline so
# the mapping is auditable next to the code that applies it.
#   Statista     -> tam_usd, sam_usd, market_growth_rate_pct, tam_source_url,
#                   tam_confidence_score
#   CB Insights  -> named_competitors, estimated_market_share, niche_growth_score
#   Similarweb   -> market_fragmentation_score, niche_growth_score
_RESULT_NUMERIC = (
    "tam_usd", "sam_usd", "market_growth_rate_pct", "tam_confidence_score",
    "niche_growth_score", "market_fragmentation_score", "estimated_market_share",
)


def _map_response(niche: str, result: dict) -> EnrichmentData:
    """Map a Perplexity research result dict into an EnrichmentData record.

    Only recognised fields are read; missing figures stay at their zero default
    so absent data degrades gracefully in scoring. research_level is promoted to
    L1 once named competitors AND an estimated share are present.
    """
    data = EnrichmentData(niche=normalize_niche(niche), enriched_at=_now().isoformat())

    for key in _RESULT_NUMERIC:
        if result.get(key) is not None:
            try:
                setattr(data, key, float(result[key]))
            except (TypeError, ValueError):
                pass

    if result.get("tam_source_url"):
        data.tam_source_url = str(result["tam_source_url"])
    if isinstance(result.get("named_competitors"), list):
        data.named_competitors = list(result["named_competitors"])

    # provenance: accept pre-shaped SourceRef dicts or bare url strings.
    for src in result.get("source_urls", []) or []:
        if isinstance(src, dict):
            data.source_urls.append(SourceRef(**{k: src.get(k, "") for k in
                                                 ("url", "label", "retrieved_at")}).model_dump())
        elif isinstance(src, str):
            data.source_urls.append(SourceRef(url=src, retrieved_at=_now().isoformat()).model_dump())

    has_share = data.estimated_market_share is not None and data.estimated_market_share > 0
    data.research_level = "L1" if (data.named_competitors and has_share) else "L0"
    data.confidence_overall = float(result.get("confidence_overall", 0.0) or 0.0)
    return data


def gather_enrichment(
    niche: str,
    client: Optional[PerplexityClient] = None,
    cache: Optional[NicheCache] = None,
) -> EnrichmentData:
    """Gather market enrichment for a niche via the Perplexity research brain.

    Flow: cache hit (fresh) short-circuits. Otherwise a structured
    PerplexityRequest is submitted; on a COMPLETED response the result is mapped
    into EnrichmentData and cached. Any other status (including the Noop client's
    ``FAILED`` when no transport is configured) returns an uncached L0 record so
    the pipeline degrades gracefully instead of crashing.
    """
    cache = cache or NicheCache()
    cached = cache.get(niche)
    if cached is not None:
        return cached

    client = client or NoopPerplexityClient()
    response = client.submit(_build_research_request(niche))

    if response.status is not PerplexityStatus.COMPLETED:
        reason = response.error or response.status.value
        return _empty_l0(niche, f"UNRESEARCHED — remote research {reason}")

    data = _map_response(niche, response.result or {})
    cache.put(niche, data)  # only real research populates the cache
    return data


def _build_paid_research_request(niche: str) -> PerplexityRequest:
    """Frame the PAID deep-dive research ask (CB Insights + Similarweb).

    This is the shortlist-only escalation: named competitors, the subject's
    estimated market share, and traffic-based fragmentation — the economically
    expensive slice we do NOT spend per-deal in the hot loop.
    """
    return PerplexityRequest(
        task_id=f"enrich-paid-{uuid.uuid4().hex[:12]}",
        utterance=(
            f"DEEP-DIVE the market niche '{niche}' for a SHORTLISTED acquisition. "
            "Use the paid connectors: CB Insights for named competitors, funding, "
            "and the subject's estimated market share; Similarweb for traffic "
            "distribution / demand fragmentation and niche growth."
        ),
        context={
            "purpose": "deal_enrichment_paid",
            "tier": "paid",
            "schema": {
                "named_competitors": "CB Insights",
                "estimated_market_share": "CB Insights + Similarweb",
                "niche_growth_score": "CB Insights + Similarweb",
                "market_fragmentation_score": "Similarweb",
            },
        },
        constraints={"return": "EnrichmentData-json", "tier": "paid"},
    )


def gather_paid_enrichment(
    niche: str,
    client: Optional[PerplexityClient] = None,
    cache: Optional[NicheCache] = None,
) -> EnrichmentData:
    """PAID deep-dive enrichment (CB Insights + Similarweb) — SHORTLIST ONLY.

    A SEPARATE, explicit escalation from the free ``gather_enrichment`` per-niche
    path: it is invoked ONLY on the final shortlist (top deals / score >= the
    configured threshold), never per-deal in the hot loop. Same offline-safe
    contract as the free path: a Noop transport degrades to an uncached L0
    record, real research is mapped into EnrichmentData and cached by niche.
    """
    cache = cache or NicheCache()
    cached = cache.get(niche)
    if cached is not None:
        return cached

    client = client or NoopPerplexityClient()
    response = client.submit(_build_paid_research_request(niche))

    if response.status is not PerplexityStatus.COMPLETED:
        reason = response.error or response.status.value
        return _empty_l0(niche, f"UNRESEARCHED — paid deep-dive {reason}")

    data = _map_response(niche, response.result or {})
    cache.put(niche, data)
    return data


def make_enricher(
    client: Optional[PerplexityClient] = None,
    cache: Optional[NicheCache] = None,
):
    """Return an ``EnrichFn`` (niche -> flat kwargs) for DealAnalyzerAgent.

    Bridges gather_enrichment to the agent's ``enrich_fn`` seam: it gathers the
    EnrichmentData and projects it to the flat kwargs analyze_deal_v7 consumes.
    """
    def _enrich(niche: str) -> dict:
        return gather_enrichment(niche, client=client, cache=cache).to_enrichment_kwargs()
    return _enrich


def make_paid_enricher(
    client: Optional[PerplexityClient] = None,
    cache: Optional[NicheCache] = None,
):
    """Return a paid ``EnrichFn`` (niche -> flat kwargs) for the shortlist deep-dive.

    Mirrors ``make_enricher`` but bridges the PAID ``gather_paid_enrichment`` path,
    so the agent can escalate a shortlisted deal without knowing the transport.
    """
    def _enrich(niche: str) -> dict:
        return gather_paid_enrichment(niche, client=client, cache=cache).to_enrichment_kwargs()
    return _enrich


def get_or_fetch(niche: str, cache: Optional[NicheCache] = None) -> tuple[EnrichmentData, str]:
    """Return (EnrichmentData, origin) for a niche.

    origin is "cache" on a fresh hit, else "stub" — the offline L0 record from
    fetch_enrichment_stub. Use gather_enrichment() with a configured Perplexity
    client for real research. A stub result is intentionally NOT cached.
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
