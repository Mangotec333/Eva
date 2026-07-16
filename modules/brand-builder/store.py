"""
EVA Brand-Builder — the local JSON store (config-file-primary).

The Brand Builder is the strategy/orchestration layer that sits ABOVE
content-engine (:8767) and social-scheduler (:8787). It writes content BRIEFS;
it never posts. Everything it owns lives as plain JSON files under the Eva data
directory — no SQLite, no SaaS DB — following the same config-file-primary
pattern as ``modules/social-publish/credentials.py``:

  ~/.eva/brand_builder/
    pipelines/<pipeline_id>.json      one strategy pipeline
    blueprints/<category-slug>.json   one market blueprint per category
    personas/<name>.json              persistent persona configs
    briefs/<brief_id>.json            content briefs (pending until queued)

The root is overridable with ``EVA_BRAND_DIR`` so the launchd service / tests can
point it anywhere. Stdlib only (json, pathlib).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


def brand_dir() -> Path:
    """Root data dir (``EVA_BRAND_DIR`` override, else ~/.eva/brand_builder)."""
    override = os.environ.get("EVA_BRAND_DIR", "").strip()
    root = Path(override) if override else (Path.home() / ".eva" / "brand_builder")
    return root


def _sub(name: str) -> Path:
    d = brand_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    """Stable, filesystem-safe slug for category / id keys."""
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "unknown"


def _write_json(path: Path, data: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return data


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# pipelines
# ---------------------------------------------------------------------------

def save_pipeline(pipeline: dict) -> dict:
    pid = pipeline.get("pipeline_id") or slugify(pipeline.get("category", ""))
    pipeline["pipeline_id"] = pid
    pipeline.setdefault("created_at", now_iso())
    pipeline["updated_at"] = now_iso()
    return _write_json(_sub("pipelines") / f"{pid}.json", pipeline)


def get_pipeline(pipeline_id: str) -> dict | None:
    return _read_json(_sub("pipelines") / f"{pipeline_id}.json")


def list_pipelines() -> list[dict]:
    out = []
    for p in sorted(_sub("pipelines").glob("*.json")):
        d = _read_json(p)
        if d:
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# blueprints (one per category)
# ---------------------------------------------------------------------------

def save_blueprint(category: str, blueprint: dict) -> dict:
    blueprint.setdefault("category", category)
    blueprint["updated_at"] = now_iso()
    return _write_json(_sub("blueprints") / f"{slugify(category)}.json", blueprint)


def get_blueprint(category: str) -> dict | None:
    return _read_json(_sub("blueprints") / f"{slugify(category)}.json")


def list_blueprints() -> list[dict]:
    out = []
    for p in sorted(_sub("blueprints").glob("*.json")):
        d = _read_json(p)
        if d:
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# personas
# ---------------------------------------------------------------------------

def save_persona(name: str, persona: dict) -> dict:
    persona.setdefault("name", name)
    persona["updated_at"] = now_iso()
    return _write_json(_sub("personas") / f"{name}.json", persona)


def get_persona(name: str) -> dict | None:
    return _read_json(_sub("personas") / f"{name}.json")


def list_personas() -> list[dict]:
    out = []
    for p in sorted(_sub("personas").glob("*.json")):
        d = _read_json(p)
        if d:
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# briefs
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_QUEUED = "queued"


def save_brief(brief: dict) -> dict:
    bid = brief.get("brief_id") or str(uuid.uuid4())
    brief["brief_id"] = bid
    brief.setdefault("status", STATUS_PENDING)
    brief.setdefault("created_at", now_iso())
    return _write_json(_sub("briefs") / f"{bid}.json", brief)


def get_brief(brief_id: str) -> dict | None:
    return _read_json(_sub("briefs") / f"{brief_id}.json")


def list_briefs(status: str | None = None) -> list[dict]:
    out = []
    for p in sorted(_sub("briefs").glob("*.json")):
        d = _read_json(p)
        if d and (status is None or d.get("status") == status):
            out.append(d)
    out.sort(key=lambda b: (b.get("scheduled_day", ""), b.get("created_at", "")))
    return out


def update_brief(brief_id: str, fields: dict) -> dict | None:
    d = get_brief(brief_id)
    if d is None:
        return None
    d.update(fields)
    d["updated_at"] = now_iso()
    return _write_json(_sub("briefs") / f"{brief_id}.json", d)


__all__ = [
    "brand_dir", "now_iso", "slugify",
    "save_pipeline", "get_pipeline", "list_pipelines",
    "save_blueprint", "get_blueprint", "list_blueprints",
    "save_persona", "get_persona", "list_personas",
    "STATUS_PENDING", "STATUS_QUEUED",
    "save_brief", "get_brief", "list_briefs", "update_brief",
]
