"""
EVA Deal Analyzer Agent — Gate 1 "radar" (free, deterministic pre-filter)
=========================================================================

The CHEAPEST gate in the cost cascade: four free heuristic checks that drop
obviously-unfit deals BEFORE any (even free) enrichment or v7 scoring is spent on
them. This is pure Python — no network, no LLM, no cost — and it NEVER raises:
any unexpected error inside a check degrades to "pass" (fail OPEN) so a radar bug
can never silently drop a good deal or crash the loop.

    radar_filter(deal, config=None) -> (passed: bool, reasons: list[str])

Checks (in order; data_completeness short-circuits because the later numeric
checks need the numbers):

  a) data_completeness  — revenue, profit, multiple present & numeric  [REQUIRED]
  b) category_niche_fit — category matches an allowed set               [REQUIRED]
  c) price_range_band   — profit >= min_profit AND multiple <= max_multiple
  d) red_flag_screen    — PBN / trademark risk / single-customer dependency
                          (>40% from one client) / declining trend
                          (best-effort; UNKNOWN fields fail OPEN / pass)

Thresholds + the allowed-category set come from config/cost_gates.yaml (via
cost_gate.load_config) — no magic numbers here.
"""

from __future__ import annotations

from typing import Any, Optional

from cost_gate import load_config

# Field aliases: deals arrive as DealV7 / DealV7.model_dump() / raw dicts. The
# canonical acquisition fields on the model are monthly_net (profit) and
# annual_multiple (multiple); "revenue" has no dedicated field, so monthly_net
# doubles as the revenue proxy for the presence check.
_PROFIT_KEYS = ("profit", "monthly_net")
_MULTIPLE_KEYS = ("multiple", "annual_multiple")
_REVENUE_KEYS = ("revenue", "monthly_revenue", "annual_revenue", "monthly_net")
_CATEGORY_KEYS = ("category_v2", "category")

# Best-effort single-customer-dependency signal (>40% revenue from one client).
_CONCENTRATION_KEYS = (
    "single_customer_pct", "top_customer_revenue_pct", "customer_concentration_pct",
)
_MAX_SINGLE_CUSTOMER_PCT = 40.0

# Textual red-flag markers scanned in the deal's free-text notes.
_PBN_MARKERS = ("pbn", "private blog network")
_TRADEMARK_MARKERS = ("trademark", "™", "cease and desist", "infringement")
_DECLINE_MARKERS = ("declining", "downtrend", "revenue falling", "shrinking")


def _get(deal: Any, key: str, default: Any = None) -> Any:
    if deal is None:
        return default
    if isinstance(deal, dict):
        return deal.get(key, default)
    return getattr(deal, key, default)


def _first_present(deal: Any, keys: tuple[str, ...]) -> Any:
    """Return the first non-None value among ``keys`` (empty string counts as absent)."""
    for k in keys:
        val = _get(deal, k)
        if val is not None and val != "":
            return val
    return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _notes(deal: Any) -> str:
    return str(_get(deal, "notes", "") or "").lower()


# ---------------------------------------------------------------------------
# Individual checks — each returns (ok: bool, reason: str|None)
# ---------------------------------------------------------------------------

def _check_data_completeness(deal: Any) -> tuple[bool, Optional[str]]:
    """REQUIRED: revenue, profit, multiple must be present AND numeric."""
    missing = []
    for label, keys in (("revenue", _REVENUE_KEYS), ("profit", _PROFIT_KEYS),
                        ("multiple", _MULTIPLE_KEYS)):
        val = _first_present(deal, keys)
        if val is None or _as_float(val) is None:
            missing.append(label)
    if missing:
        return False, f"data_completeness: missing/non-numeric {', '.join(missing)}"
    return True, None


def _check_category_niche_fit(deal: Any, allowed: list[str]) -> tuple[bool, Optional[str]]:
    """REQUIRED: category matches an allowed one (exact or normalized substring)."""
    raw = _first_present(deal, _CATEGORY_KEYS)
    if raw is None:
        return False, "category_niche_fit: category missing (required)"
    cat = str(raw).strip().lower()
    for allowed_cat in allowed:
        a = str(allowed_cat).strip().lower()
        if a and (a == cat or a in cat or cat in a):
            return True, None
    return False, f"category_niche_fit: '{raw}' not in allowed {allowed}"


def _check_price_range_band(deal: Any, min_profit: float,
                            max_multiple: float) -> tuple[bool, Optional[str]]:
    """profit >= min_profit AND multiple <= max_multiple."""
    profit = _as_float(_first_present(deal, _PROFIT_KEYS))
    multiple = _as_float(_first_present(deal, _MULTIPLE_KEYS))
    if profit is not None and profit < min_profit:
        return False, f"price_range_band: profit {profit:g} < min_profit {min_profit:g}"
    if multiple is not None and multiple > max_multiple:
        return False, f"price_range_band: multiple {multiple:g} > max_multiple {max_multiple:g}"
    return True, None


def _check_red_flag_screen(deal: Any) -> tuple[bool, Optional[str]]:
    """Best-effort red-flag heuristics. UNKNOWN fields fail OPEN (pass)."""
    notes = _notes(deal)
    flags: list[str] = []

    if any(m in notes for m in _PBN_MARKERS):
        flags.append("PBN")
    if any(m in notes for m in _TRADEMARK_MARKERS):
        flags.append("trademark risk")

    # single-customer dependency: explicit numeric field wins; else a notes hint.
    concentration = _as_float(_first_present(deal, _CONCENTRATION_KEYS))
    if concentration is not None and concentration > _MAX_SINGLE_CUSTOMER_PCT:
        flags.append(f"single-customer dependency ({concentration:g}%)")
    elif "single customer" in notes or "one client" in notes:
        flags.append("single-customer dependency")

    trend = str(_get(deal, "revenue_trend", "") or _get(deal, "trend", "") or "").lower()
    if trend == "declining" or any(m in notes for m in _DECLINE_MARKERS):
        flags.append("declining trend")

    if flags:
        return False, f"red_flag_screen: {', '.join(flags)}"
    return True, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def radar_filter(deal: Any, config: Optional[dict] = None) -> tuple[bool, list[str]]:
    """Run the four Gate-1 checks. Returns (passed, reasons).

    ``passed`` is True only when every check passes; ``reasons`` lists each
    failing check's explanation (empty when passed). data_completeness
    short-circuits (later numeric checks need the numbers); the remaining checks
    all run so the caller gets a full failure trace for logging. Never raises.
    """
    cfg = config or load_config()
    band = cfg.get("price_band", {}) or {}
    min_profit = float(band.get("min_profit_usd", 1000))
    max_multiple = float(band.get("max_multiple", 5.0))
    allowed = list(cfg.get("allowed_categories", []) or [])

    reasons: list[str] = []
    try:
        ok, reason = _check_data_completeness(deal)
        if not ok:
            return False, [reason] if reason else ["data_completeness: failed"]

        for ok, reason in (
            _check_category_niche_fit(deal, allowed),
            _check_price_range_band(deal, min_profit, max_multiple),
            _check_red_flag_screen(deal),
        ):
            if not ok and reason:
                reasons.append(reason)
    except Exception as exc:  # noqa: BLE001 — radar must NEVER break the loop
        # Fail OPEN on an unexpected internal error: pass with a diagnostic note
        # rather than dropping a possibly-good deal or crashing.
        return True, [f"radar_error(fail_open): {exc}"]

    return (len(reasons) == 0), reasons
