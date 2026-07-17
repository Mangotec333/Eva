"""
EVA IP-Scout — local store (config-file-primary JSON + sqlite).

IP-Scout is an L1-autonomy prior-art triage lobe: it triages invention-idea
seeds against prior art and reports what's worth an attorney's review. It NEVER
files anything. Everything it owns lives locally under the Eva data dir — no SaaS
DB — following the same config-file-primary pattern as the other lobes:

  ~/.eva/ip_ideas.json              user-seeded idea records (the seed surface)
  ~/.eva/ip_scout/ip_scout.db       sqlite: invention disclosures + run history
  ~/.eva/ip_scout/reports/<date>.md daily markdown triage reports

Overrides for the launchd service / tests:
  EVA_IP_IDEAS_FILE  → the ideas json path (else ~/.eva/ip_ideas.json)
  EVA_IP_DIR         → the ip_scout data dir (else ~/.eva/ip_scout)

Stdlib only (json, sqlite3, pathlib).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_TRIAGED = "triaged"
STATUS_ARCHIVED = "archived"

REC_FILE = "file"
REC_MONITOR = "monitor"
REC_DROP = "drop"


def ideas_file() -> Path:
    override = os.environ.get("EVA_IP_IDEAS_FILE", "").strip()
    return Path(override) if override else (Path.home() / ".eva" / "ip_ideas.json")


def ip_dir() -> Path:
    override = os.environ.get("EVA_IP_DIR", "").strip()
    root = Path(override) if override else (Path.home() / ".eva" / "ip_scout")
    root.mkdir(parents=True, exist_ok=True)
    return root


def reports_dir() -> Path:
    d = ip_dir() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return ip_dir() / "ip_scout.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_MEM_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ledger (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL DEFAULT '',
    entity_id    TEXT NOT NULL DEFAULT '',
    actor        TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TRIGGER IF NOT EXISTS ledger_no_update
BEFORE UPDATE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS ledger_no_delete
BEFORE DELETE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;
"""


def slugify(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "unknown"


# ---------------------------------------------------------------------------
# ideas (~/.eva/ip_ideas.json)
# ---------------------------------------------------------------------------

def _read_ideas_raw() -> list[dict]:
    path = ideas_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("ideas", [])
    return [d for d in data if isinstance(d, dict)]


def _write_ideas_raw(ideas: list[dict]) -> None:
    path = ideas_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"ideas": ideas}, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(path)


def list_ideas(status: str | None = None) -> list[dict]:
    ideas = _read_ideas_raw()
    if status is not None:
        ideas = [i for i in ideas if i.get("status") == status]
    ideas.sort(key=lambda i: i.get("seeded_at", ""))
    return ideas


def get_idea(idea_id: str) -> dict | None:
    for i in _read_ideas_raw():
        if i.get("id") == idea_id:
            return i
    return None


def save_idea(idea: dict) -> dict:
    """Insert or update an idea record by id (id/title/description/category/
    seeded_at/status). Returns the persisted record."""
    iid = idea.get("id") or slugify(idea.get("title", "")) or str(uuid.uuid4())
    idea["id"] = iid
    idea.setdefault("category", "uncategorized")
    idea.setdefault("seeded_at", now_iso())
    idea.setdefault("status", STATUS_PENDING)
    ideas = _read_ideas_raw()
    for n, existing in enumerate(ideas):
        if existing.get("id") == iid:
            existing.update(idea)
            ideas[n] = existing
            _write_ideas_raw(ideas)
            return existing
    ideas.append(idea)
    _write_ideas_raw(ideas)
    return idea


def update_idea(idea_id: str, fields: dict) -> dict | None:
    ideas = _read_ideas_raw()
    for n, existing in enumerate(ideas):
        if existing.get("id") == idea_id:
            existing.update(fields)
            ideas[n] = existing
            _write_ideas_raw(ideas)
            return existing
    return None


