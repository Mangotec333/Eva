"""
EVA State Ledger — idempotent seed + Kalpawriksha importer
==========================================================

Two seed sources, both idempotent (re-running never duplicates):

1. :func:`import_project_map` — parses the current static Kalpawriksha
   (``eva-project-map/index.html``, bundled under ``seed/``) into seed events.
   Each terminal node carrying a status badge becomes one event. The badge map:

       Production-Live -> live      In Progress -> in_progress
       Open            -> open      Planned     -> planned
       Blocked         -> blocked

2. :func:`seed_lost_state` — the state lost from Jul 8–10 that never made it into
   the static map (Monetizing Agent, kb_index, Book Agent corpus/scaffold, the
   Sunday recurring task, Storeys fund formation, the eva-panel blocker, the
   external Sunday cron, and the ScissorHands coined term).

:func:`seed_all` runs both and then writes the ``batch.ai`` correction: the map
still shows it Open (LOI sent, awaiting broker) but Vineet walked away 2026-06-05,
so a ``correction_event`` supersedes it, dropping the deal.

Idempotency is by content identity: :func:`_append_once` skips an event whose
(entity_type, entity_id, event_type, summary) already exists.
"""

from __future__ import annotations

import os
import re
from html import unescape

import memory

HERE = os.path.dirname(__file__)
SOURCE_HTML = os.path.join(HERE, "seed", "project_map_source.html")

# HTML section comment -> (project, entity_type) for imported nodes.
_SECTIONS = {
    "HOSTED INTERFACES": ("Hosted Interfaces", "interface"),
    "AGENT OPERATING MODEL": ("Agent Operating Model", "module"),
    "MODULES": ("Modules", "module"),
    "ACQUISITION PIPELINE": ("Acquisition Pipeline", "deal"),
    "INFRASTRUCTURE": ("Infrastructure & Backlog", "task"),
}

# badge css class -> ledger status
_BADGE_STATUS = {
    "b-live": memory.STATUS_LIVE,
    "b-prog": memory.STATUS_IN_PROGRESS,
    "b-open": memory.STATUS_OPEN,
    "b-plan": memory.STATUS_PLANNED,
    "b-block": memory.STATUS_BLOCKED,
}

# ledger status -> (event_type, entity_type override or None)
_STATUS_EVENT = {
    memory.STATUS_LIVE:        ("project_status_changed", None),
    memory.STATUS_IN_PROGRESS: ("project_status_changed", None),
    memory.STATUS_OPEN:        ("task_created", None),
    memory.STATUS_PLANNED:     ("task_created", None),
    memory.STATUS_BLOCKED:     ("blocker_added", "blocker"),
}

_IMPORT_TS = "2026-07-08T00:00:00+00:00"   # the static map's "Last refresh"


def _append_once(*, path: str, **kwargs) -> str:
    """Append an event unless an identical one already exists (idempotent).

    Identity = (entity_type, entity_id, event_type, summary).
    """
    existing = memory.list_events(
        entity_type=kwargs.get("entity_type"),
        entity_id=kwargs.get("entity_id"),
        event_type=kwargs.get("event_type"),
        path=path,
    )
    summary = kwargs.get("summary", "")
    for e in existing:
        if e["summary"] == summary:
            return e["event_id"]
    return memory.append_event(path=path, **kwargs)


# ---------------------------------------------------------------------------
# Kalpawriksha HTML importer
# ---------------------------------------------------------------------------

