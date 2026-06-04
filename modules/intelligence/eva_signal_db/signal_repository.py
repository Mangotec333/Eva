"""
EVA Signal Intelligence — SignalRepository
Living knowledge layer: save, validate, close, supersede, version signals.
Version 1.0 | June 2026
"""

import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any


DB_PATH = Path(__file__).parent / "eva_signals.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Validation period in days (default: monthly)
DEFAULT_VALIDATION_DAYS = 30


# ─────────────────────────────────────────────
# DB BOOTSTRAP
# ─────────────────────────────────────────────

def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def bootstrap_db(db_path: Path = DB_PATH) -> None:
    """Create the DB and apply schema if not already present."""
    schema = SCHEMA_PATH.read_text()
    with get_connection(db_path) as conn:
        conn.executescript(schema)
    print(f"[SignalDB] Bootstrapped: {db_path}")


# ─────────────────────────────────────────────
# SIGNAL REPOSITORY
# ─────────────────────────────────────────────

class SignalRepository:
    """
    All CRUD + lifecycle operations for eva_signals.db.

    Lifecycle:
        active → validated (confirmed true)
               → invalidated (proved false)
               → superseded (replaced by newer version)
               → expired (time-window passed)

    Opinion changes: supersede() creates a new signal and chains the old one to it.
    Monthly validation: due_for_validation() returns signals needing review.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        if not db_path.exists():
            bootstrap_db(db_path)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    # ── SAVE ─────────────────────────────────

    def save(
        self,
        *,
        signal_type: str,           # 'learning' | 'trend' | 'opinion' | 'hormozi' | 'unusual_whiz' | 'hn' | 'deal_signal' | 'market' | 'personal'
        source: str,                # 'morning_brief' | 'hormozi' | 'unusual_whiz' | 'hacker_news' | 'google_trends' | 'manual' | 'deal_scout'
        title: str,
        body: str,
        source_detail: Optional[str] = None,
        raw_source_text: Optional[str] = None,
        domain: Optional[List[str]] = None,
        applies_to: Optional[List[str]] = None,
        confidence: float = 0.7,
        stance: str = "belief",     # 'belief' | 'hypothesis' | 'observation' | 'contrarian'
        is_actionable: bool = False,
        valid_until: Optional[str] = None,   # ISO date string
        brief_date: Optional[str] = None,
        brief_snippet: Optional[str] = None,
        validation_days: int = DEFAULT_VALIDATION_DAYS,
    ) -> str:
        """
        Save a new signal. Returns the signal ID.
        Deduplicates by (title, source, brief_date) — silently updates if exists.
        """
        signal_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        next_val = (datetime.utcnow() + timedelta(days=validation_days)).date().isoformat()

        domain_json    = json.dumps(domain or [])
        applies_json   = json.dumps(applies_to or [])
        brief_date_str = brief_date or datetime.utcnow().strftime("%Y-%m-%d")

        with self._conn() as conn:
            # Dedup check
            existing = conn.execute(
                """SELECT id FROM signals
                   WHERE title = ? AND source = ? AND brief_date = ?
                   LIMIT 1""",
                (title, source, brief_date_str)
            ).fetchone()

            if existing:
                # Update body + confidence if content changed
                conn.execute(
                    """UPDATE signals
                       SET body = ?, confidence = ?, updated_at = ?
                       WHERE id = ?""",
                    (body, confidence, now, existing["id"])
                )
                return existing["id"]

            conn.execute(
                """INSERT INTO signals (
                    id, signal_type, source, source_detail,
                    title, body, raw_source_text,
                    domain, applies_to,
                    confidence, stance, is_actionable,
                    status, opened_at, valid_until,
                    next_validation_at, brief_date, brief_snippet,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    signal_id, signal_type, source, source_detail,
                    title, body, raw_source_text,
                    domain_json, applies_json,
                    confidence, stance, int(is_actionable),
                    "active", now, valid_until,
                    next_val, brief_date_str, brief_snippet,
                    now, now
                )
            )
        return signal_id

    # ── VALIDATE ─────────────────────────────

    def validate(
        self,
        signal_id: str,
        verdict: str,               # 'still_true' | 'partially_true' | 'false' | 'outdated' | 'needs_more_data'
        evidence: Optional[str] = None,
        new_confidence: Optional[float] = None,
        validator: str = "eva",
    ) -> str:
        """
        Record a validation review. Updates signal status and schedules next review.
        Returns action taken: 'kept_active' | 'closed' | 'confidence_updated'
        """
        now = datetime.utcnow().isoformat()
        next_val = (datetime.utcnow() + timedelta(days=DEFAULT_VALIDATION_DAYS)).date().isoformat()

        verdict_to_status = {
            "false":        ("invalidated",   "outcome_disproved"),
            "outdated":     ("expired",        "time_expired"),
        }
        new_status, close_reason = verdict_to_status.get(verdict, (None, None))
        action_taken = "kept_active"

        with self._conn() as conn:
            sig = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            if not sig:
                raise ValueError(f"Signal not found: {signal_id}")

            updates: Dict[str, Any] = {
                "last_validated_at": now,
                "next_validation_at": next_val,
                "validation_count": sig["validation_count"] + 1,
                "updated_at": now,
            }

            if new_confidence is not None:
                updates["confidence"] = new_confidence
                action_taken = "confidence_updated"

            if new_status:
                updates["status"] = new_status
                updates["closed_at"] = now
                updates["close_reason"] = close_reason
                action_taken = "closed"

            # Apply updates
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE signals SET {set_clause} WHERE id = ?",
                list(updates.values()) + [signal_id]
            )

            # Log validation
            conn.execute(
                """INSERT INTO signal_validations
                   (signal_id, validated_at, validator, verdict, evidence, new_confidence, action_taken)
                   VALUES (?,?,?,?,?,?,?)""",
                (signal_id, now, validator, verdict, evidence, new_confidence, action_taken)
            )

        return action_taken

    # ── CLOSE ────────────────────────────────

    def close(
        self,
        signal_id: str,
        reason: str,                # 'outcome_proved' | 'outcome_disproved' | 'new_evidence' | 'time_expired' | 'manual'
        outcome_note: Optional[str] = None,
        final_status: str = "invalidated",
    ) -> None:
        """
        Permanently close a signal. Sets status, closed_at, and outcome_note.
        final_status: 'validated' | 'invalidated' | 'expired'
        """
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """UPDATE signals
                   SET status = ?, closed_at = ?, close_reason = ?,
                       outcome_note = ?, updated_at = ?
                   WHERE id = ?""",
                (final_status, now, reason, outcome_note, now, signal_id)
            )

    # ── SUPERSEDE (VERSION A SIGNAL) ─────────

    def supersede(
        self,
        old_signal_id: str,
        *,
        new_title: str,
        new_body: str,
        new_confidence: float = 0.7,
        new_stance: str = "belief",
        reason: str = "new_evidence",
        outcome_note: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Mark old signal as superseded and create a new version.
        Returns new signal ID. Chains old → new via superseded_by field.
        Copies all non-content fields (domain, applies_to, etc.) to new version unless overridden.
        """
        with self._conn() as conn:
            old = conn.execute("SELECT * FROM signals WHERE id = ?", (old_signal_id,)).fetchone()
            if not old:
                raise ValueError(f"Signal not found: {old_signal_id}")

        # Build new signal kwargs from old, allow overrides
        new_kwargs = {
            "signal_type":   kwargs.get("signal_type",   old["signal_type"]),
            "source":        kwargs.get("source",        old["source"]),
            "source_detail": kwargs.get("source_detail", old["source_detail"]),
            "domain":        json.loads(old["domain"]),
            "applies_to":    json.loads(old["applies_to"]),
            "stance":        new_stance,
            "is_actionable": bool(old["is_actionable"]),
            "brief_date":    old["brief_date"],
        }
        new_kwargs.update(kwargs)

        # Save new version (incremented version number)
        new_id = self.save(
            title=new_title,
            body=new_body,
            confidence=new_confidence,
            **new_kwargs,
        )

        # Set version on new signal
        old_version = old["version"] or 1
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE signals SET version = ? WHERE id = ?",
                (old_version + 1, new_id)
            )
            # Chain old to new, close old
            conn.execute(
                """UPDATE signals
                   SET status = 'superseded', superseded_by = ?,
                       closed_at = ?, close_reason = ?,
                       outcome_note = ?, updated_at = ?
                   WHERE id = ?""",
                (new_id, now, reason, outcome_note, now, old_signal_id)
            )

        return new_id

    # ── QUERIES ──────────────────────────────

    def get(self, signal_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            return dict(row) if row else None

    def active(
        self,
        signal_type: Optional[str] = None,
        applies_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Return active signals, optionally filtered."""
        query = "SELECT * FROM active_signals"
        params: List[Any] = []
        conditions = []

        if signal_type:
            conditions.append("signal_type = ?")
            params.append(signal_type)
        if applies_to:
            conditions.append("applies_to LIKE ?")
            params.append(f'%"{applies_to}"%')

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" LIMIT {limit}"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def due_for_validation(self) -> List[Dict]:
        """Return all signals due for monthly review."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM signals_due_for_validation").fetchall()
            return [dict(r) for r in rows]

    def opinion_ledger(self) -> List[Dict]:
        """Return all changed opinions/beliefs with full audit trail."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM opinion_ledger").fetchall()
            return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Full-text search across title, body, raw_source_text, source_detail."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT s.* FROM signals s
                   JOIN signals_fts f ON s.rowid = f.rowid
                   WHERE signals_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_briefs(self, days: int = 7) -> List[Dict]:
        """Signals from the last N days of morning briefs."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM signals
                   WHERE brief_date >= ? AND status = 'active'
                   ORDER BY brief_date DESC, is_actionable DESC""",
                (since,)
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> Dict:
        """Quick DB health stats."""
        with self._conn() as conn:
            total       = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            active      = conn.execute("SELECT COUNT(*) FROM signals WHERE status='active'").fetchone()[0]
            due         = conn.execute("SELECT COUNT(*) FROM signals_due_for_validation").fetchone()[0]
            validated   = conn.execute("SELECT COUNT(*) FROM signals WHERE status='validated'").fetchone()[0]
            invalidated = conn.execute("SELECT COUNT(*) FROM signals WHERE status='invalidated'").fetchone()[0]
            superseded  = conn.execute("SELECT COUNT(*) FROM signals WHERE status='superseded'").fetchone()[0]
            return {
                "total": total,
                "active": active,
                "due_for_validation": due,
                "validated": validated,
                "invalidated": invalidated,
                "superseded": superseded,
            }

    # ── BATCH SAVE FROM MORNING BRIEF ────────

    def save_brief_signals(self, brief_date: str, signals: List[Dict]) -> List[str]:
        """
        Batch-save signals extracted from a morning brief.
        Each dict in `signals` follows the save() keyword signature.
        Returns list of saved signal IDs.
        """
        ids = []
        for sig in signals:
            sig = {k: v for k, v in sig.items() if k != "brief_date"}  # avoid duplicate kwarg
            sig_id = self.save(brief_date=brief_date, **sig)
            ids.append(sig_id)
        return ids
