"""
EVA Monetizing Agent — Mine step (signal sources behind a Protocol)
===================================================================

The first step of the Mine -> Match -> Package -> Route -> Follow-up pattern.
Sources are behind a Protocol so the scan loop never depends on a concrete data
connector (same rule the rest of Eva follows).

- ``SignalSource`` — the Protocol: ``mine() -> list[signal dict]``.
- ``StubSignalSource`` — deterministic, offline sample signals for tests. Honest
  about being a stub (every signal carries ``source="stub"``).
- ``RepoSignalSource`` — the real, best-effort gatherer. It ports Yaksha's
  context-gathering logic (knowledge docs, social-signals DB, deals DB, git log,
  its own run history) into structured signals, reusing whatever sources exist
  in the repo/host and degrading gracefully to nothing when they're absent (the
  sandbox has no network and no ``~/.eva`` DBs).

A mined *signal* is a plain dict. Recognized keys (all optional except a short
``description``)::

    {
      "source": str, "kind": str, "name"/"subject": str, "description": str,
      "stage": str, "engagement": float, "age_days": float, "lost_days": float,
      "decay_days": float, "has_cta": bool, "suggested_play": str,
      # optional explicit scoring overrides:
      "cash_proximity", "effort_hours", "strategic_fit", "reusability",
      "urgency", "cash_estimate"
    }
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_HOME = Path.home()
_EVA_DIR = _HOME / ".eva"


@runtime_checkable
class SignalSource(Protocol):
    def mine(self) -> list[dict[str, Any]]:
        """Return a list of mined signal dicts (possibly empty)."""


# ---------------------------------------------------------------------------
# Stub source (offline, deterministic — the test + sandbox default)
# ---------------------------------------------------------------------------

class StubSignalSource:
    """Deterministic sample signals covering the playbook. No network."""

    def mine(self) -> list[dict[str, Any]]:
        return [
            {
                "source": "stub", "kind": "lead", "subject": "RCFE Buyer (Oxnard)",
                "description": "RCFE acquisition lead stalled in Demo 9 days, opened email 3x",
                "stage": "demo", "engagement": 3, "age_days": 9, "decay_days": 5,
                "cash_estimate": 4000,
            },
            {
                "source": "stub", "kind": "spec", "subject": "Onboarding spec",
                "description": "Reusable client onboarding spec used across 3 engagements",
                "reusability": 95, "strategic_fit": 85, "effort_hours": 4,
                "cash_estimate": 1500,
            },
            {
                "source": "stub", "kind": "waitlist", "subject": "4 waitlist signups",
                "description": "4 waitlist signups never received a sales touch",
                "engagement": 0, "age_days": 12, "cash_estimate": 4000,
            },
            {
                "source": "stub", "kind": "customer", "subject": "GHL client (high engagement)",
                "description": "Client with high engagement, no referral ask made",
                "stage": "won", "engagement": 7, "cash_estimate": 3000,
            },
            {
                "source": "stub", "kind": "lost_deal", "subject": "Lost SaaS deal",
                "description": "Deal marked lost 34 days ago; blocker since shipped",
                "lost_days": 34, "cash_estimate": 2000,
            },
            {
                "source": "stub", "kind": "content", "subject": "LinkedIn thought-leader post",
                "description": "High-reach LinkedIn post with no CTA attached",
                "has_cta": False, "engagement": 4, "cash_estimate": 800,
            },
        ]


# ---------------------------------------------------------------------------
# Real source (best-effort; ports Yaksha's gatherers into structured signals)
# ---------------------------------------------------------------------------

class RepoSignalSource:
    """Best-effort real mining. Every gatherer degrades to [] on any failure."""

    def __init__(self, *, knowledge_dir: Path | None = None,
                 social_db: Path | None = None, deals_db: Path | None = None,
                 repo_root: Path | None = None) -> None:
        self.knowledge_dir = knowledge_dir or (_REPO_ROOT / "modules" / "knowledge" / "data")
        self.social_db = social_db or (_EVA_DIR / "eva-social-signals.db")
        self.deals_db = deals_db or (_EVA_DIR / "eva-deals.db")
        self.repo_root = repo_root or _REPO_ROOT

    def mine(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for gather in (self._from_deals, self._from_social, self._from_specs,
                       self._from_git):
            try:
                signals.extend(gather())
            except Exception:  # noqa: BLE001 — a bad source must not abort the scan
                continue
        return signals

    # -- deals pipeline (stalled / lost -> Reactivate / Revive) --------------
    def _from_deals(self) -> list[dict[str, Any]]:
        if not self.deals_db.exists():
            return []
        out: list[dict[str, Any]] = []
        conn = sqlite3.connect(str(self.deals_db))
        try:
            conn.row_factory = sqlite3.Row
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in tables:
                try:
                    rows = conn.execute(
                        f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 25").fetchall()
                except sqlite3.Error:
                    continue
                for r in rows:
                    d = dict(r)
                    stage = str(d.get("stage", d.get("status", ""))).lower()
                    out.append({
                        "source": "deals_db", "kind": "lead",
                        "subject": d.get("name") or d.get("id") or "deal",
                        "description": f"Pipeline row in '{table}' at stage {stage or 'unknown'}",
                        "stage": stage,
                    })
            return out
        finally:
            conn.close()

    # -- social signals (engagement -> Upsell / Referral) --------------------
    def _from_social(self) -> list[dict[str, Any]]:
        if not self.social_db.exists():
            return []
        out: list[dict[str, Any]] = []
        conn = sqlite3.connect(str(self.social_db))
        try:
            conn.row_factory = sqlite3.Row
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in tables:
                try:
                    rows = conn.execute(f"SELECT * FROM {table} LIMIT 25").fetchall()
                except sqlite3.Error:
                    continue
                if rows:
                    out.append({
                        "source": "social_db", "kind": "engagement",
                        "subject": f"{table} signals",
                        "description": f"{len(rows)} social signals in '{table}'",
                        "engagement": float(len(rows)),
                    })
            return out
        finally:
            conn.close()

    # -- knowledge specs (sellable assets -> Productize) ---------------------
    def _from_specs(self) -> list[dict[str, Any]]:
        if not self.knowledge_dir.exists():
            return []
        out: list[dict[str, Any]] = []
        for f in sorted(self.knowledge_dir.glob("*.md"))[:15]:
            name = f.stem
            if any(k in name.lower() for k in ("spec", "playbook", "offer", "pricing", "template")):
                out.append({
                    "source": "knowledge", "kind": "spec", "subject": name,
                    "description": f"Knowledge doc '{f.name}' may be a sellable asset",
                    "reusability": 90,
                })
        return out

    # -- git log (shipped work -> Productize) --------------------------------
    def _from_git(self) -> list[dict[str, Any]]:
        try:
            result = subprocess.run(
                ["git", "log", "--since=7 days ago", "--oneline", "--no-merges"],
                cwd=str(self.repo_root), capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        lines = [ln for ln in result.stdout.strip().splitlines() if ln]
        if not lines:
            return []
        return [{
            "source": "git", "kind": "shipped_work", "subject": "Recent commits",
            "description": f"{len(lines)} commits shipped in last 7 days — productization candidate",
            "reusability": 80,
        }]


# ---------------------------------------------------------------------------
# History (Follow-up step) — read own prior briefs/plays for the feedback block
# ---------------------------------------------------------------------------

def last_week_feedback(memory_module, path: str) -> str:
    """Build the 'Last week' feedback line from the prior brief's play outcomes.

    Reads the agent's OWN memory only (never a sibling agent's DB). Returns an
    empty string on the first-ever run.
    """
    briefs = memory_module.list_plays(path=path)
    learnings = memory_module.list_learnings(path=path)
    if not learnings:
        return ""
    converted = [l for l in learnings if l.get("outcome") == "converted"]
    total = len(learnings)
    dollars = 0.0
    play_map = {p["play_id"]: p for p in briefs}
    for l in converted:
        p = play_map.get(l.get("play_id"))
        if p:
            dollars += float(p.get("cash_estimate", 0) or 0)
    lesson = converted[0].get("lesson") if converted else (learnings[0].get("lesson") or "")
    base = f"Last week: {len(converted)} of {total} plays converted (${dollars:,.0f})."
    return f"{base} Lesson: {lesson}" if lesson else base


__all__ = [
    "SignalSource",
    "StubSignalSource",
    "RepoSignalSource",
    "last_week_feedback",
]