# ---------------------------------------------------------------------------
# sqlite: invention disclosures + run history
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS disclosures (
            disclosure_id         TEXT PRIMARY KEY,
            idea_id               TEXT,
            title                 TEXT,
            abstract              TEXT,
            claims_draft          TEXT,
            sensor_source         TEXT,
            created_at            TEXT,
            novelty_score         REAL,
            confidence_band       TEXT,
            prior_art_hits        TEXT,
            status                TEXT,
            attorney_review_needed INTEGER,
            recommendation        TEXT,
            run_id                TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id               TEXT PRIMARY KEY,
            started_at           TEXT,
            finished_at          TEXT,
            report_date          TEXT,
            ideas_scanned        INTEGER,
            disclosures_created  INTEGER,
            offline              INTEGER,
            provider             TEXT,
            report_path          TEXT,
            summary              TEXT
        )
    """)
    # Canonical per-agent memory + append-only ledger (Architecture Directive).
    # Schema + immutability triggers copied verbatim from the reference modules
    # (modules/postcards, modules/meet-ingest).
    conn.executescript(_MEM_LEDGER_SCHEMA)
    return conn


def _disclosure_from_row(row: sqlite3.Row) -> dict:
    return {
        "disclosure_id": row["disclosure_id"],
        "idea_id": row["idea_id"],
        "title": row["title"],
        "abstract": row["abstract"],
        "claims_draft": json.loads(row["claims_draft"] or "[]"),
        "sensor_source": row["sensor_source"],
        "created_at": row["created_at"],
        "novelty_score": row["novelty_score"],
        "confidence_band": row["confidence_band"],
        "prior_art_hits": json.loads(row["prior_art_hits"] or "[]"),
        "status": row["status"],
        "attorney_review_needed": bool(row["attorney_review_needed"]),
        "recommendation": row["recommendation"],
        "run_id": row["run_id"],
    }


def save_disclosure(disc: dict) -> dict:
    disc.setdefault("disclosure_id", str(uuid.uuid4()))
    disc.setdefault("created_at", now_iso())
    conn = _connect()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO disclosures (
                disclosure_id, idea_id, title, abstract, claims_draft,
                sensor_source, created_at, novelty_score, confidence_band,
                prior_art_hits, status, attorney_review_needed, recommendation, run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            disc["disclosure_id"], disc.get("idea_id", ""), disc.get("title", ""),
            disc.get("abstract", ""), json.dumps(disc.get("claims_draft", [])),
            disc.get("sensor_source", ""), disc["created_at"],
            float(disc.get("novelty_score", 0.0)), disc.get("confidence_band", "low"),
            json.dumps(disc.get("prior_art_hits", [])), disc.get("status", "triaged"),
            1 if disc.get("attorney_review_needed") else 0,
            disc.get("recommendation", REC_MONITOR), disc.get("run_id", ""),
        ))
        conn.commit()
    finally:
        conn.close()
    return disc


def get_disclosure(disclosure_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM disclosures WHERE disclosure_id = ?",
            (disclosure_id,)).fetchone()
        return _disclosure_from_row(row) if row else None
    finally:
        conn.close()


def latest_disclosure_for_idea(idea_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM disclosures WHERE idea_id = ? "
            "ORDER BY created_at DESC LIMIT 1", (idea_id,)).fetchone()
        return _disclosure_from_row(row) if row else None
    finally:
        conn.close()


def list_disclosures(run_id: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        if run_id:
            rows = conn.execute(
                "SELECT * FROM disclosures WHERE run_id = ? ORDER BY created_at",
                (run_id,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM disclosures ORDER BY created_at DESC").fetchall()
        return [_disclosure_from_row(r) for r in rows]
    finally:
        conn.close()


def save_run(run: dict) -> dict:
    run.setdefault("run_id", str(uuid.uuid4()))
    run.setdefault("started_at", now_iso())
    conn = _connect()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO runs (
                run_id, started_at, finished_at, report_date, ideas_scanned,
                disclosures_created, offline, provider, report_path, summary
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            run["run_id"], run["started_at"], run.get("finished_at", ""),
            run.get("report_date", ""), int(run.get("ideas_scanned", 0)),
            int(run.get("disclosures_created", 0)), 1 if run.get("offline") else 0,
            run.get("provider", ""), run.get("report_path", ""),
            json.dumps(run.get("summary", {})),
        ))
        conn.commit()
    finally:
        conn.close()
    return run


def list_runs(limit: int | None = None) -> list[dict]:
    conn = _connect()
    try:
        q = "SELECT * FROM runs ORDER BY started_at DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = conn.execute(q).fetchall()
        out = []
        for r in rows:
            out.append({
                "run_id": r["run_id"], "started_at": r["started_at"],
                "finished_at": r["finished_at"], "report_date": r["report_date"],
                "ideas_scanned": r["ideas_scanned"],
                "disclosures_created": r["disclosures_created"],
                "offline": bool(r["offline"]), "provider": r["provider"],
                "report_path": r["report_path"],
                "summary": json.loads(r["summary"] or "{}"),
            })
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# reports (markdown on disk)
# ---------------------------------------------------------------------------

def save_report(report_date: str, markdown: str) -> str:
    path = reports_dir() / f"{report_date}.md"
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(path)
    return str(path)


def get_report(report_date: str) -> str | None:
    path = reports_dir() / f"{report_date}.md"
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None


def list_report_dates() -> list[str]:
    return sorted(p.stem for p in reports_dir().glob("*.md"))


# ---------------------------------------------------------------------------
# memory (per-agent knowledge) + append-only ledger accessors
# ---------------------------------------------------------------------------

def set_memory(key: str, value: str, source: str = "system") -> dict:
    now = now_iso()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO memory (key, value, ts, source) VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value, ts=excluded.ts, source=excluded.source""",
            (key, value, now, source),
        )
        conn.commit()
    finally:
        conn.close()
    return {"key": key, "value": value, "ts": now, "source": source}


