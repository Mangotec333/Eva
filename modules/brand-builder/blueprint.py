"""
EVA Brand-Builder — parse a brand-blueprint markdown into structured JSON.

The blueprint markdown (e.g. ``brand_blueprint_eva_growth_agency.md``) is the
SOURCE OF TRUTH for a pipeline. This module turns it into the two core objects
the Brand Builder stores and reasons over:

  * ``blueprint.json`` per category —
      {audience, market_patterns[], channels[], content_archetypes[],
       authority_signals[], awareness_loops[], cadence{}, cta_ladder[],
       do_not_say[], kpis[]}
    Each ``market_pattern`` carries date + source_url + confidence(high/med/low).

  * ``pipeline.json`` per pipeline —
      {pipeline_id, category, mission, target_audience, current_goal, offer, cta,
       positioning, proof_assets[], content_pillars[], voice_rules[],
       approval_required, success_metric, blueprint_version}

Parsing is deterministic and section-aware (splits on ``## N.`` / ``### N.x``
headers) so it runs offline with zero network and is fully testable against the
real seed file. Stdlib only (re).
"""

from __future__ import annotations

import re

CONF_RE = re.compile(r"\*\*Confidence:\s*(high|med|low)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s\)\]]+")


def normalize_confidence(text: str) -> str:
    """Map any confidence phrasing to one of high/med/low."""
    m = CONF_RE.search(text or "")
    if not m:
        # loose fallback on bare words
        low = (text or "").lower()
        if "confidence: high" in low or "**high**" in low:
            return "high"
        if "confidence: med" in low or "**med**" in low:
            return "med"
        return "low"
    return m.group(1).lower()


def first_url(text: str) -> str:
    m = URL_RE.search(text or "")
    return m.group(0) if m else ""


def _split_sections(md: str) -> dict[str, str]:
    """Top-level ``## N. Title`` sections keyed by their integer number."""
    out: dict[str, str] = {}
    parts = re.split(r"^##\s+(\d+)\.\s*(.+)$", md, flags=re.MULTILINE)
    # parts: [pre, num, title, body, num, title, body, ...]
    for i in range(1, len(parts), 3):
        num = parts[i].strip()
        body = parts[i + 2] if i + 2 < len(parts) else ""
        out[num] = body
    return out


