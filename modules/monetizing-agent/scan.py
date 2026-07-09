"""
EVA Monetizing Agent — the weekly scan (Mine -> Match -> Package -> Route -> Follow-up)
=======================================================================================

Ties the deterministic core (``playbook``), the mining sources (``mining``), the
packaging brain (``brain``), and persistence (``memory``) into one governed
weekly pass, and renders the very-brief-pithy Sunday brief from the doctrine.

The scan is FREE and deterministic with the Stub brain + Stub source, so the
whole pipeline is offline-testable. Irreversible execution is NOT performed here
— the scan only *packages* plays and writes a pending-approval brief. Execution
happens after the approval gate (see ``service.MonetizingService.approve`` /
``execute``).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import memory
from brain import MonetizationBrain, make_brain
from mining import RepoSignalSource, SignalSource, StubSignalSource, last_week_feedback
from playbook import score_signal

# KB reports live alongside the module so they can be exported to Drive + indexed.
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")

# How many top plays land in the brief.
TOP_N = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _week_of() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Brief rendering (matches the doctrine's format exactly)
# ---------------------------------------------------------------------------

def _fmt_cash(x: float) -> str:
    return f"${x:,.0f}" if x else "$0"


def render_brief(plays: list[dict], feedback: str, *, week_of: str,
                 est_cash: float) -> str:
    """Render the very-brief-pithy Sunday brief. One line per play."""
    date_label = datetime.strptime(week_of, "%Y-%m-%d").strftime("%b %-d") \
        if _safe_strptime(week_of) else week_of
    lines = [
        f"EVA SUNDAY MONETIZATION — {date_label}",
        f"Top {len(plays)} plays, est. {_fmt_cash(est_cash)} cash this week",
        "",
    ]
    for i, p in enumerate(plays, 1):
        artifact = p.get("action_artifact", {}) or {}
        touch = _artifact_touch(artifact)
        lines.append(
            f"{i}. [{p['play_type']}] {p['source_signal']} → {touch} "
            f"| est {_fmt_cash(p['cash_estimate'])} | score {p['score']:g}"
        )
    lines.append("")
    if feedback:
        lines.append(feedback)
        lines.append("")
    lines.append('Reply "go" to execute all, or edit the list.')
    return "\n".join(lines)


def _safe_strptime(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _artifact_touch(artifact: dict) -> str:
    """One-word/phrase description of the packaged next touch, for the brief."""
    kind = artifact.get("kind", "action")
    return {
        "sms": "SMS drafted",
        "email": "email drafted",
        "proposal_doc": "proposal drafted",
        "landing_tweak": "CTA tweak",
        "human_task": "human task routed",
    }.get(kind, kind)


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------

def run_scan(
    *,
    source: Optional[SignalSource] = None,
    brain: Optional[MonetizationBrain] = None,
    db_path: str = memory.DB_PATH,
    top_n: int = TOP_N,
    write_report: bool = True,
    index_transport: Any = None,
    offline: Optional[bool] = None,
) -> dict[str, Any]:
    """Run one full weekly scan and persist a pending-approval brief.

    Steps: Mine (source) -> Match+score (playbook) -> Package (brain) ->
    Route (record ledger rows + write KB report) -> Follow-up (feedback block
    from own history). Returns a summary dict including the brief id and text.
    """
    memory.init_db(db_path)
    source = source or (StubSignalSource() if _is_offline(offline) else RepoSignalSource())
    brain = brain or make_brain(offline=_is_offline(offline))

    # --- Mine ---------------------------------------------------------------
    signals = source.mine()

    # --- Match + score (deterministic, authoritative) -----------------------
    scored = [score_signal(s) for s in signals]
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]

    # --- Follow-up feedback (own history, before this run's writes) ---------
    feedback = last_week_feedback(memory, db_path)

    # --- Package + Route (persist ledger rows) ------------------------------
    week_of = _week_of()
    est_cash = round(sum(p["cash_estimate"] for p in top), 2)

    # Create the brief shell first so plays can reference its id.
    brief_id = memory.save_brief(
        week_of=week_of, est_cash=est_cash, play_count=len(top),
        report_path="", brief_text="", feedback=feedback, path=db_path,
    )

    total_tokens = 0
    persisted: list[dict] = []
    for p in top:
        packaged = brain.package({"play_type": p["play_type"], "signal": p["signal"]})
        total_tokens += int(packaged.get("tokens", 0))
        artifact = packaged.get("artifact", {})
        play_id = memory.record_play(
            brief_id=brief_id,
            play_type=p["play_type"],
            source_signal=str(p["signal"].get("subject") or p["signal"].get("name")
                              or p["signal"].get("description", ""))[:200],
            score=p["score"],
            cash_estimate=p["cash_estimate"],
            action_artifact=artifact,
            path=db_path,
        )
        persisted.append({
            "play_id": play_id,
            "play_type": p["play_type"],
            "source_signal": str(p["signal"].get("subject") or p["signal"].get("description", ""))[:200],
            "score": p["score"],
            "cash_estimate": p["cash_estimate"],
            "action_artifact": artifact,
        })

    # --- Render the brief ---------------------------------------------------
    brief_text = render_brief(persisted, feedback, week_of=week_of, est_cash=est_cash)

    # --- KB: write markdown report + index it -------------------------------
    report_path = ""
    index_result: dict[str, Any] = {}
    if write_report:
        report_path = _write_report(brief_id, week_of, brief_text, persisted)
        index_result = _index_report(week_of, est_cash, len(persisted), report_path,
                                     transport=index_transport)

    # Persist final brief text/report path + record the run.
    _finalize_brief(brief_id, brief_text, report_path, db_path)
    memory.save_run(
        brief_id=brief_id,
        inputs={"signals_mined": len(signals)},
        outputs={"plays": len(persisted), "est_cash": est_cash,
                 "brain_provider": getattr(brain, "provider", "unknown")},
        tokens=total_tokens,
        notes=f"scan top_n={top_n}",
        path=db_path,
    )

    return {
        "brief_id": brief_id,
        "week_of": week_of,
        "signals_mined": len(signals),
        "plays": persisted,
        "est_cash": est_cash,
        "tokens": total_tokens,
        "brief_text": brief_text,
        "report_path": report_path,
        "index_result": index_result,
        "status": memory.STATUS_PENDING,
        "ran_at": _now(),
    }


def _is_offline(offline: Optional[bool]) -> bool:
    if offline is not None:
        return offline
    return os.environ.get("EVA_MONETIZE_OFFLINE") == "1"


def _finalize_brief(brief_id: str, brief_text: str, report_path: str, db_path: str) -> None:
    conn = memory._connect(db_path)
    try:
        conn.execute(
            "UPDATE briefs SET brief_text = ?, report_path = ? WHERE id = ?",
            (brief_text, report_path, brief_id),
        )
        conn.commit()
    finally:
        conn.close()


def _write_report(brief_id: str, week_of: str, brief_text: str,
                  plays: list[dict]) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"revenue-brief-{week_of}.md")
    lines = [
        f"# EVA Revenue Brief — {week_of}",
        "",
        f"Brief ID: `{brief_id}`  ·  Status: pending-approval",
        "",
        "```",
        brief_text,
        "```",
        "",
        "## Packaged plays (detail)",
        "",
    ]
    for i, p in enumerate(plays, 1):
        lines.append(f"### {i}. [{p['play_type']}] {p['source_signal']}")
        lines.append(f"- score: {p['score']}  ·  est cash: ${p['cash_estimate']:,.0f}")
        lines.append(f"- artifact: `{p['action_artifact']}`")
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def _index_report(week_of: str, est_cash: float, play_count: int,
                  report_path: str, *, transport: Any = None) -> dict[str, Any]:
    """Append a row to the Eva Master Index (best-effort, never raises)."""
    try:
        import sys
        modules_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if modules_dir not in sys.path:
            sys.path.insert(0, modules_dir)
        from kb_index import append_to_index
        title = f"Revenue Brief {week_of}"
        summary = f"{play_count} monetization plays, est ${est_cash:,.0f} — {report_path}"
        return append_to_index(title, summary, "", transport=transport)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


__all__ = ["run_scan", "render_brief", "REPORTS_DIR", "TOP_N"]
