"""
EVA Deal Scout — two-stage DB-backed pipeline.

    Stage 1 (SOURCE)  source_deals(...)  →  raw_deals + deal_snapshots + source_run
    Stage 2 (SCORE)   score_pending(...) →  scored_deals   (gated, from the DB)

The two stages are deliberately decoupled: sourcing persists normalized rows
first, and scoring reads those persisted rows back out.  The scorer is never
handed transient JSON.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Iterable, Optional

import urllib.error
import urllib.request

from analyzer import analyze_deal, build_feasibility_assessment
from models import Deal
from pipeline_models import DealSnapshot, RawDeal, ScoredDeal, now_iso
from scoring_gate import evaluate
from sources import ACTIVATED_SOURCES, get_adapter
from store import DealStore

# 11 composite dimensions carried from analyzer output into scored_deals.
SCORE_FIELDS = (
    "cashflow_score", "moat_score", "ai_proof_score", "value_add_score",
    "buy_vs_build_score", "risk_score", "mitigation_score",
    "competitor_analysis_score", "company_life_score", "owner_neglect_score",
    "adobe_platform_risk_score", "overall_score",
)


# ---------------------------------------------------------------------------
# Stage 1 — SOURCE
# ---------------------------------------------------------------------------

def source_deals(
    store: DealStore,
    source: str,
    payloads: Iterable[dict],
    *,
    mode: str = "source",
) -> dict[str, Any]:
    """Normalize + persist listings from one source into the store.

    Returns a summary dict with the source_run id and counts.
    """
    adapter = get_adapter(source)
    run = store.start_source_run(source=source, adapter=adapter.label, mode=mode)

    new_count = updated_count = snap_count = 0
    try:
        raw_deals = adapter.to_raw_deals(list(payloads))
        for rd in raw_deals:
            rd.source_run_id = run.id
            stored, created = store.upsert_raw_deal(rd)
            if created:
                new_count += 1
            else:
                updated_count += 1
            # Every source touch records a status observation.
            store.add_snapshot(DealSnapshot(
                id="",
                raw_deal_id=stored.id,
                source_run_id=run.id,
                market_status=stored.market_status,
                asking_price=stored.asking_price,
                monthly_net=stored.monthly_net,
                observed_at=now_iso(),
            ))
            snap_count += 1

        run.deals_found = len(raw_deals)
        run.deals_new = new_count
        run.deals_updated = updated_count
        run.snapshots_added = snap_count
        run.status = "completed"
    except Exception as exc:  # noqa: BLE001 — surface the failure on the run row
        run.status = "failed"
        run.error = str(exc)
        store.finish_source_run(run)
        raise
    store.finish_source_run(run)

    return {
        "source_run_id": run.id,
        "source": source,
        "found": run.deals_found,
        "new": new_count,
        "updated": updated_count,
        "snapshots": snap_count,
        "status": run.status,
    }


# ---------------------------------------------------------------------------
# Wide source run — attempt every activated source, record what needs a browser
# ---------------------------------------------------------------------------

def _fetch_feed(url: str, *, timeout: float = 8.0) -> list[dict]:
    """Best-effort fetch of a public feed page.

    We have no per-source HTML→listing parser for the newly activated sources
    yet, so a *successful* fetch still can't yield structured deals — it is
    surfaced as a distinct blocking reason (needs a parser) separate from a
    network/HTTP failure.  Raises on any blocking condition; the caller records
    the reason on a ``seeded_not_fetchable`` source_run.
    """
    if not url:
        raise RuntimeError("no feed_url configured")
    req = urllib.request.Request(url, headers={"User-Agent": "EVA-DealScout/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted urls)
        resp.read()
    raise NotImplementedError(
        "public page fetched but no structured feed parser for this source yet "
        "— needs a source-specific adapter/browser to extract listings"
    )


def wide_source_run(
    store: DealStore,
    sources: Iterable[str] = ACTIVATED_SOURCES,
    *,
    payloads_by_source: Optional[dict[str, list[dict]]] = None,
) -> dict[str, Any]:
    """Attempt to source every requested source into raw_deals.

    For each source:
      * if a caller supplies ready payloads (``payloads_by_source``), ingest
        them via the normal SOURCE stage;
      * else if the source is gated (auth/browser only), record a
        ``seeded_not_fetchable`` source_run with the blocking reason;
      * else attempt to fetch the public feed — on any failure (network, HTTP,
        or no-parser-yet) record ``seeded_not_fetchable`` with that reason.

    Returns a per-source summary: ingested vs unfetchable + the reason.
    """
    payloads_by_source = payloads_by_source or {}
    results: dict[str, dict[str, Any]] = {}

    for source in sources:
        adapter = get_adapter(source)
        supplied = payloads_by_source.get(source)

        if supplied:
            summary = source_deals(store, source, supplied)
            results[source] = {"status": "ingested", "ingested": summary["new"] + summary["updated"],
                               "reason": ""}
            continue

        if adapter.access == "gated":
            reason = f"gated marketplace — {adapter.feed_url or adapter.label} requires an authenticated session / browser"
            _record_unfetchable(store, adapter, reason)
            results[source] = {"status": "seeded_not_fetchable", "ingested": 0, "reason": reason}
            continue

        try:
            listings = _fetch_feed(adapter.feed_url)
        except Exception as exc:  # noqa: BLE001 — reason is recorded, not raised
            reason = f"{type(exc).__name__}: {exc}"
            _record_unfetchable(store, adapter, reason)
            results[source] = {"status": "seeded_not_fetchable", "ingested": 0, "reason": reason}
            continue

        summary = source_deals(store, source, listings)
        results[source] = {"status": "ingested", "ingested": summary["new"] + summary["updated"],
                           "reason": ""}

    ingested = sum(1 for r in results.values() if r["status"] == "ingested")
    unfetchable = sum(1 for r in results.values() if r["status"] == "seeded_not_fetchable")
    return {
        "sources_attempted": len(results),
        "ingested_sources": ingested,
        "unfetchable_sources": unfetchable,
        "per_source": results,
    }


def _record_unfetchable(store: DealStore, adapter, reason: str) -> None:
    """Log a source_run row flagging a source as needing a browser/auth."""
    run = store.start_source_run(source=adapter.key, adapter=adapter.label, mode="wide")
    run.status = "seeded_not_fetchable"
    run.error = reason
    store.finish_source_run(run)


# ---------------------------------------------------------------------------
# RawDeal → Deal bridge (for the v6 scorer)
# ---------------------------------------------------------------------------

def raw_to_deal(rd: RawDeal) -> Deal:
    """Adapt a persisted RawDeal into the analyzer's Deal shape."""
    return Deal(
        id=rd.id,
        source=rd.source,
        listing_id=rd.listing_id,
        url=rd.url,
        name=rd.name or "Unnamed",
        category=rd.category,
        monthly_net=rd.monthly_net,
        annual_multiple=rd.annual_multiple,
        asking_price=rd.asking_price,
        listing_price_original=rd.asking_price,
        age_years=rd.age_years,
        notes=rd.notes,
        market_status=rd.market_status if rd.market_status in ("available", "sold", "off_market") else "available",
        discovered_at=rd.sourced_at,
        created_at=rd.created_at,
        updated_at=now_iso(),
    )


