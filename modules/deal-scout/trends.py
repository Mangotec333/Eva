"""
EVA Deal Scout — market-trend analyzer.

Consumes ``raw_deals`` (open + closed comps) from the store and produces:

  * a structured stats dict (sold vs open by source/category, median multiple,
    price bands, owner-hours, moat/AI profile of sold vs unsold, inferred sale
    drivers), and
  * a human-readable markdown report saved to ``trend_reports`` and, optionally,
    to disk.

Closed comps are ingested for ALL geographies (no US filter), so trends reflect
the whole market, not just US-eligible deals.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from typing import Any, Optional

from pipeline_models import RawDeal, TrendReport, now_iso
from store import DealStore


def _median(values: list[float]) -> float:
    vals = [v for v in values if v]
    return round(statistics.median(vals), 2) if vals else 0.0


def _price_band(price: float) -> str:
    if price <= 0:
        return "unknown"
    if price < 50_000:
        return "<$50k"
    if price < 150_000:
        return "$50k–$150k"
    if price < 500_000:
        return "$150k–$500k"
    if price < 1_000_000:
        return "$500k–$1M"
    return "$1M+"


def _profile(deals: list[RawDeal]) -> dict[str, float]:
    """Aggregate moat/AI-relevant signals across a cohort of deals."""
    if not deals:
        return {"count": 0, "median_multiple": 0.0, "median_monthly_net": 0.0,
                "median_age_years": 0.0, "median_owner_hours": 0.0}
    return {
        "count": len(deals),
        "median_multiple": _median([d.annual_multiple for d in deals]),
        "median_monthly_net": _median([d.monthly_net for d in deals]),
        "median_age_years": _median([d.age_years for d in deals]),
        "median_owner_hours": _median([d.owner_hours_per_week for d in deals]),
    }


def _infer_sale_drivers(sold: list[RawDeal], unsold: list[RawDeal]) -> list[str]:
    """Heuristic comparison of sold vs unsold cohorts → plain-language drivers."""
    drivers: list[str] = []
    if not sold:
        return ["No closed comps ingested yet — sale drivers cannot be inferred."]

    sold_mult = _median([d.annual_multiple for d in sold])
    open_mult = _median([d.annual_multiple for d in unsold]) if unsold else 0.0
    if sold_mult and open_mult:
        if sold_mult < open_mult:
            drivers.append(
                f"Sold deals cleared at a *lower* median multiple ({sold_mult}x) than "
                f"open listings ({open_mult}x) — pricing discipline drives closure."
            )
        else:
            drivers.append(
                f"Sold deals commanded a median multiple of {sold_mult}x vs {open_mult}x "
                "open — quality/scarcity commanded a premium."
            )

    sold_hours = _median([d.owner_hours_per_week for d in sold])
    open_hours = _median([d.owner_hours_per_week for d in unsold]) if unsold else 0.0
    if sold_hours and open_hours and sold_hours < open_hours:
        drivers.append(
            f"Sold businesses required fewer owner-hours/week (median {sold_hours} vs "
            f"{open_hours}) — lower operational burden accelerates sale."
        )

    sold_age = _median([d.age_years for d in sold])
    if sold_age:
        drivers.append(f"Median age of sold businesses is {sold_age} years — track record matters to buyers.")

    cat_counts = Counter(d.category for d in sold)
    if cat_counts:
        top_cat, top_n = cat_counts.most_common(1)[0]
        drivers.append(f"Most-transacted category among closed comps: {top_cat} ({top_n} deals).")

    return drivers


def analyze_trends(store: DealStore) -> dict[str, Any]:
    """Compute the full trend stats dict from stored raw deals."""
    all_deals = store.list_raw_deals()
    sold = [d for d in all_deals if d.is_closed]
    open_deals = [d for d in all_deals if not d.is_closed]

    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"open": 0, "sold": 0})
    for d in all_deals:
        by_source[d.source]["sold" if d.is_closed else "open"] += 1

    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"open": 0, "sold": 0})
    for d in all_deals:
        by_category[d.category]["sold" if d.is_closed else "open"] += 1

    price_bands: dict[str, dict[str, int]] = defaultdict(lambda: {"open": 0, "sold": 0})
    for d in all_deals:
        band = _price_band(d.sold_price if d.is_closed and d.sold_price else d.asking_price)
        price_bands[band]["sold" if d.is_closed else "open"] += 1

    return {
        "generated_at": now_iso(),
        "totals": {"all": len(all_deals), "open": len(open_deals), "sold": len(sold)},
        "median_multiple": {
            "sold": _median([d.annual_multiple for d in sold]),
            "open": _median([d.annual_multiple for d in open_deals]),
        },
        "by_source": dict(by_source),
        "by_category": dict(by_category),
        "price_bands": dict(price_bands),
        "profile_sold": _profile(sold),
        "profile_unsold": _profile(open_deals),
        "sale_drivers": _infer_sale_drivers(sold, open_deals),
    }


def render_markdown(stats: dict[str, Any], title: str = "EVA Deal Scout — Market Trend Report") -> str:
    """Render the stats dict into a markdown report."""
    L: list[str] = []
    L.append(f"# {title}")
    L.append("")
    L.append(f"_Generated: {stats['generated_at']}_")
    L.append("")
    t = stats["totals"]
    L.append(f"**Corpus:** {t['all']} deals — {t['open']} open, {t['sold']} closed comps "
             "(closed comps span all geographies).")
    L.append("")

    mm = stats["median_multiple"]
    L.append("## Median Annual Multiple")
    L.append("")
    L.append("| Cohort | Median multiple |")
    L.append("|--------|-----------------|")
    L.append(f"| Sold   | {mm['sold']}x |")
    L.append(f"| Open   | {mm['open']}x |")
    L.append("")

    L.append("## Sold vs Open by Source")
    L.append("")
    L.append("| Source | Open | Sold |")
    L.append("|--------|-----:|-----:|")
    for src, c in sorted(stats["by_source"].items()):
        L.append(f"| {src} | {c['open']} | {c['sold']} |")
    L.append("")

    L.append("## Sold vs Open by Category")
    L.append("")
    L.append("| Category | Open | Sold |")
    L.append("|----------|-----:|-----:|")
    for cat, c in sorted(stats["by_category"].items()):
        L.append(f"| {cat} | {c['open']} | {c['sold']} |")
    L.append("")

    L.append("## Price Bands")
    L.append("")
    L.append("| Band | Open | Sold |")
    L.append("|------|-----:|-----:|")
    order = ["<$50k", "$50k–$150k", "$150k–$500k", "$500k–$1M", "$1M+", "unknown"]
    bands = stats["price_bands"]
    for band in order:
        if band in bands:
            L.append(f"| {band} | {bands[band]['open']} | {bands[band]['sold']} |")
    L.append("")

    ps, pu = stats["profile_sold"], stats["profile_unsold"]
    L.append("## Moat / AI Profile — Sold vs Unsold")
    L.append("")
    L.append("| Metric | Sold | Unsold |")
    L.append("|--------|-----:|-------:|")
    L.append(f"| Count | {ps['count']} | {pu['count']} |")
    L.append(f"| Median multiple | {ps['median_multiple']}x | {pu['median_multiple']}x |")
    L.append(f"| Median monthly net | ${ps['median_monthly_net']:,.0f} | ${pu['median_monthly_net']:,.0f} |")
    L.append(f"| Median age (yrs) | {ps['median_age_years']} | {pu['median_age_years']} |")
    L.append(f"| Median owner-hours/wk | {ps['median_owner_hours']} | {pu['median_owner_hours']} |")
    L.append("")

    L.append("## Inferred Sale Drivers")
    L.append("")
    for d in stats["sale_drivers"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L)


def build_and_save_report(
    store: DealStore,
    *,
    output_path: Optional[str] = None,
    title: str = "EVA Deal Scout — Market Trend Report",
) -> TrendReport:
    """Compute trends, persist a TrendReport row, and optionally write to disk."""
    stats = analyze_trends(store)
    md = render_markdown(stats, title=title)
    report = TrendReport(
        id="",
        title=title,
        report_md=md,
        stats_json=json.dumps(stats, default=str),
        generated_at=stats["generated_at"],
    )
    store.save_trend_report(report)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(md)
    return report
