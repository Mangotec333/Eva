"""
EVA Diracatron — the top-level autonomous triage brain
======================================================

Diracatron sits on top of everything as the primary triage agent that knows
everything that is happening. It reads eva-state + activity + signals, ranks
priorities, dispatches to agents, and logs decisions back to eva-state so Eva
learns. This fills the autonomy gap for the 2-month handoff to Eva as primary
console.

Concretely, one triage *pass* does four things:

  1. **Poll** three read surfaces (behind Protocols, so tests use stubs and
     touch no network):
       * the eva-state append-only ledger (:8769) — recent events + derived
         pending-approvals / open-blockers,
       * the logger context/activity API (:8765),
       * inbound signals (an optional signals feed).
  2. **Normalise** every raw item into a candidate ``{kind, entity_id,
     summary, source, payload}``.
  3. **Rank** candidates by priority (kind weight + payload bumps + recency)
     and persist them idempotently into the triage queue (cron-safe).
  4. **Dispatch** a chosen item to the right downstream agent and log the
     decision back to eva-state via ``state_client`` so the system learns.

Stdlib only (``urllib`` for all HTTP). Slack alerts reuse
``modules/social-publish/slack_client.py`` — never duplicated, always
best-effort. No secrets are read here beyond what sibling modules already read
from the environment.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

STATE_URL = os.environ.get("EVA_STATE_URL", "http://localhost:8769")
CONTEXT_URL = os.environ.get("EVA_CONTEXT_URL", "http://localhost:8765")
SIGNALS_URL = os.environ.get("EVA_SIGNALS_URL", "")  # optional inbound feed

# ---------------------------------------------------------------------------
# Triage vocabulary — the kinds of open item the brain reasons about, their
# base priority weight, and the downstream agent that owns each kind.
# ---------------------------------------------------------------------------

KIND_NEW_LEAD = "new_lead"
KIND_BROKER_REPLY = "broker_reply"
KIND_DEAL_SCORE = "deal_score_threshold"
KIND_REVENUE_LEAK = "revenue_leak"
KIND_CONTENT_DRAFT = "content_draft_pending"
KIND_STALLED_TASK = "stalled_task"

# A broker who replied is a human waiting on us — highest. A brand-new lead is
# next. Everything else is proactive work that can queue behind those two.
PRIORITY = {
    KIND_BROKER_REPLY: 100,
    KIND_NEW_LEAD: 90,
    KIND_DEAL_SCORE: 80,
    KIND_REVENUE_LEAK: 70,
    KIND_CONTENT_DRAFT: 60,
    KIND_STALLED_TASK: 50,
}

# kind -> (downstream agent slug, port or None if delegated via launcher,
#          dispatch route). Ports mirror EVA_AGENT_CATALOG.md.
ROUTES = {
    KIND_NEW_LEAD: ("ghl-agent", 8782, "/lead/capture"),
    KIND_BROKER_REPLY: ("pathfinder", 8773, "/pathfinder/lead"),
    KIND_DEAL_SCORE: ("deal-scout", 8766, "/deals/score"),
    KIND_REVENUE_LEAK: ("monetizing-agent", 8772, "/scan"),
    KIND_CONTENT_DRAFT: ("social-publish", None, "/social/submit"),
    KIND_STALLED_TASK: ("content-engine", 8767, "/tick"),
}

# eva-state event_type -> triage kind. Only the events the brain acts on are
# mapped; everything else is ignored.
EVENT_KIND = {
    "lead_captured": KIND_NEW_LEAD,
    "lead_engaged": KIND_BROKER_REPLY,
    "lead_replied": KIND_BROKER_REPLY,
    "broker_reply": KIND_BROKER_REPLY,
    "deal_scored": KIND_DEAL_SCORE,
    "deal_score_threshold": KIND_DEAL_SCORE,
    "revenue_leak_found": KIND_REVENUE_LEAK,
    "revenue_leak": KIND_REVENUE_LEAK,
    "content_draft": KIND_CONTENT_DRAFT,
    "content_draft_pending": KIND_CONTENT_DRAFT,
    "task_stalled": KIND_STALLED_TASK,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(url: str, timeout: float = 5.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, body: dict, timeout: float = 5.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        return {"ok": 200 <= resp.status < 300, "status": resp.status,
                "body": parsed}


def normalise_event(event: dict, source: str = "eva-state") -> Optional[dict]:
    """Turn a raw eva-state event into a triage candidate, or None to ignore."""
    etype = (event.get("event_type") or "").strip().lower()
    kind = EVENT_KIND.get(etype)
    if not kind:
        return None
    return {
        "kind": kind,
        "entity_id": event.get("entity_id") or event.get("id") or "",
        "summary": event.get("summary") or f"{etype} event",
        "source": source,
        "payload": event.get("payload") or {},
    }


def score(candidate: dict) -> int:
    """Priority score = kind weight + payload bumps. Higher ranks first."""
    kind = candidate["kind"]
    base = PRIORITY.get(kind, 10)
    payload = candidate.get("payload") or {}
    bump = 0
    # A deal that crossed a *high* score threshold jumps the queue.
    if kind == KIND_DEAL_SCORE:
        try:
            bump += min(int(float(payload.get("score", 0))) // 10, 15)
        except (TypeError, ValueError):
            bump = 0
    # An explicit urgent flag from any upstream nudges priority.
    if payload.get("urgent"):
        bump += 20
    return base + bump


def route_for(candidate: dict) -> str:
    """Which downstream agent owns this candidate. A stalled task routes back
    to the agent that stalled (from payload) when known, else its default."""
    kind = candidate["kind"]
    if kind == KIND_STALLED_TASK:
        agent = (candidate.get("payload") or {}).get("agent")
        if agent:
            return agent
    return ROUTES.get(kind, ("unknown", None, "/"))[0]


# ---------------------------------------------------------------------------
# Read surfaces (Protocols) — live HTTP impls + in-memory stubs for tests.
# ---------------------------------------------------------------------------

@runtime_checkable
class CandidateSource(Protocol):
    def candidates(self) -> list[dict]: ...


class StubSource:
    """Offline source — returns a fixed list of candidates. Tests inject this."""

    def __init__(self, candidates: Optional[list[dict]] = None) -> None:
        self._candidates = candidates or []

    def candidates(self) -> list[dict]:
        return list(self._candidates)


class HttpStateSource:
    """Live source — reads recent events + derived state from eva-state."""

    def __init__(self, base_url: str = STATE_URL, limit: int = 100,
                 timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.limit = limit
        self.timeout = timeout

    def candidates(self) -> list[dict]:
        out: list[dict] = []
        try:
            events = _get_json(
                f"{self.base_url}/events?limit={self.limit}", self.timeout)
            for ev in events if isinstance(events, list) else []:
                cand = normalise_event(ev)
                if cand:
                    out.append(cand)
        except Exception:  # ledger down — degrade, never raise
            pass
        # Derived surfaces map straight onto kinds.
        for url, kind, src in (
            (f"{self.base_url}/state/pending-approvals", KIND_CONTENT_DRAFT,
             "eva-state:pending-approvals"),
            (f"{self.base_url}/state/open-blockers", KIND_STALLED_TASK,
             "eva-state:open-blockers"),
        ):
            try:
                rows = _get_json(url, self.timeout)
                for row in rows if isinstance(rows, list) else []:
                    out.append({
                        "kind": kind,
                        "entity_id": row.get("entity_id") or row.get("id") or "",
                        "summary": row.get("summary") or kind,
                        "source": src,
                        "payload": row,
                    })
            except Exception:
                pass
        return out


class HttpContextSource:
    """Live source — reads the logger activity/context API for signals."""

    def __init__(self, base_url: str = CONTEXT_URL, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def candidates(self) -> list[dict]:
        # The context API surfaces activity, not triage items directly; we only
        # lift entries it explicitly tags with a triage ``kind``. Absent that,
        # it contributes nothing (and never raises).
        out: list[dict] = []
        try:
            data = _get_json(f"{self.base_url}/context", self.timeout)
        except Exception:
            return out
        items = data.get("items", []) if isinstance(data, dict) else []
        for it in items:
            kind = EVENT_KIND.get((it.get("event_type") or "").lower())
            if kind:
                out.append({
                    "kind": kind,
                    "entity_id": it.get("entity_id", ""),
                    "summary": it.get("summary", kind),
                    "source": "context",
                    "payload": it,
                })
        return out


class HttpSignalSource:
    """Live source — an optional inbound signals feed (webhooks/queues)."""

    def __init__(self, url: str = SIGNALS_URL, timeout: float = 5.0) -> None:
        self.url = url.rstrip("/") if url else ""
        self.timeout = timeout

    def candidates(self) -> list[dict]:
        if not self.url:
            return []
        try:
            rows = _get_json(self.url, self.timeout)
        except Exception:
            return []
        out: list[dict] = []
        for row in rows if isinstance(rows, list) else []:
            kind = EVENT_KIND.get((row.get("event_type") or "").lower())
            if kind:
                out.append({
                    "kind": kind,
                    "entity_id": row.get("entity_id", ""),
                    "summary": row.get("summary", kind),
                    "source": "signal",
                    "payload": row,
                })
        return out


# ---------------------------------------------------------------------------
# Dispatcher (Protocol) — live HTTP POST + in-memory stub for tests.
# ---------------------------------------------------------------------------

@runtime_checkable
class Dispatcher(Protocol):
    def dispatch(self, *, agent: str, route: str, port: Optional[int],
                 item: dict) -> dict: ...


class StubDispatcher:
    """Offline dispatcher — records calls, fires nothing. Tests inject this."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def dispatch(self, *, agent: str, route: str, port: Optional[int],
                 item: dict) -> dict:
        self.calls.append({"agent": agent, "route": route, "port": port,
                           "item_id": item.get("id"), "kind": item.get("kind")})
        return {"ok": True, "stub": True, "agent": agent, "route": route}


