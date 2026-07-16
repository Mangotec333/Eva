"""
EVA IP-Scout — daily markdown triage report.

Renders one run's invention disclosures into a human-readable markdown report
with a file / monitor / drop recommendation per idea. Crucially, IP-Scout is an
L1 lobe: the report NEVER asserts patentability — every disclosure carries a
"needs attorney review" flag, and the header states the disclaimer plainly.
"""

from __future__ import annotations

REC_EMOJI = {"file": "FILE", "monitor": "MONITOR", "drop": "DROP"}

DISCLAIMER = (
    "> **Not legal advice.** IP-Scout is an automated prior-art *triage* tool "
    "(L1 autonomy): it never files, submits, or asserts patentability. Novelty "
    "scores are heuristic signals to prioritise a **patent attorney's review** — "
    "nothing here is a determination that anything is patentable."
)


def _confidence_note(band: str) -> str:
    return {
        "high": "high confidence (broad prior-art evidence examined)",
        "med": "medium confidence (some prior-art evidence)",
        "low": "low confidence (little/no prior-art evidence — treat as tentative)",
    }.get(band, band)


def render_report(report_date: str, disclosures: list[dict], *,
                  offline: bool, provider: str) -> str:
    disclosures = disclosures or []
    by_rec = {"file": [], "monitor": [], "drop": []}
    for d in disclosures:
        by_rec.setdefault(d.get("recommendation", "monitor"), []).append(d)

    lines = [
        f"# IP-Scout — Prior-Art Triage Report — {report_date}",
        "",
        DISCLAIMER,
        "",
        f"- **Ideas triaged:** {len(disclosures)}",
        f"- **Recommend attorney review (file):** {len(by_rec['file'])}",
        f"- **Monitor:** {len(by_rec['monitor'])}",
        f"- **Drop:** {len(by_rec['drop'])}",
        f"- **Prior-art provider:** {provider}" + (" (offline/mocked)" if offline else ""),
        "",
        "---",
        "",
    ]

    if not disclosures:
        lines += ["_No pending ideas to triage this run._", ""]
        return "\n".join(lines)

    for rec in ("file", "monitor", "drop"):
        group = by_rec.get(rec) or []
        if not group:
            continue
        lines.append(f"## {REC_EMOJI.get(rec, rec.upper())} — {rec.title()} "
                     f"({len(group)})")
        lines.append("")
        for d in sorted(group, key=lambda x: x.get("novelty_score", 0), reverse=True):
            lines += _render_disclosure(d)
        lines.append("")

    return "\n".join(lines)


def _render_disclosure(d: dict) -> list[str]:
    hits = d.get("prior_art_hits", []) or []
    review = "**needs attorney review**" if d.get("attorney_review_needed") else \
        "no attorney review flagged"
    out = [
        f"### {d.get('title', '(untitled)')}",
        "",
        f"- **Idea id:** `{d.get('idea_id', '')}`  ·  **Sensor:** "
        f"{d.get('sensor_source', 'user-seed')}",
        f"- **Novelty score:** {d.get('novelty_score', 0):.2f}  ·  "
        f"**Confidence:** {_confidence_note(d.get('confidence_band', 'low'))}",
        f"- **Recommendation:** {d.get('recommendation', 'monitor').upper()} — {review}",
        f"- **Abstract:** {d.get('abstract', '')[:300]}",
    ]
    claims = d.get("claims_draft", []) or []
    if claims:
        out.append(f"- **Draft claims ({len(claims)}):**")
        for c in claims[:5]:
            out.append(f"  - {c}")
    if hits:
        out.append(f"- **Prior-art hits ({len(hits)}):**")
        for h in hits[:5]:
            title = h.get("title", "")[:90]
            pid = h.get("patent_id", "")
            out.append(f"  - `{pid}` {title}")
    else:
        out.append("- **Prior-art hits:** none found (low confidence — verify manually)")
    out.append("")
    return out


__all__ = ["render_report", "DISCLAIMER"]