def _split_subsections(body: str) -> list[tuple[str, str]]:
    """``### x.y Title`` subsections as (title, body) in order."""
    out: list[tuple[str, str]] = []
    parts = re.split(r"^###\s+(.+)$", body, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        sub = parts[i + 1] if i + 1 < len(parts) else ""
        out.append((title, sub))
    return out


def _first_paragraph(text: str) -> str:
    for block in text.strip().split("\n\n"):
        clean = " ".join(line.strip() for line in block.splitlines() if line.strip())
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean and not clean.startswith("|"):
            return clean
    return ""


def _table_rows(body: str) -> list[list[str]]:
    """Parse markdown table rows (skips header + separator)."""
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue  # separator row
        rows.append(cells)
    return rows


def _strip_md(text: str) -> str:
    """Drop bold/italic/link markup for clean field values."""
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # links → label
    text = text.replace("**", "").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# section extractors
# ---------------------------------------------------------------------------

def _header_field(md: str, label: str) -> str:
    m = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$", md, flags=re.MULTILINE)
    return _strip_md(m.group(1)) if m else ""


def parse_audience(body: str) -> dict:
    segments = []
    for row in _table_rows(body):
        if len(row) >= 2:
            name = _strip_md(row[0])
            if name.lower() in ("segment", ""):
                continue
            segments.append({
                "segment": name,
                "profile": _strip_md(row[1]),
                "deal_range": _strip_md(row[2]) if len(row) > 2 else "",
                "values": _strip_md(row[3]) if len(row) > 3 else "",
            })
    return {"segments": segments}


def parse_market_patterns(body: str, date: str) -> list[dict]:
    out = []
    for title, sub in _split_subsections(body):
        summary = _first_paragraph(sub)
        out.append({
            "pattern": _strip_md(re.sub(r"^\d+\.\d+\s*", "", title)),
            "summary": _strip_md(summary),
            "date": date,
            "source_url": first_url(sub),
            "confidence": normalize_confidence(sub),
        })
    return out


def parse_channels(body: str) -> list[dict]:
    out = []
    for row in _table_rows(body):
        if len(row) < 2:
            continue
        rank = _strip_md(row[0])
        channel = _strip_md(row[1])
        if channel.lower() in ("channel", ""):
            continue
        evidence = row[-1]
        out.append({
            "rank": rank,
            "channel": channel,
            "why": _strip_md(row[2]) if len(row) > 2 else "",
            "confidence": normalize_confidence(evidence),
            "source_url": first_url(evidence),
        })
    return out


def parse_titled(body: str) -> list[dict]:
    """Generic ``### x.y Title`` → [{name, summary, confidence}]."""
    out = []
    for title, sub in _split_subsections(body):
        name = _strip_md(re.sub(r"^\d+\.\d+\s*", "", title))
        name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
        out.append({
            "name": name,
            "summary": _strip_md(_first_paragraph(sub)),
            "confidence": normalize_confidence(sub),
        })
    return out


def parse_awareness_loops(body: str) -> list[dict]:
    out = []
    for title, sub in _split_subsections(body):
        name = _strip_md(re.sub(r"^\d+\.\d+\s*", "", title))
        out.append({
            "name": name,
            "hook": _header_field(sub, "Hook"),
            "distribution_motion": _header_field(sub, "Distribution motion"),
        })
    return out


def parse_cadence(body: str) -> dict:
    out = {}
    for row in _table_rows(body):
        if len(row) < 2:
            continue
        channel = _strip_md(row[0])
        if channel.lower() in ("channel", ""):
            continue
        out[channel] = _strip_md(row[1])
    return out


def parse_cta_ladder(body: str) -> list[dict]:
    out = []
    for title, sub in _split_subsections(body):
        if not title.lower().startswith("stage"):
            continue
        out.append({
            "stage": _strip_md(title),
            "cta": _header_field(sub, "CTA"),
            "goal": _header_field(sub, "Goal"),
        })
    return out


def parse_do_not_say(body: str) -> list[str]:
    out = []
    for label in ("Never say", "Never use", "Avoid"):
        for m in re.finditer(rf"\*\*{label}:\*\*\s*(.+)", body):
            out.append(_strip_md(m.group(1)))
    return out


def parse_kpis(body: str) -> list[dict]:
    out = []
    for row in _table_rows(body):
        if len(row) < 2:
            continue
        name = _strip_md(row[0])
        if name.lower() in ("kpi", ""):
            continue
        out.append({
            "kpi": name,
            "target": _strip_md(row[1]),
            "confidence": normalize_confidence(row[-1]),
        })
    return out


# ---------------------------------------------------------------------------
# top-level
# ---------------------------------------------------------------------------

def parse_blueprint(md: str) -> dict:
    """Parse the full markdown into a blueprint dict."""
    category = _header_field(md, "Category")
    date = _header_field(md, "Date")
    # normalize date to ISO-ish if it's "Month D, YYYY"
    iso_date = _to_iso_date(date)
    sections = _split_sections(md)

    return {
        "category": category,
        "date": iso_date or date,
        "audience": parse_audience(sections.get("1", "")),
        "market_patterns": parse_market_patterns(sections.get("2", ""), iso_date or date),
        "channels": parse_channels(sections.get("3", "")),
        "content_archetypes": parse_titled(sections.get("4", "")),
        "authority_signals": parse_titled(sections.get("5", "")),
        "awareness_loops": parse_awareness_loops(sections.get("6", "")),
        "cadence": parse_cadence(sections.get("7", "")),
        "cta_ladder": parse_cta_ladder(sections.get("8", "")),
        "do_not_say": parse_do_not_say(sections.get("9", "")),
        "kpis": parse_kpis(sections.get("10", "")),
        "blueprint_version": iso_date or date,
    }


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def _to_iso_date(text: str) -> str:
    """'July 16, 2026' -> '2026-07-16'. Passthrough if already ISO."""
    text = (text or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if m and m.group(1).lower() in _MONTHS:
        return f"{int(m.group(3)):04d}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return ""


def derive_pipeline(pipeline_id: str, blueprint: dict) -> dict:
    """Build the pipeline.json strategy object from a parsed blueprint.

    The blueprint captures market research; the pipeline captures the strategic
    decisions Eva makes from it. Fields not spelled out verbatim in the markdown
    are synthesised from the strongest signals (entry offer, top archetypes,
    do-not-say list) so the pipeline is self-contained for planning.
    """
    archetypes = [a["name"] for a in blueprint.get("content_archetypes", [])]
    signals = [s["name"] for s in blueprint.get("authority_signals", [])]
    ladder = blueprint.get("cta_ladder", [])
    # signature entry-offer CTA = the audit stage, else the last stage
    entry = next((s for s in ladder if "audit" in (s.get("stage", "") + s.get("cta", "")).lower()), None)
    cta = (entry or (ladder[0] if ladder else {})).get("cta", "")
    offer = (ladder[-1].get("cta", "") if ladder else "")
    audience_segments = [s["segment"] for s in blueprint.get("audience", {}).get("segments", [])]

    do_not_say = blueprint.get("do_not_say", [])
    voice_rules = [
        "No unsubstantiated superlatives (leading, best-in-class, world-class, revolutionary).",
        "Every performance claim must be substantiatable with data on demand.",
        "No guaranteed-returns / financial-advice language.",
        "Lead with proprietary data and specific observations, not generic industry stats.",
        "Include the informational-only disclaimer on outbound content.",
    ]

    return {
        "pipeline_id": pipeline_id,
        "category": blueprint.get("category", ""),
        "mission": (
            "Build founder-led authority that compounds into qualified acquirer "
            "pipeline for Eva's AI deal-sourcing + scoring service."
        ),
        "target_audience": audience_segments,
        "current_goal": "Generate qualified inbound DMs and booked free deal audits.",
        "offer": offer or (
            "Eva continuously scans Flippa, Acquire.com, and Empire Flippers "
            "against the buy box, scores listings on 11 parameters, and surfaces "
            "the 3 worth closing."
        ),
        "cta": cta or (
            "Send me a listing you're evaluating — I'll run it through Eva's "
            "11-parameter model and send a free deal audit, no strings."
        ),
        "positioning": (
            "AI-powered acquisition sourcing & deal-scoring; proprietary 92-deal "
            "dataset; durability + AI-resilience as the scoring edge."
        ),
        "proof_assets": signals or [
            "92-deal dataset", "11-parameter scoring framework", "AI-resilience test",
        ],
        "content_pillars": archetypes,
        "voice_rules": voice_rules,
        "do_not_say": do_not_say,
        "approval_required": True,
        "success_metric": "Booked free audits/month (5-10); qualified DMs/month (10-20).",
        "blueprint_version": blueprint.get("blueprint_version", ""),
    }


def parse_file(path: str, pipeline_id: str) -> tuple[dict, dict]:
    """Read a blueprint markdown file → (pipeline_dict, blueprint_dict)."""
    with open(path, "r", encoding="utf-8") as fh:
        md = fh.read()
    blueprint = parse_blueprint(md)
    pipeline = derive_pipeline(pipeline_id, blueprint)
    return pipeline, blueprint


__all__ = [
    "parse_blueprint", "derive_pipeline", "parse_file",
    "normalize_confidence", "first_url",
]
