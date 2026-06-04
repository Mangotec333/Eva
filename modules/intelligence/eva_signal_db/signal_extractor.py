"""
EVA Signal Intelligence — Morning Brief Signal Extractor
Parses a completed morning brief and extracts structured signals for the DB.
Called at end of each morning brief run.
Version 1.0 | June 2026
"""

import re
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from .signal_repository import SignalRepository


# ─────────────────────────────────────────────
# SIGNAL EXTRACTION RULES
# Maps brief sections → signal types + metadata
# ─────────────────────────────────────────────

SECTION_MAP = {
    "HORMOZI":       {"signal_type": "hormozi",      "source": "hormozi",       "domain": ["mindset", "sales", "acquisition"], "confidence": 0.85, "stance": "belief"},
    "UNUSUAL WHIZ":  {"signal_type": "unusual_whiz", "source": "unusual_whiz",  "domain": ["mindset", "philosophy"],           "confidence": 0.75, "stance": "observation"},
    "SIGNALS":       {"signal_type": "learning",     "source": "morning_brief", "domain": ["saas", "ai", "business"],          "confidence": 0.70, "stance": "hypothesis"},
    "HN":            {"signal_type": "hn",            "source": "hacker_news",   "domain": ["ai", "saas", "tech"],              "confidence": 0.65, "stance": "observation"},
    "TRENDS":        {"signal_type": "trend",         "source": "google_trends", "domain": ["market", "ai", "real-estate"],    "confidence": 0.60, "stance": "observation"},
    "DEAL FLOW":     {"signal_type": "deal_signal",   "source": "morning_brief", "domain": ["deal-sourcing"],                  "confidence": 0.80, "stance": "observation"},
}


# ─────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────

def parse_brief_to_signals(brief_text: str, brief_date: Optional[str] = None) -> List[Dict]:
    """
    Parse a morning brief body text into a list of signal dicts
    ready for SignalRepository.save_brief_signals().

    Handles:
    - Hormozi: single lesson line
    - Unusual Whiz: single insight line
    - Signals: bullet points
    - HN: pipe-separated stories
    - Trends: pipe-separated items
    - Deal Flow: new listings (skip "No new listings")
    """
    signals = []
    brief_date = brief_date or datetime.utcnow().strftime("%Y-%m-%d")

    # Split brief into sections
    lines = brief_text.strip().split("\n")
    current_section = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect section headers
        upper = line.upper()
        matched_section = None
        for section_key in SECTION_MAP:
            if upper.startswith(section_key):
                matched_section = section_key
                break

        if matched_section:
            current_section = matched_section
            # Extract content after the section header (same line)
            content_after = line[len(matched_section):].strip().lstrip(":—-").strip()
            if content_after and _is_valid_content(content_after, current_section):
                signals.extend(_parse_section_line(content_after, current_section, brief_date))
            continue

        # Content lines within a section
        if current_section and _is_valid_content(line, current_section):
            signals.extend(_parse_section_line(line, current_section, brief_date))

    return signals


def _is_valid_content(text: str, section: str) -> bool:
    """Filter out placeholder/empty lines."""
    text = text.strip()
    if not text:
        return False
    skip_phrases = [
        "nothing today", "no new listings", "clear calendar",
        "north star", "fico", "kaizen", "eva morning brief",
        "today", "deal flow"
    ]
    lower = text.lower()
    for phrase in skip_phrases:
        if lower.startswith(phrase):
            return False
    return True


