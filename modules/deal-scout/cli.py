"""
EVA Deal Scout — pipeline CLI.

Commands
--------
    migrate                       apply schema migrations
    sources                       list configured sources + trust levels
    backfill [--data-dir ...]     import existing JSON datasets into the DB
    source  --source KEY --file F source listings from a JSON payload file
    ingest-ef-closed              pull EF SOLD comps from the public API into
                                  the closed-comps set (paginated + deduped)
    score                         run the gated v6 scorer over pending DB rows
    trends  [--output PATH]       build the trend report + save markdown
    export                        dump the DB as JSON (legacy-compatible)
    add-competitor  --deal-id ... --name ...   attach researched competitor intel
    list-competitors --deal-id ...             list a deal's competitors
    add-case-study  --source-url ... [--snapshot/--analysis JSON]  store a case study
    list-case-studies [--deal-type X]          list case studies

Usage:
    python cli.py migrate --db eva-deal-scout.db
    python cli.py backfill
    python cli.py score
    python cli.py trends --output /home/user/workspace/deal_trend_report_2026-07-16.md
"""

from __future__ import annotations

import argparse
import json
import sys

from backfill import backfill_all
from pipeline import score_pending, source_deals
from sources import list_sources
from store import DEFAULT_DB_PATH, SQLiteDealStore
from trends import build_and_save_report


