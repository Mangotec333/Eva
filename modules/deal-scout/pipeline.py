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

from analyzer import analyze_deal
from models import Deal
from pipeline_models import DealSnapshot, RawDeal, ScoredDeal, now_iso
from scoring_gate import evaluate
from sources import get_adapter
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

def score_pending(store: DealStore, **analyzer_kwargs: Any) -> dict[str, Any]:
    """Score every unscored open raw deal that passes the gate.

    ``analyzer_kwargs`` are forwarded to ``analyze_deal`` (v6 11-param scorer),
    letting callers pass qualitative signals per batch when known.
    """
    pending = store.list_unscored_open_deals()
    scored_ids: list[str] = []
    skipped: list[dict[str, str]] = []

    for rd in pending:
        decision = evaluate(rd)
        if not decision.should_score:
            skipped.append({"raw_deal_id": rd.id, "name": rd.name, "reason": decision.reason})
            continue

        deal = raw_to_deal(rd)
        result = analyze_deal(deal, **analyzer_kwargs)
        dump = result.model_dump()

        scored = ScoredDeal(
            id="",
            raw_deal_id=rd.id,
            source=rd.source,
            listing_id=rd.listing_id,
            us_eligible=decision.us_eligible,
            trust_level=rd.trust_level,
            gate_reason=decision.reason,
            score_json=json.dumps(dump, default=str),
            scored_at=now_iso(),
        )
        for f in SCORE_FIELDS:
            setattr(scored, f, float(dump.get(f, 0.0) or 0.0))
        store.save_scored_deal(scored)
        scored_ids.append(rd.id)

    return {
        "scored": len(scored_ids),
        "skipped": len(skipped),
        "skipped_detail": skipped,
        "scored_raw_ids": scored_ids,
    }