# ---------------------------------------------------------------------------
# Stage 2 — SCORE (gated)
# ---------------------------------------------------------------------------

def score_raw_deal(store: DealStore, rd: RawDeal, *, force: bool = False,
                   **analyzer_kwargs: Any) -> dict[str, Any]:
    """Gate + score a single persisted raw deal, writing the gate audit either way.

    ``force=True`` scores a deal the gate would skip (used by manual
    single-listing ingests of gated marketplaces), recording the would-be skip
    reason on the scored row so the audit trail still shows the gate verdict.
    """
    decision = evaluate(rd)
    if not decision.should_score and not force:
        # Persist the skip decision on the raw row so the gate audit stays
        # queryable (US_eligible / trust_high / skip_reason).
        store.set_gate_audit(
            rd.id, gate_status="skipped", us_eligible=decision.us_eligible,
            trust_high=decision.trust_high, skip_reason=decision.reason,
        )
        return {"status": "skipped", "raw_deal_id": rd.id, "name": rd.name,
                "reason": decision.reason}

    deal = raw_to_deal(rd)
    result = analyze_deal(deal, **analyzer_kwargs)
    dump = result.model_dump()

    forced = not decision.should_score
    scored = ScoredDeal(
        id="",
        raw_deal_id=rd.id,
        source=rd.source,
        listing_id=rd.listing_id,
        us_eligible=decision.us_eligible,
        trust_high=decision.trust_high,
        trust_level=rd.trust_level,
        gate_reason=decision.reason,
        skip_reason="manual_score_gate_would_skip" if forced else "",
        score_json=json.dumps(dump, default=str),
        scored_at=now_iso(),
    )
    for f in SCORE_FIELDS:
        setattr(scored, f, float(dump.get(f, 0.0) or 0.0))

    # Buy-vs-Build assessment on every scored deal (moat_build_years = the
    # deal-killer for the build path).
    assessment = build_feasibility_assessment(
        moat_score=scored.moat_score,
        ai_proof_score=scored.ai_proof_score,
        category=rd.category,
    )
    for f, v in assessment.items():
        setattr(scored, f, v)

    store.save_scored_deal(scored)
    store.set_gate_audit(
        rd.id, gate_status="scored", us_eligible=decision.us_eligible,
        trust_high=decision.trust_high,
        skip_reason=scored.skip_reason,
    )
    return {"status": "scored", "raw_deal_id": rd.id, "name": rd.name,
            "reason": decision.reason, "forced": forced,
            "overall_score": scored.overall_score,
            "scores": {f: getattr(scored, f) for f in SCORE_FIELDS}}


def score_pending(store: DealStore, **analyzer_kwargs: Any) -> dict[str, Any]:
    """Score every unscored open raw deal that passes the gate.

    ``analyzer_kwargs`` are forwarded to ``analyze_deal`` (v6 11-param scorer),
    letting callers pass qualitative signals per batch when known.
    """
    scored_ids: list[str] = []
    skipped: list[dict[str, str]] = []

    for rd in store.list_unscored_open_deals():
        outcome = score_raw_deal(store, rd, **analyzer_kwargs)
        if outcome["status"] == "scored":
            scored_ids.append(rd.id)
        else:
            skipped.append({"raw_deal_id": rd.id, "name": rd.name,
                            "reason": outcome["reason"]})

    return {
        "scored": len(scored_ids),
        "skipped": len(skipped),
        "skipped_detail": skipped,
        "scored_raw_ids": scored_ids,
    }
