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


def _usable(v: Any) -> bool:
    """A metric value counts only if it is a positive number.

    Missing (``None``/blank) and ``0`` are treated as *not populated* — none of
    multiple / age / owner-hours have a meaningful zero, so a 0 here means the
    source simply did not carry the field.
    """
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def _stat(values: list[Any], total: Optional[int] = None) -> dict[str, Any]:
    """Median over populated values only, plus coverage (n populated / total)."""
    vals = [v for v in values if _usable(v)]
    return {
        "median": round(statistics.median(vals), 2) if vals else None,
        "n": len(vals),
        "total": len(values) if total is None else total,
    }


def _multiple_values(deals: list[RawDeal]) -> list[float]:
    """Annual multiple per deal: explicit when present, else derived.

    Derived = price / (monthly_net * 12) when both are populated — recovers a
    multiple for closed comps that carry a sale price + monthly profit but no
    explicit ``multiple`` field.
    """
    out: list[float] = []
    for d in deals:
        if _usable(d.annual_multiple):
            out.append(round(d.annual_multiple, 2))
            continue
        price = d.sold_price if (d.is_closed and _usable(d.sold_price)) else d.asking_price
        if _usable(price) and _usable(d.monthly_net):
            out.append(round(price / (d.monthly_net * 12.0), 2))
    return out


def _confidence(n: int) -> str:
    if n == 0:
        return "not available"
    if n < 10:
        return "low confidence"
    if n < 30:
        return "medium confidence"
    return "high confidence"


def _median(values: list[float]) -> float:
    """Legacy numeric-median helper (missing-aware) kept for the price-band path."""
    stat = _stat(values)
    return stat["median"] if stat["median"] is not None else 0.0


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


def _profile(deals: list[RawDeal]) -> dict[str, Any]:
    """Aggregate moat/AI-relevant signals across a cohort, with coverage."""
    n = len(deals)
    return {
        "count": n,
        "multiple": _stat(_multiple_values(deals), total=n),
        "monthly_net": _stat([d.monthly_net for d in deals]),
        "age_years": _stat([d.age_years for d in deals]),
        "owner_hours": _stat([d.owner_hours_per_week for d in deals]),
    }


def _infer_sale_drivers(sold: list[RawDeal], unsold: list[RawDeal]) -> list[str]:
    """Heuristic comparison of sold vs unsold cohorts → plain-language drivers."""
    drivers: list[str] = []
    if not sold:
        return ["No closed comps ingested yet — sale drivers cannot be inferred."]

    sold_mult = _stat(_multiple_values(sold), total=len(sold))
    open_mult = _stat(_multiple_values(unsold), total=len(unsold))
    if sold_mult["median"] is not None and open_mult["median"] is not None:
        sm, om = sold_mult["median"], open_mult["median"]
        conf = f"(sold n={sold_mult['n']}/{sold_mult['total']}, {_confidence(sold_mult['n'])})"
        if sm < om:
            drivers.append(
                f"Sold deals cleared at a *lower* median multiple ({sm}x) than "
                f"open listings ({om}x) — pricing discipline drives closure {conf}."
            )
        else:
            drivers.append(
                f"Sold deals commanded a median multiple of {sm}x vs {om}x "
                f"open — quality/scarcity commanded a premium {conf}."
            )

    sold_hours = _stat([d.owner_hours_per_week for d in sold])
    open_hours = _stat([d.owner_hours_per_week for d in unsold])
    if (sold_hours["median"] is not None and open_hours["median"] is not None
            and sold_hours["median"] < open_hours["median"]):
        drivers.append(
            f"Sold businesses required fewer owner-hours/week (median "
            f"{sold_hours['median']} vs {open_hours['median']}) — lower "
            "operational burden accelerates sale."
        )

    sold_age = _stat([d.age_years for d in sold])
    if sold_age["median"] is not None:
        drivers.append(
            f"Median age of sold businesses is {sold_age['median']} years "
            f"(n={sold_age['n']}/{sold_age['total']}) — track record matters to buyers."
        )

    cat_counts = Counter(d.category for d in sold)
    if cat_counts:
        top_cat, top_n = cat_counts.most_common(1)[0]
        drivers.append(f"Most-transacted category among closed comps: {top_cat} ({top_n} deals).")

    return drivers