_NODE_RE = re.compile(r'<div class="node"[^>]*>(.*?)</div>', re.DOTALL)
_LBL_RE = re.compile(r'<span class="lbl"[^>]*>(.*?)</span>', re.DOTALL)
_LINK_RE = re.compile(r'<a class="link" href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_DESC_RE = re.compile(r'<span class="desc">(.*?)</span>', re.DOTALL)
_BADGE_RE = re.compile(r'<span class="badge (b-\w+)">(.*?)</span>', re.DOTALL)
_SECTION_RE = re.compile(r'<!--\s*(.*?)\s*-->')
_TAG_RE = re.compile(r'<[^>]+>')


def _text(s: str) -> str:
    return unescape(_TAG_RE.sub("", s or "")).strip()


def import_project_map(db_path: str = memory.DB_PATH,
                       html_path: str = SOURCE_HTML) -> dict:
    """Parse the static Kalpawriksha HTML into seed events (idempotent).

    Returns ``{"created": [event_ids], "by_key": {entity_id: event}}``.
    """
    if not os.path.exists(html_path):
        return {"created": [], "by_key": {}, "error": f"source not found: {html_path}"}
    with open(html_path, "r", encoding="utf-8") as fh:
        doc = fh.read()

    # Walk the document, tracking the current section from HTML comments.
    created: list[str] = []
    by_key: dict[str, dict] = {}
    pos = 0
    current = ("Unsorted", "task")
    # Build a list of (index, kind, value) tokens for sections and nodes in order.
    tokens = []
    for m in _SECTION_RE.finditer(doc):
        label = m.group(1).strip().upper()
        for key, mapping in _SECTIONS.items():
            if label.startswith(key):
                tokens.append((m.start(), "section", mapping))
                break
    for m in _NODE_RE.finditer(doc):
        tokens.append((m.start(), "node", m.group(1)))
    tokens.sort(key=lambda t: t[0])

    for _, kind, value in tokens:
        if kind == "section":
            current = value
            continue
        inner = value
        badge = _BADGE_RE.search(inner)
        if not badge:
            continue  # only terminal nodes carrying a status badge become events
        bclass, blabel = badge.group(1), _text(badge.group(2))
        status = _BADGE_STATUS.get(bclass, memory.STATUS_OPEN)

        link = _LINK_RE.search(inner)
        lbl_m = _LBL_RE.search(inner)
        desc_m = _DESC_RE.search(inner)
        url = ""
        if link:
            url = _text(link.group(1))
            label = _text(link.group(2))
        elif lbl_m:
            label = _text(lbl_m.group(1))
        else:
            label = _text(desc_m.group(1)) if desc_m else ""
        desc = _text(desc_m.group(1)) if desc_m else ""
        if not (label or desc):
            continue

        project, base_entity = current
        event_type, entity_override = _STATUS_EVENT.get(
            status, ("project_status_changed", None))
        entity_type = entity_override or base_entity
        name = label or desc
        entity_id = memory.slugify(name)
        summary = desc or label or name

        eid = _append_once(
            path=db_path, event_type=event_type, entity_type=entity_type,
            entity_id=entity_id, project=project, track="kalpawriksha-import",
            actor="Eva", source_surface="Kalpawriksha HTML",
            summary=summary, status=status,
            payload={"imported_from": "eva-project-map/index.html",
                     "badge": blabel, "label": name},
            evidence_urls=[url] if url else None,
            timestamp=_IMPORT_TS,
        )
        created.append(eid)
        by_key[entity_id] = memory.get_event(eid, db_path)

    return {"created": created, "by_key": by_key}


# ---------------------------------------------------------------------------
# Lost state (Jul 8–10) + ScissorHands coined term
# ---------------------------------------------------------------------------

def seed_lost_state(db_path: str = memory.DB_PATH) -> list[str]:
    """Seed the Jul 8–10 state that never made it into the static map."""
    ids: list[str] = []

    def once(**kw):
        ids.append(_append_once(path=db_path, **kw))

    once(event_type="artifact_created", entity_type="module",
         entity_id="monetizing-agent", project="Agent Operating Model",
         track="monetization", actor="Eva", source_surface="GitHub PR",
         summary="Monetizing Agent merged (PR #20) — governed weekly revenue-leak agent, port 8772",
         status=memory.STATUS_LIVE,
         payload={"pr": 20, "port": 8772, "merged": "2026-07-10"},
         evidence_urls=["https://github.com/Mangotec333/Eva/pull/20"],
         timestamp="2026-07-10T00:00:00+00:00")

    once(event_type="artifact_created", entity_type="module",
         entity_id="kb-index", project="Agent Operating Model",
         track="infrastructure", actor="Eva", source_surface="GitHub PR",
         summary="kb_index — shared Drive Master INDEX writer module (PR #20)",
         status=memory.STATUS_LIVE, payload={"pr": 20},
         evidence_urls=["https://github.com/Mangotec333/Eva/pull/20"],
         timestamp="2026-07-10T00:00:00+00:00")

    once(event_type="artifact_created", entity_type="artifact",
         entity_id="book-agent-corpus", project="Book Agent",
         track="corpus", actor="Eva", source_surface="Drive",
         summary="Book Agent corpus — Rich Gomez ingestion corpus + 33-question finalization set",
         status=memory.STATUS_LIVE,
         payload={"corpus": "Rich Gomez", "questions": 33},
         timestamp="2026-07-09T00:00:00+00:00")

    once(event_type="task_created", entity_type="task",
         entity_id="book-agent-scaffold", project="Book Agent",
         track="build", actor="Vineet", source_surface="Perplexity",
         summary="Book Agent scaffold — governed microservice, port 8773, pending build",
         status=memory.STATUS_PLANNED, payload={"port": 8773},
         timestamp="2026-07-10T00:00:00+00:00")

    once(event_type="task_created", entity_type="task",
         entity_id="sunday-monetizing-recurring", project="Agent Operating Model",
         track="monetization", actor="Vineet", source_surface="Perplexity",
         summary="Sunday monetizing recurring task — external Perplexity scheduled task, pending retirement once in-repo agent validates",
         status=memory.STATUS_OPEN,
         payload={"retire_after": "monetizing-agent validation"},
         timestamp="2026-07-08T00:00:00+00:00")

    once(event_type="task_created", entity_type="task",
         entity_id="storeys-fund-formation", project="Storeys",
         track="fund", actor="Vineet", source_surface="Perplexity",
         summary="Storeys fund formation — SEC Rule 506(c) accredited-verification gate, $1.29M+ down payments",
         status=memory.STATUS_OPEN,
         payload={"regulation": "SEC Rule 506(c)", "down_payments_usd": 1290000,
                  "deadline": "2026-09-30"},
         timestamp="2026-07-09T00:00:00+00:00")

    once(event_type="blocker_added", entity_type="blocker",
         entity_id="eva-panel-backend", project="Hosted Interfaces",
         track="deploy", actor="Eva", source_surface="cron",
         summary="eva-panel backend — 4 crons 404 on ping, never deployed",
         status=memory.STATUS_BLOCKED,
         payload={"crons_failing": 4, "symptom": "404 on /api/crons/ping"},
         timestamp="2026-07-08T00:00:00+00:00")

    once(event_type="task_created", entity_type="task",
         entity_id="external-sunday-cron-c31194a7", project="Agent Operating Model",
         track="monetization", actor="system", source_surface="cron",
         summary="External Sunday cron c31194a7 — temporary bootstrap, retire/downgrade once governed monetizing-agent validates",
         status=memory.STATUS_OPEN,
         payload={"cron_id": "c31194a7", "retire_after": "monetizing-agent validation"},
         timestamp="2026-07-08T00:00:00+00:00")

    return ids


def seed_scissorhands(db_path: str = memory.DB_PATH) -> str:
    """Seed the ScissorHands coined_term_created event (idempotent)."""
    entity_id = memory.slugify("ScissorHands")
    existing = memory.list_events(entity_type="coined_term", entity_id=entity_id,
                                  event_type="coined_term_created", path=db_path)
    if existing:
        return existing[0]["event_id"]
    return memory.append_event(
        path=db_path, event_type="coined_term_created", entity_type="coined_term",
        entity_id=entity_id, project="Personal Brand", track="coined-terms",
        actor="Vineet", source_surface="Twitter (manual)",
        summary="Coined term 'ScissorHands' (Football / defensive technique)",
        status=memory.STATUS_ACTIVE,
        payload={
            "term": "ScissorHands",
            "domain": "Football / defensive technique",
            "definition": ("two defenders pressing a star striker from opposite "
                           "sides like scissor blades to isolate and neutralize "
                           "the threat"),
            "first_published_surface": "Twitter (manual)",
            "first_published_url": "",
            "first_published_date": "2026-07-10",
        },
        timestamp="2026-07-10T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _batch_ai_correction(db_path: str) -> str | None:
    """Supersede the stale batch.ai 'Open' node — Vineet walked away 2026-06-05."""
    candidates = memory.list_events(entity_type="deal", path=db_path)
    target = None
    for e in candidates:
        if "batch" in (e["entity_id"] or "").lower() and e["status"] != memory.STATUS_SUPERSEDED \
                and e["event_type"] != "correction_event":
            target = e
            break
    if target is None:
        return None
    # Idempotency: don't re-correct if already superseded/dropped.
    already = memory.list_events(entity_type="deal", entity_id=target["entity_id"],
                                 event_type="correction_event", path=db_path)
    if already:
        return already[0]["event_id"]
    return memory.correct_event(
        target["event_id"],
        summary="batch.ai DROPPED — Vineet walked away 2026-06-05; supersedes the stale 'Open — LOI sent, awaiting broker' node",
        status=memory.STATUS_DROPPED, actor="Vineet", source_surface="Perplexity",
        payload={"walked_away": "2026-06-05", "reason": "deal abandoned"},
        evidence_urls=[], path=db_path,
    )


def seed_all(db_path: str = memory.DB_PATH, *, force: bool = False) -> dict:
    """Run the full idempotent seed: import map, lost state, ScissorHands, batch.ai fix."""
    memory.init_db(db_path)
    if force:
        # ``force`` only re-runs the append path; it never deletes (append-only).
        pass
    imported = import_project_map(db_path)
    lost = seed_lost_state(db_path)
    scissor = seed_scissorhands(db_path)
    batch_fix = _batch_ai_correction(db_path)
    result = {
        "imported": len(imported.get("created", [])),
        "lost_state": len(lost),
        "scissorhands_event": scissor,
        "batch_ai_correction": batch_fix,
        "total_events": memory.event_count(db_path),
    }
    memory.save_run(
        inputs={"source": "seed_all"},
        outputs=result,
        notes="idempotent seed: Kalpawriksha import + lost state + ScissorHands + batch.ai correction",
        path=db_path,
    )
    return result


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(seed_all(), indent=2, default=str))