def _parse_section_line(line: str, section: str, brief_date: str) -> List[Dict]:
    """Convert a section line into one or more signal dicts."""
    meta = SECTION_MAP[section]
    signals = []

    if section in ("HORMOZI", "UNUSUAL WHIZ"):
        # Single line — strip label prefix if present
        body = re.sub(r"^(Hormozi|Unusual Whiz)\s*[:–—]\s*", "", line, flags=re.IGNORECASE).strip()
        if body:
            signals.append({
                **meta,
                "title": f"[{section.title()}] {body[:80]}",
                "body": body,
                "brief_date": brief_date,
                "brief_snippet": line,
                "is_actionable": False,
            })

    elif section == "SIGNALS":
        # Bullet points: "Signal: [topic] — [insight]"
        body = re.sub(r"^[•\-*]\s*", "", line).strip()
        body = re.sub(r"^Signal\s*[:–—]\s*", "", body, flags=re.IGNORECASE).strip()
        parts = re.split(r"\s*[—–]\s*", body, maxsplit=1)
        title_text = parts[0].strip() if parts else body[:80]
        body_text  = parts[1].strip() if len(parts) > 1 else body
        if body_text:
            signals.append({
                **meta,
                "title": title_text[:120],
                "body": body_text,
                "brief_date": brief_date,
                "brief_snippet": line,
                "is_actionable": True,  # Business signals = actionable
            })

    elif section == "HN":
        # Pipe-separated: "HN: Title — reason | Title2 — reason2"
        items = line.split("|")
        for item in items:
            item = item.strip()
            item = re.sub(r"^HN\s*[:–—]\s*", "", item, flags=re.IGNORECASE).strip()
            parts = re.split(r"\s*[—–]\s*", item, maxsplit=1)
            title_text = parts[0].strip() if parts else item[:80]
            body_text  = parts[1].strip() if len(parts) > 1 else item
            if title_text and len(title_text) > 5:
                signals.append({
                    **meta,
                    "title": f"[HN] {title_text[:100]}",
                    "body": body_text or title_text,
                    "brief_date": brief_date,
                    "brief_snippet": item,
                    "is_actionable": False,
                    "valid_until": _days_from_now(14),   # HN stories expire in 2 weeks
                })

    elif section == "TRENDS":
        # Pipe-separated: "Trend: topic — connection | ..."
        items = line.split("|")
        for item in items:
            item = item.strip()
            item = re.sub(r"^Trend\s*[:–—]\s*", "", item, flags=re.IGNORECASE).strip()
            parts = re.split(r"\s*[—–]\s*", item, maxsplit=1)
            title_text = parts[0].strip() if parts else item[:80]
            body_text  = parts[1].strip() if len(parts) > 1 else item
            if title_text and len(title_text) > 3:
                signals.append({
                    **meta,
                    "title": f"[Trend] {title_text[:100]}",
                    "body": body_text or title_text,
                    "brief_date": brief_date,
                    "brief_snippet": item,
                    "is_actionable": False,
                    "valid_until": _days_from_now(7),   # Trends expire in 1 week
                })

    elif section == "DEAL FLOW":
        # "source | subject | summary | URL"
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2:
            source_name = parts[0] if parts else "broker"
            subject     = parts[1] if len(parts) > 1 else ""
            summary     = parts[2] if len(parts) > 2 else ""
            url         = parts[3] if len(parts) > 3 else None
            body_text   = f"{summary}" + (f" | {url}" if url else "")
            title_text  = f"[Deal] {subject[:80]}"
            if subject:
                signals.append({
                    **meta,
                    "title": title_text,
                    "body": body_text,
                    "source_detail": source_name,
                    "brief_date": brief_date,
                    "brief_snippet": line,
                    "is_actionable": True,
                    "applies_to": ["deal-sourcing"],
                    "valid_until": _days_from_now(7),
                })

    return signals


def _days_from_now(days: int) -> str:
    from datetime import timedelta
    return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# MAIN ENTRY — called from morning brief cron
# ─────────────────────────────────────────────

def extract_and_save_brief(brief_text: str, brief_date: Optional[str] = None) -> Dict:
    """
    Full pipeline: parse brief → extract signals → save to DB.
    Returns summary of what was saved.
    """
    date_str = brief_date or datetime.utcnow().strftime("%Y-%m-%d")
    repo = SignalRepository()

    extracted = parse_brief_to_signals(brief_text, brief_date=date_str)
    if not extracted:
        return {"brief_date": date_str, "saved": 0, "message": "No extractable signals found"}

    saved_ids = repo.save_brief_signals(brief_date=date_str, signals=extracted)

    return {
        "brief_date": date_str,
        "saved": len(saved_ids),
        "ids": saved_ids,
        "signal_types": list({s["signal_type"] for s in extracted}),
    }


# ─────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    sample_brief = """
EVA Morning Brief — Tuesday, June 3

TODAY
Clear calendar

DEAL FLOW
Empire Flippers | batch.ai Reply | Shawn replied to LOI | https://empireflippers.com/listing/87872

HORMOZI  The money is in the offer — if your close rate is low, fix the offer before the funnel.

UNUSUAL WHIZ  When 0 and 1 are the same sign, the system overflows. Build capacity before load.

SIGNALS
Signal: AI agents replacing junior ops roles — 40% of admin tasks automatable by 2026.
Signal: SaaS multiples compressing — bootstrapped exits now 2–3x ARR vs 4–5x in 2022.

HN: LLM context windows hit 2M tokens — local retrieval less critical | Supabase open-sources vector storage layer — SQLite alternative for small teams

TRENDS  AI Automation Tools — Eva module opportunity | RCFE Senior Care Demand — Storeys expansion signal | Online Business Acquisition — batch.ai validation

NORTH STAR
FICO 706→731 Sep 2 · batch.ai LOI sent · Mission Villa $7,128/mo NOI · Kaizen
"""

    result = extract_and_save_brief(sample_brief, brief_date="2026-06-03")
    print(json.dumps(result, indent=2))

    repo = SignalRepository()
    print("\n--- Stats ---")
    print(json.dumps(repo.stats(), indent=2))

    print("\n--- Active Signals ---")
    for s in repo.active():
        print(f"  [{s['signal_type']:12}] {s['title']}")