def _buy_vs_build_summary(store: DealStore) -> dict[str, Any]:
    """Aggregate the buy-vs-build assessment across scored deals.

    A high median ``moat_build_years`` is the deal-killer for the build path,
    so buy-heavy recommendations indicate a market where moats favor acquiring.
    """
    scored = store.list_scored_deals() if hasattr(store, "list_scored_deals") else []
    if not scored:
        return {"scored": 0, "recommendation_counts": {}, "feasibility_counts": {},
                "moat_build_years": {"median": None, "n": 0, "total": 0}}

    rec = Counter(s.buy_vs_build_recommendation for s in scored if s.buy_vs_build_recommendation)
    feas = Counter(s.build_feasibility for s in scored if s.build_feasibility)
    years = _stat([s.moat_build_years for s in scored], total=len(scored))
    return {
        "scored": len(scored),
        "recommendation_counts": dict(rec),
        "feasibility_counts": dict(feas),
        "moat_build_years": years,
    }


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

    mult_sold = _stat(_multiple_values(sold), total=len(sold))
    mult_open = _stat(_multiple_values(open_deals), total=len(open_deals))
    profile_sold = _profile(sold)
    profile_unsold = _profile(open_deals)

    return {
        "generated_at": now_iso(),
        "totals": {"all": len(all_deals), "open": len(open_deals), "sold": len(sold)},
        # Backward-compatible numeric medians (0.0 when no populated values);
        # `multiple_coverage` carries the n/total + confidence behind them.
        "median_multiple": {
            "sold": mult_sold["median"] if mult_sold["median"] is not None else 0.0,
            "open": mult_open["median"] if mult_open["median"] is not None else 0.0,
        },
        "multiple_coverage": {"sold": mult_sold, "open": mult_open},
        "coverage": {
            "sold": {"multiple": mult_sold, "monthly_net": profile_sold["monthly_net"],
                     "age_years": profile_sold["age_years"],
                     "owner_hours": profile_sold["owner_hours"]},
            "open": {"multiple": mult_open, "monthly_net": profile_unsold["monthly_net"],
                     "age_years": profile_unsold["age_years"],
                     "owner_hours": profile_unsold["owner_hours"]},
        },
        "by_source": dict(by_source),
        "by_category": dict(by_category),
        "price_bands": dict(price_bands),
        "profile_sold": profile_sold,
        "profile_unsold": profile_unsold,
        "sale_drivers": _infer_sale_drivers(sold, open_deals),
        "buy_vs_build": _buy_vs_build_summary(store),
    }


def _fmt_cov(stat: dict[str, Any]) -> str:
    return f"n={stat['n']}/{stat['total']}, {_confidence(stat['n'])}"


def _fmt_mult(stat: dict[str, Any]) -> str:
    if stat["median"] is None:
        return "not available"
    return f"{stat['median']}x"


def _fmt_metric(stat: dict[str, Any], *, money: bool = False, suffix: str = "") -> str:
    """Format a stat's median for the profile table; 'not available' when empty."""
    if stat["median"] is None:
        return f"not available (n=0/{stat['total']})"
    val = f"${stat['median']:,.0f}" if money else f"{stat['median']}{suffix}"
    return val


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

    mc = stats["multiple_coverage"]
    L.append("## Median Annual Multiple")
    L.append("")
    L.append("Missing / null / zero values are excluded; closed-comp multiples are "
             "derived from sale price ÷ (monthly net × 12) when not stated explicitly.")
    L.append("")
    L.append("| Cohort | Median multiple | Coverage |")
    L.append("|--------|-----------------|----------|")
    L.append(f"| Sold   | {_fmt_mult(mc['sold'])} | {_fmt_cov(mc['sold'])} |")
    L.append(f"| Open   | {_fmt_mult(mc['open'])} | {_fmt_cov(mc['open'])} |")
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
    L.append(f"| Median multiple | {_fmt_metric(ps['multiple'], suffix='x')} | {_fmt_metric(pu['multiple'], suffix='x')} |")
    L.append(f"| Median monthly net | {_fmt_metric(ps['monthly_net'], money=True)} | {_fmt_metric(pu['monthly_net'], money=True)} |")
    L.append(f"| Median age (yrs) | {_fmt_metric(ps['age_years'])} | {_fmt_metric(pu['age_years'])} |")
    L.append(f"| Median owner-hours/wk | {_fmt_metric(ps['owner_hours'])} | {_fmt_metric(pu['owner_hours'])} |")
    L.append("")

    cov = stats["coverage"]
    L.append("## Data Coverage / Confidence")
    L.append("")
    L.append("Populated (non-null, non-zero) values per metric, per cohort.")
    L.append("")
    L.append("| Metric | Sold (n/total) | Open (n/total) |")
    L.append("|--------|----------------|----------------|")
    for key, label in (("multiple", "Annual multiple"), ("monthly_net", "Monthly net"),
                       ("age_years", "Age (yrs)"), ("owner_hours", "Owner-hours/wk")):
        L.append(f"| {label} | {_fmt_cov(cov['sold'][key])} | {_fmt_cov(cov['open'][key])} |")
    L.append("")

    bvb = stats.get("buy_vs_build")
    if bvb:
        L.append("## Buy vs Build (scored deals)")
        L.append("")
        if bvb["scored"] == 0:
            L.append("No scored deals yet — buy-vs-build assessment unavailable.")
        else:
            years = bvb["moat_build_years"]
            median = "not available" if years["median"] is None else f"{years['median']} yrs"
            L.append(f"Assessed across {bvb['scored']} scored deals. Median years to "
                     f"rebuild a defensible moat: **{median}** "
                     f"({_fmt_cov(years)}) — high years = the deal-killer for building.")
            L.append("")
            L.append("| Recommendation | Deals |")
            L.append("|----------------|------:|")
            for rec in ("buy", "either", "build"):
                if rec in bvb["recommendation_counts"]:
                    L.append(f"| {rec} | {bvb['recommendation_counts'][rec]} |")
            L.append("")
            L.append("| Build feasibility | Deals |")
            L.append("|-------------------|------:|")
            for feas in ("low", "medium", "high"):
                if feas in bvb["feasibility_counts"]:
                    L.append(f"| {feas} | {bvb['feasibility_counts'][feas]} |")
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
