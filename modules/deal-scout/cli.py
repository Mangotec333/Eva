"""
EVA Deal Scout — pipeline CLI.

Commands
--------
    migrate                       apply schema migrations
    sources                       list configured sources + trust levels
    backfill [--data-dir ...]     import existing JSON datasets into the DB
    source  --source KEY --file F source listings from a JSON payload file
    score                         run the gated v6 scorer over pending DB rows
    trends  [--output PATH]       build the trend report + save markdown
    export                        dump the DB as JSON (legacy-compatible)

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
            score, basis = s.overall_score, "scored"
        else:
            score, basis = r.incoming_score, "incoming"
        radar.append({
            "name": r.name, "source": r.source, "asking_price": r.asking_price,
            "score": round(score, 2), "basis": basis, "gate_status": r.gate_status,
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

    sub.add_parser("score").set_defaults(func=cmd_score)

    tr = sub.add_parser("trends")
    tr.add_argument("--output", default="/home/user/workspace/deal_trend_report_2026-07-16.md")
    tr.set_defaults(func=cmd_trends)

    sub.add_parser("export").set_defaults(func=cmd_export)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
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