def get_memory(key: str, default: str | None = None) -> str | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def list_memory() -> list[dict]:
    conn = _connect()
    try:
        return [dict(r) for r in
                conn.execute("SELECT * FROM memory ORDER BY key").fetchall()]
    finally:
        conn.close()


def append_ledger(event_type: str, entity_type: str = "", entity_id: str = "",
                  actor: str = "", details: dict | None = None) -> dict:
    row = {
        "id": str(uuid.uuid4()), "ts": now_iso(), "event_type": event_type,
        "entity_type": entity_type, "entity_id": entity_id, "actor": actor,
        "details_json": json.dumps(details or {}),
    }
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO ledger
               (id, ts, event_type, entity_type, entity_id, actor, details_json)
               VALUES (:id,:ts,:event_type,:entity_type,:entity_id,:actor,:details_json)""",
            row,
        )
        conn.commit()
    finally:
        conn.close()
    out = dict(row)
    out["details"] = json.loads(out.pop("details_json"))
    return out


def query_ledger(event_type: str | None = None) -> list[dict]:
    q, params = "SELECT * FROM ledger", []
    if event_type:
        q += " WHERE event_type=?"
        params.append(event_type)
    q += " ORDER BY ts ASC"
    conn = _connect()
    try:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()
    for r in rows:
        try:
            r["details"] = json.loads(r.get("details_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["details"] = {}
    return rows


__all__ = [
    "STATUS_PENDING", "STATUS_TRIAGED", "STATUS_ARCHIVED",
    "REC_FILE", "REC_MONITOR", "REC_DROP",
    "ideas_file", "ip_dir", "reports_dir", "db_path", "now_iso", "slugify",
    "list_ideas", "get_idea", "save_idea", "update_idea",
    "save_disclosure", "get_disclosure", "latest_disclosure_for_idea",
    "list_disclosures", "save_run", "list_runs",
    "save_report", "get_report", "list_report_dates",
    "set_memory", "get_memory", "list_memory",
    "append_ledger", "query_ledger",
]