def _out(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_migrate(store: SQLiteDealStore, args) -> None:
    _out({"applied_migrations": store.migrate()})


def cmd_sources(store: SQLiteDealStore, args) -> None:
    _out(list_sources())


def cmd_backfill(store: SQLiteDealStore, args) -> None:
    store.migrate()
    # --source-dir / --closed-comps-file are the canonical flags; the older
    # --data-dir / --closed-file remain as aliases.
    data_dir = args.source_dir or args.data_dir
    closed_path = args.closed_comps_file or args.closed_file
    _out(backfill_all(store, data_dir=data_dir, closed_path=closed_path))


def cmd_source(store: SQLiteDealStore, args) -> None:
    store.migrate()
    with open(args.file, encoding="utf-8") as fh:
        data = json.load(fh)
    payloads = data.get("deals", data) if isinstance(data, dict) else data
    _out(source_deals(store, args.source, payloads))


def cmd_ingest_ef_closed(store: SQLiteDealStore, args) -> None:
    """Pull Empire Flippers SOLD comps from the public API into closed_comps."""
    from ef_closed_comps import ingest_ef_closed_comps

    if args.closed_comps_source and args.closed_comps_source != "empire_flippers":
        _out({"error": f"unsupported closed-comps source {args.closed_comps_source!r} "
                       "— only 'empire_flippers' is implemented"})
        return
    store.migrate()
    _out(ingest_ef_closed_comps(
        store, per_page=args.per_page, max_pages=args.max_pages))


def cmd_score(store: SQLiteDealStore, args) -> None:
    store.migrate()
    _out(score_pending(store))


def cmd_trends(store: SQLiteDealStore, args) -> None:
    store.migrate()
    report = build_and_save_report(store, output_path=args.output)
    _out({"trend_report_id": report.id, "generated_at": report.generated_at,
          "output_path": args.output, "bytes": len(report.report_md)})


def cmd_export(store: SQLiteDealStore, args) -> None:
    _out(store.export_json())


def cmd_add_competitor(store: SQLiteDealStore, args) -> None:
    store.migrate()
    comp = store.add_competitor(
        deal_id=args.deal_id,
        name=args.name,
        what_they_do=args.description,
        pricing_model=args.pricing,
        url=args.url,
        moat_comparison=args.moat,
        source_url=args.source_url,
        category=args.category,
    )
    _out(comp.model_dump())


def cmd_list_competitors(store: SQLiteDealStore, args) -> None:
    store.migrate()
    comps = [c.model_dump() for c in store.list_competitors(args.deal_id)]
    _out({"deal_id": args.deal_id, "competitors": comps, "count": len(comps)})


def _parse_json_arg(raw: str, label: str, expected: type):
    """Parse a JSON CLI arg into ``expected`` (dict/list); return (value, error)."""
    if not raw:
        return expected(), None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{label} must be valid JSON: {exc}"
    if not isinstance(value, expected):
        return None, f"{label} must be a JSON {expected.__name__}"
    return value, None


def cmd_add_case_study(store: SQLiteDealStore, args) -> None:
    store.migrate()
    snapshot, err = _parse_json_arg(args.snapshot, "--snapshot", dict)
    if err:
        _out({"error": err})
        return
    analysis, err = _parse_json_arg(args.analysis, "--analysis", dict)
    if err:
        _out({"error": err})
        return
    pattern_tags, err = _parse_json_arg(args.pattern_tags, "--pattern-tags", list)
    if err:
        _out({"error": err})
        return
    study = store.add_case_study(
        source_url=args.source_url,
        deal_type=args.deal_type,
        title=args.title,
        deal_id=args.deal_id,
        snapshot=snapshot,
        analysis=analysis,
        pattern_tags=pattern_tags,
        formula_insight=args.formula_insight,
    )
    _out(study.model_dump())


def cmd_list_case_studies(store: SQLiteDealStore, args) -> None:
    store.migrate()
    studies = [s.model_dump() for s in store.list_case_studies(deal_type=args.deal_type)]
    _out({"case_studies": studies, "count": len(studies),
          "deal_type": args.deal_type})


def cmd_wide_source(store: SQLiteDealStore, args) -> None:
    """Attempt a source run across every activated source; log unfetchable ones."""
    from pipeline import wide_source_run

    store.migrate()
    _out(wide_source_run(store))


def cmd_stats(store: SQLiteDealStore, args) -> None:
    """Summary counts + the unified top-10 radar (scored + gate-skipped)."""
    from collections import Counter

    store.migrate()
    raw = store.list_raw_deals()
    open_raw = [r for r in raw if not r.is_closed]
    closed_raw = [r for r in raw if r.is_closed]
    scored = store.list_scored_deals()

    raw_by_source = Counter(r.source for r in open_raw)
    skip_reasons = Counter(r.skip_reason for r in open_raw if r.gate_status == "skipped")

    # Unified radar on a single 0-10 scale: the DB v6 overall_score for gated
    # deals, else the source-carried incoming_score for gate-skipped deals.
    scored_by_raw = {s.raw_deal_id: s for s in scored}
    radar = []
    for r in open_raw:
        s = scored_by_raw.get(r.id)
        if s is not None:
            score, provenance = s.overall_score, "v6_scored"
            buy_vs_build = {
                "recommendation": s.buy_vs_build_recommendation,
                "feasibility": s.build_feasibility,
                "moat_build_years": s.moat_build_years,
                "time_estimate": s.build_time_estimate,
            }
        else:
            # Surfaced by the source-carried score but NOT run through the v6
            # gate/scorer — its rank is not a validated v6 result.
            score, provenance = r.incoming_score, "incoming_score_only (skipped_by_gate)"
            buy_vs_build = None
        radar.append({
            "name": r.name, "source": r.source, "asking_price": r.asking_price,
            "score": round(score, 2), "provenance": provenance,
            "gate_status": r.gate_status, "buy_vs_build": buy_vs_build,
        })
    radar.sort(key=lambda d: d["score"], reverse=True)

    audit_sample = [
        {"raw_deal_id": s.raw_deal_id, "source": s.source, "us_eligible": s.us_eligible,
         "trust_high": s.trust_high, "skip_reason": s.skip_reason,
         "gate_reason": s.gate_reason}
        for s in scored[:5]
    ]

    _out({
        "raw_deals_open_by_source": dict(raw_by_source),
        "raw_deals_open_total": len(open_raw),
        "closed_comps_ingested": len(closed_raw),
        "scored_deals": len(scored),
        "skipped_by_gate": sum(1 for r in open_raw if r.gate_status == "skipped"),
        "skip_reason_breakdown": dict(skip_reasons),
        "source_runs": len(store.list_source_runs()),
        "trend_reports": len(store.conn.execute("SELECT id FROM trend_reports").fetchall()),
        "scored_deals_audit_sample": audit_sample,
        "top_10_radar": radar[:10],
    })


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deal-scout", description="EVA Deal Scout pipeline CLI")
    p.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB path")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate").set_defaults(func=cmd_migrate)
    sub.add_parser("sources").set_defaults(func=cmd_sources)

    bf = sub.add_parser("backfill")
    bf.add_argument("--source-dir", default="", help="dir of open-listing JSON files")
    bf.add_argument("--closed-comps-file", default="", help="closed comps JSON file")
    bf.add_argument("--data-dir", default="deal_scout_data", help="(alias of --source-dir)")
    bf.add_argument("--closed-file", default="closed_deals_dataset.json",
                    help="(alias of --closed-comps-file)")
    bf.set_defaults(func=cmd_backfill)

    so = sub.add_parser("source")
    so.add_argument("--source", required=True)
    so.add_argument("--file", required=True)
    so.set_defaults(func=cmd_source)

    ef = sub.add_parser("ingest-ef-closed",
                        help="pull EF sold comps from the public API into closed_comps")
    ef.add_argument("--closed-comps-source", default="empire_flippers",
                    help="closed-comps source (only 'empire_flippers' is implemented)")
    ef.add_argument("--per-page", type=int, default=100, help="EF API page size")
    ef.add_argument("--max-pages", type=int, default=None,
                    help="cap the number of API pages pulled (default: all)")
    ef.set_defaults(func=cmd_ingest_ef_closed)

    sub.add_parser("score").set_defaults(func=cmd_score)

    tr = sub.add_parser("trends")
    tr.add_argument("--output", default="/home/user/workspace/deal_trend_report_2026-07-16.md")
    tr.set_defaults(func=cmd_trends)

    sub.add_parser("export").set_defaults(func=cmd_export)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("wide-source").set_defaults(func=cmd_wide_source)

    ac = sub.add_parser("add-competitor",
                        help="attach a researched competitor to a deal")
    ac.add_argument("--deal-id", required=True, help="raw_deal id to link to")
    ac.add_argument("--name", required=True, help="competitor company name")
    ac.add_argument("--description", default="", help="what they do")
    ac.add_argument("--pricing", default="", help="pricing model")
    ac.add_argument("--url", default="", help="competitor website")
    ac.add_argument("--source-url", default="", help="where this intel came from")
    ac.add_argument("--moat", default="", help="how this deal compares vs the competitor")
    ac.add_argument("--category", default=None, help="competitor category")
    ac.set_defaults(func=cmd_add_competitor)

    lc = sub.add_parser("list-competitors",
                        help="list competitors linked to a deal")
    lc.add_argument("--deal-id", required=True, help="raw_deal id")
    lc.set_defaults(func=cmd_list_competitors)

    cs = sub.add_parser("add-case-study",
                        help="store a 4-lens deal case study (compounding intel)")
    cs.add_argument("--source-url", required=True, help="source URL (upsert key)")
    cs.add_argument("--deal-type", default="within_box",
                    choices=["within_box", "juggernaut_study", "build_vs_buy_reference"],
                    help="case study type")
    cs.add_argument("--title", default="", help="case study / deal title")
    cs.add_argument("--deal-id", default=None,
                    help="raw_deal id (omit for out-of-box studies)")
    cs.add_argument("--snapshot", default="",
                    help="JSON object of deal metrics (asking, revenue, profit, "
                         "margin, multiples, founded, customers, team, location, usp)")
    cs.add_argument("--analysis", default="",
                    help="JSON object of the 4 lenses (lens1_box_fit, "
                         "lens2_what_selling, lens3_juggernaut_arc, lens4_build_vs_buy)")
    cs.add_argument("--pattern-tags", default="", help="JSON array of pattern tags")
    cs.add_argument("--formula-insight", default="", help="the compounding formula insight")
    cs.set_defaults(func=cmd_add_case_study)

    ls = sub.add_parser("list-case-studies",
                        help="list stored case studies (filter by type)")
    ls.add_argument("--deal-type", default=None,
                    choices=["within_box", "juggernaut_study", "build_vs_buy_reference"],
                    help="filter by case study type")
    ls.set_defaults(func=cmd_list_case_studies)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = SQLiteDealStore(args.db)
    try:
        args.func(store, args)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
