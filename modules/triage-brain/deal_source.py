"""
EVA Diracatron — deal-scout candidate source (open acquisition doors)
=====================================================================

Diracatron's job on ``/triage/run`` is to rank every *open door*. The biggest
category of open door is a **scored + gated acquisition target** sitting in the
deal-scout SQLite ``DealStore`` (``modules/deal-scout/eva-deal-scout.db``).

This source reads that DB directly with stdlib ``sqlite3`` (no pydantic import,
no network — so tests stay offline and a missing/locked DB degrades to an empty
list, never a crash). It lifts only the deals that actually *matter*:

  * ``gate_status = 'scored'`` and ``us_eligible = 1`` — deals the scoring gate
    passed (real, actionable open doors, not skipped noise),
  * still **available** (not closed / sold),

and normalises each into a ``deal_score_threshold`` triage candidate carrying
the ``overall_score`` and the **buy-vs-build** recommendation in its payload, so
the first-principles ranker can stack-rank them and the dispatch brain can act.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

import diracatron

# Config-file-primary is overkill for a sibling DB path; env override with a
# sensible default beside the deal-scout module (its DEFAULT_DB_PATH is the
# relative "eva-deal-scout.db", created in the module's CWD).
DEAL_SCOUT_DB = os.environ.get(
    "DEAL_SCOUT_DB",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "deal-scout",
                 "eva-deal-scout.db"),
)

# A deal must clear this composite score (0–10) to be treated as a live door
# worth ranking; below it, it is tracked by deal-scout but not pushed at Eva.
MIN_OPEN_DOOR_SCORE = float(os.environ.get("EVA_DEAL_MIN_SCORE", "5.0"))


class DealScoutSource:
    """Read-only view of deal-scout's scored+gated open doors as candidates."""

    def __init__(self, db_path: str = DEAL_SCOUT_DB,
                 min_score: float = MIN_OPEN_DOOR_SCORE) -> None:
        self.db_path = db_path
        self.min_score = min_score

    def candidates(self) -> list[dict]:
        if not os.path.exists(self.db_path):
            return []
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error:
            return []
        try:
            rows = conn.execute(
                """
                SELECT s.raw_deal_id, s.overall_score, s.gate_reason,
                       s.buy_vs_build_recommendation, s.buy_vs_build_rationale,
                       s.build_feasibility, s.moat_build_years,
                       r.name, r.source, r.url, r.asking_price, r.monthly_net,
                       r.market_status, r.is_closed
                FROM scored_deals s
                JOIN raw_deals r ON r.id = s.raw_deal_id
                WHERE s.us_eligible = 1
                  AND COALESCE(r.is_closed, 0) = 0
                  AND COALESCE(r.market_status, 'available') = 'available'
                  AND s.overall_score >= ?
                ORDER BY s.overall_score DESC
                """,
                (self.min_score,),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()

        out: list[dict] = []
        for r in rows:
            name = r["name"] or r["raw_deal_id"]
            score = float(r["overall_score"] or 0.0)
            rec = (r["buy_vs_build_recommendation"] or "buy").lower()
            out.append({
                "kind": diracatron.KIND_DEAL_SCORE,
                "entity_id": r["raw_deal_id"],
                "summary": f"Acquisition door: {name} "
                           f"(score {score:.1f}/10, {rec})",
                "source": f"deal-scout:{r['source'] or 'unknown'}",
                "payload": {
                    "score": score,
                    "name": name,
                    "url": r["url"] or "",
                    "asking_price": float(r["asking_price"] or 0.0),
                    "monthly_net": float(r["monthly_net"] or 0.0),
                    "buy_vs_build": rec,
                    "buy_vs_build_rationale": r["buy_vs_build_rationale"] or "",
                    "build_feasibility": r["build_feasibility"] or "",
                    "moat_build_years": float(r["moat_build_years"] or 0.0),
                    "gate_reason": r["gate_reason"] or "",
                    "revenue_path": "acquire_cashflow",
                },
            })
        return out


class MarketSignalSource:
    """Optional market-signal / revenue-path feed as triage candidates.

    Signals are provided as a JSON array (env ``EVA_MARKET_SIGNALS_FILE`` or a
    literal in ``EVA_MARKET_SIGNALS``); absent both, this contributes nothing.
    Each signal ``{summary, score?, urgent?, revenue_path?}`` becomes a
    ``revenue_leak`` candidate so first-principles ranking weighs money paths
    alongside deals. Kept dead-simple and offline-safe on purpose.
    """

    def __init__(self, signals: Optional[list[dict]] = None) -> None:
        self._signals = signals if signals is not None else self._load()

    @staticmethod
    def _load() -> list[dict]:
        import json
        path = os.environ.get("EVA_MARKET_SIGNALS_FILE", "")
        blob = os.environ.get("EVA_MARKET_SIGNALS", "")
        try:
            if path and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            elif blob:
                data = json.loads(blob)
            else:
                return []
        except Exception:  # noqa: BLE001 — malformed feed is non-fatal
            return []
        return data if isinstance(data, list) else []

    def candidates(self) -> list[dict]:
        out: list[dict] = []
        for i, sig in enumerate(self._signals):
            if not isinstance(sig, dict):
                continue
            payload = {"score": 0, "revenue_path": "unknown",
                       **{k: v for k, v in sig.items()
                          if k not in {"entity_id", "summary"}}}
            payload["urgent"] = bool(payload.get("urgent"))
            out.append({
                "kind": diracatron.KIND_REVENUE_LEAK,
                "entity_id": sig.get("entity_id") or f"signal-{i}",
                "summary": sig.get("summary") or "Market signal / revenue path",
                "source": "market-signal",
                "payload": payload,
            })
        return out


__all__ = ["DealScoutSource", "MarketSignalSource", "DEAL_SCOUT_DB"]