class HttpDispatcher:
    """Live dispatcher — POSTs the item to the downstream agent's route.

    Agents with a port are called directly; port-less agents (e.g.
    social-publish) are delegated through the launcher on :8768, exactly like
    the launcher already fronts those gates.
    """

    def __init__(self, launcher_url: str = "http://localhost:8768",
                 host: str = "http://localhost", timeout: float = 5.0) -> None:
        self.launcher_url = launcher_url.rstrip("/")
        self.host = host.rstrip("/")
        self.timeout = timeout

    def dispatch(self, *, agent: str, route: str, port: Optional[int],
                 item: dict) -> dict:
        base = f"{self.host}:{port}" if port else self.launcher_url
        url = f"{base}{route}"
        body = {"triage_item_id": item.get("id"), "kind": item.get("kind"),
                "entity_id": item.get("entity_id"), "summary": item.get("summary"),
                "payload": item.get("payload") or {}}
        try:
            return {**_post_json(url, body, self.timeout), "agent": agent, "url": url}
        except Exception as exc:  # agent down — honest failure, item stays queued
            return {"ok": False, "agent": agent, "url": url,
                    "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Slack alert — reuse social-publish's client, never duplicate it.
# ---------------------------------------------------------------------------

def slack_alert(text: str) -> dict:
    """Best-effort Slack alert via modules/social-publish/slack_client.py.

    Absence of the module or ``SLACK_BOT_TOKEN`` is non-fatal (returns ok=False).
    """
    import sys
    social_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "social-publish")
    if social_dir not in sys.path:
        sys.path.insert(0, social_dir)
    try:
        import slack_client  # type: ignore  # noqa: PLC0415
    except Exception as exc:
        return {"ok": False, "error": f"slack_client unavailable: {exc}"}
    if not slack_client.is_configured():
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
    return slack_client.post_message(text)


def build_sources(offline: Optional[bool] = None) -> list[CandidateSource]:
    """Live read surfaces, or a single empty stub when offline."""
    if offline is None:
        offline = os.environ.get("EVA_DIRACATRON_OFFLINE") == "1"
    if offline:
        return [StubSource([])]
    return [HttpStateSource(), HttpContextSource(), HttpSignalSource()]


def build_dispatcher(offline: Optional[bool] = None) -> Dispatcher:
    if offline is None:
        offline = os.environ.get("EVA_DIRACATRON_OFFLINE") == "1"
    return StubDispatcher() if offline else HttpDispatcher()
