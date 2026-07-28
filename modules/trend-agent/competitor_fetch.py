"""
EVA Trend Agent — Competitor Scan fetcher (plain HTTP, zero LLM cost)
======================================================================

Builds one month's snapshot of https://agent.distributedapps.ai/directory for
the search terms that describe EVA's niche, and writes it to
``cases/competitor_scan_YYYY-MM.json`` in ``CompetitorScanRunInput`` shape for
competitor_scan_engine.py to diff.

There is deliberately NO LLM call anywhere in this file — it is
``requests`` + BeautifulSoup + regex only, so a monthly run costs ~$0 in
ongoing credits. The noise vocabulary is imported from
competitor_scan_engine.py rather than restated here, so the fetch filter and
the verdict rule can never drift apart.

Honest-failure contract (matters for a scheduled job): if the directory cannot
be reached, or a site redesign means zero cards parse, this script does NOT
overwrite an existing snapshot with an empty one and exits non-zero. Silently
writing an empty month would make every prior listing look like it vanished and
every listing next month look brand new — i.e. a fake ALERT. Loud failure is
the safer default.

Usage:
    python3 competitor_fetch.py                 # writes cases/competitor_scan_<this month>.json
    python3 competitor_fetch.py --dry-run       # parse + report, write nothing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from competitor_models import CompetitorEntry, CompetitorScanRunInput
from competitor_scan_engine import CASES_DIR, find_previous_snapshot, is_noise

DIRECTORY_URL = "https://agent.distributedapps.ai/directory"

# The niche EVA actually competes in: buy-side deal sourcing + underwriting
# automation for acquirers (PE / ETA / family offices).
SEARCH_TERMS = [
    "deal sourcing",
    "M&A",
    "merger",
    "underwriting",
    "acquisition financing",
    "deal flow",
    "private equity deal",
]

REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.0  # be a polite crawler; 7 terms/month is trivial load
USER_AGENT = "EVA-trend-agent competitor-scan (+https://github.com/Mangotec333/Eva)"

# Directory detail links look like /agent/<slug> or /directory/<slug>.
_DETAIL_HREF_RE = re.compile(r"^/?(?:agent|agents|directory)/[^/?#]+", re.IGNORECASE)
_AIVSS_RE = re.compile(r"AIVSS[^0-9]{0,24}(\d{1,2}(?:\.\d+)?)", re.IGNORECASE)
_SCORE_RE = re.compile(r"score[^0-9]{0,12}(\d{1,2}(?:\.\d+)?)", re.IGNORECASE)


def current_scan_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def fetch_term(term: str, session: requests.Session) -> str:
    """GET the directory filtered by one search term. Raises on HTTP error so
    main() can count the failure honestly."""
    resp = session.get(
        DIRECTORY_URL,
        params={"q": term},
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.text


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _absolute(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return "https://agent.distributedapps.ai/" + href.lstrip("/")


def _aivss_from(text: str) -> float | None:
    for pattern in (_AIVSS_RE, _SCORE_RE):
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def parse_cards(html: str, term: str, scan_date: str) -> list[CompetitorEntry]:
    """Extract agent listings from one directory results page.

    Cards are located by their detail-page anchor (the only structural feature
    stable enough to rely on); name/category/description/AIVSS are read from
    the anchor's enclosing card element.
    """
    soup = BeautifulSoup(html, "html.parser")
    entries: list[CompetitorEntry] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not _DETAIL_HREF_RE.match(href):
            continue
        url = _absolute(href)
        if url in seen_urls:
            continue

        card = anchor.find_parent(["article", "li", "div"]) or anchor
        card_text = _clean(card.get_text(" ", strip=True))

        heading = card.find(["h1", "h2", "h3", "h4"])
        name = _clean(heading.get_text(" ", strip=True)) if heading else _clean(anchor.get_text(" ", strip=True))
        if not name:
            continue

        # Description: the longest paragraph-ish block in the card that isn't
        # just the name repeated.
        blocks = [
            _clean(el.get_text(" ", strip=True))
            for el in card.find_all(["p", "span", "div"])
        ]
        candidates = [b for b in blocks if len(b) > 30 and b.lower() != name.lower()]
        description = max(candidates, key=len) if candidates else card_text

        # Category: a short badge-like block that isn't the name.
        badges = [b for b in blocks if 2 < len(b) <= 40 and b.lower() != name.lower()]
        category = badges[0] if badges else ""

        seen_urls.add(url)
        entries.append(
            CompetitorEntry(
                name=name,
                url=url,
                category=category,
                description=description,
                aivss_score=_aivss_from(card_text),
                matched_keyword=term,
                first_seen_scan=scan_date,
            )
        )
    return entries


def dedupe_by_url(entries: list[CompetitorEntry]) -> list[CompetitorEntry]:
    """First occurrence wins, so matched_keyword records the earliest search
    term that surfaced the agent."""
    by_url: dict[str, CompetitorEntry] = {}
    for entry in entries:
        by_url.setdefault(entry.url, entry)
    return list(by_url.values())


def filter_noise(entries: list[CompetitorEntry]) -> tuple[list[CompetitorEntry], list[CompetitorEntry]]:
    kept, dropped = [], []
    for entry in entries:
        (dropped if is_noise(entry) else kept).append(entry)
    return kept, dropped


def carry_forward_first_seen(entries: list[CompetitorEntry], scan_date: str, cases_dir: str) -> None:
    """Preserve first_seen_scan for urls already present in an earlier snapshot,
    so the field means "first seen" rather than "seen this month"."""
    previous_path = find_previous_snapshot(scan_date, cases_dir)
    if previous_path is None:
        return
    with open(previous_path, "r", encoding="utf-8") as fh:
        previous = CompetitorScanRunInput(**json.load(fh))
    known = {e.url: e.first_seen_scan for e in previous.entries}
    for entry in entries:
        if entry.url in known and known[entry.url]:
            entry.first_seen_scan = known[entry.url]


def build_snapshot(cases_dir: str = CASES_DIR, scan_date: str | None = None) -> tuple[CompetitorScanRunInput, list[str]]:
    """Fetch every search term and assemble the month's snapshot.

    Returns (snapshot, warnings). Per-term HTTP failures are collected as
    warnings rather than aborting the whole run.
    """
    scan_date = scan_date or current_scan_month()
    warnings: list[str] = []
    raw: list[CompetitorEntry] = []

    session = requests.Session()
    for i, term in enumerate(SEARCH_TERMS):
        try:
            html = fetch_term(term, session)
        except Exception as exc:
            warnings.append(f"term {term!r} failed: {type(exc).__name__}: {exc}")
            continue
        found = parse_cards(html, term, scan_date)
        if not found:
            warnings.append(f"term {term!r} returned no parseable cards (zero results, or the page layout changed)")
        raw.extend(found)
        if i < len(SEARCH_TERMS) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    deduped = dedupe_by_url(raw)
    kept, dropped = filter_noise(deduped)
    if dropped:
        warnings.append(
            f"filtered {len(dropped)} noise listing(s) (talent-acquisition/recruiting or generic lead-gen): "
            + ", ".join(e.name for e in dropped[:10])
        )
    carry_forward_first_seen(kept, scan_date, cases_dir)

    notes = (
        f"Automated fetch of {DIRECTORY_URL} on {datetime.now(timezone.utc).isoformat()} "
        f"across {len(SEARCH_TERMS)} niche search terms: {len(raw)} raw hits -> "
        f"{len(deduped)} unique urls -> {len(kept)} kept, {len(dropped)} filtered as noise."
    )
    return (
        CompetitorScanRunInput(
            scan_date=scan_date,
            keywords=list(SEARCH_TERMS),
            entries=kept,
            source_notes=notes,
        ),
        warnings,
    )


def snapshot_path(scan_date: str, cases_dir: str = CASES_DIR) -> str:
    return os.path.join(cases_dir, f"competitor_scan_{scan_date}.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the monthly competitor-scan snapshot (pure HTTP, no LLM)")
    parser.add_argument("--cases-dir", default=CASES_DIR)
    parser.add_argument("--scan-date", default=None, help="Override the YYYY-MM snapshot month (default: current UTC month)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing the snapshot")
    args = parser.parse_args(argv)

    snapshot, warnings = build_snapshot(cases_dir=args.cases_dir, scan_date=args.scan_date)
    for warning in warnings:
        print(f"[trend-agent] competitor-fetch WARN: {warning}", file=sys.stderr)

    out_path = snapshot_path(snapshot.scan_date, args.cases_dir)

    if not snapshot.entries:
        print(
            "[trend-agent] competitor-fetch: zero entries parsed — refusing to write an empty snapshot "
            "(an empty month would fake a mass exit this month and a mass ALERT next month). "
            "Check the directory URL/layout, then re-run.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(f"[trend-agent] competitor-fetch dry-run: {len(snapshot.entries)} entries would be written to {out_path}", file=sys.stderr)
        print(snapshot.model_dump_json(indent=2))
        return 0

    os.makedirs(args.cases_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(snapshot.model_dump_json(indent=2))
        fh.write("\n")
    print(f"[trend-agent] competitor-fetch: wrote {len(snapshot.entries)} entries to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
