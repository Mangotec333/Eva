"""
EVA State Ledger — service layer (governed read/write surface)
=============================================================

Sits between the HTTP/CLI surfaces and the append-only ledger core. Owns the
governed concerns from the module standard:

- **Append-only writes.** Every write goes through :meth:`StateService.record`
  (a thin, audited wrapper over ``memory.append_event``). Corrections go through
  :meth:`StateService.correct` and are written as new ``correction_event`` rows —
  never edits/deletes.
- **Approval gate on irreversible actions.** Publishing a rebuilt Kalpawriksha
  ``index.html`` (an artifact that leaves the ledger and lands on a surface) is
  gated: it routes through a :class:`StateTransport` chokepoint. The offline
  ``StubStateTransport`` records intent and never fakes a real publish.
- **Transport behind a Protocol.** Mirrors monetizing-agent's seam: a Stub for
  tests, a subprocess chokepoint for the single place real side effects happen.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Optional, Protocol, runtime_checkable

import memory
import project_map


class NotFoundError(RuntimeError):
    pass


class ApprovalError(RuntimeError):
    """Raised when an irreversible publish is attempted without approval."""


# ---------------------------------------------------------------------------
# Transport (irreversible-action chokepoint: publishing a rebuilt map surface)
# ---------------------------------------------------------------------------

@runtime_checkable
class StateTransport(Protocol):
    def publish_map(self, html: str, dest: str) -> dict[str, Any]:
        """Publish a rendered Kalpawriksha ``index.html``. Returns ``{ok, ...}``."""


class StubStateTransport:
    """Offline transport used in tests. Records intent; performs no publish."""

    def __init__(self) -> None:
        self.published: list[dict] = []

    def publish_map(self, html: str, dest: str) -> dict[str, Any]:
        self.published.append({"dest": dest, "bytes": len(html)})
        return {"ok": True, "stub": True, "dest": dest, "bytes": len(html)}


class SubprocessStateTransport:
    """Real transport: writes the rendered map through a subprocess chokepoint.

    The chokepoint (``publish_map.py``) is the only place a live publish (Vercel
    deploy, Drive push) would run. Absent/failed → honest ``ok=False``.
    """

    def __init__(self, chokepoint: Optional[str] = None) -> None:
        self.chokepoint = chokepoint or os.path.join(
            os.path.dirname(__file__), "publish_map.py")

    def publish_map(self, html: str, dest: str) -> dict[str, Any]:
        if not os.path.exists(self.chokepoint):
            return {"ok": False, "stub": False,
                    "error": f"chokepoint not wired: {self.chokepoint}"}
        try:
            result = subprocess.run(
                ["python3", self.chokepoint, dest],
                input=html, capture_output=True, text=True, timeout=60,
            )
            return {"ok": result.returncode == 0, "stub": False,
                    "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "stub": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class StateService:
    def __init__(self, *, db_path: str = memory.DB_PATH,
                 transport: Optional[StateTransport] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline
        self.transport = transport or (
            StubStateTransport() if self._is_offline() else SubprocessStateTransport()
        )
        memory.init_db(self.db_path)

    def _is_offline(self) -> bool:
        if self.offline is not None:
            return self.offline
        return os.environ.get("EVA_STATE_OFFLINE") == "1"

    # -- write (append-only) -------------------------------------------------
    def record(self, **kwargs) -> dict[str, Any]:
        kwargs.setdefault("path", self.db_path)
        event_id = memory.append_event(**kwargs)
        return memory.get_event(event_id, self.db_path)

    def correct(self, original_event_id: str, *, summary: str,
                status: str = memory.STATUS_DROPPED, actor: str = "Eva",
                source_surface: str = "", payload: Optional[dict] = None,
                evidence_urls: Optional[list] = None) -> dict[str, Any]:
        try:
            event_id = memory.correct_event(
                original_event_id, summary=summary, status=status, actor=actor,
                source_surface=source_surface, payload=payload,
                evidence_urls=evidence_urls, path=self.db_path)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return memory.get_event(event_id, self.db_path)

    # -- coined terms (first-class entity) -----------------------------------
    def coin_term(self, term: str, *, domain: str = "", definition: str = "",
                  first_published_surface: str = "", first_published_url: str = "",
                  first_published_date: str = "", actor: str = "Vineet",
                  source_surface: str = "") -> dict[str, Any]:
        """Create a coined_term entity with its founding ``coined_term_created`` event."""
        entity_id = memory.slugify(term)
        payload = {
            "term": term, "domain": domain, "definition": definition,
            "first_published_surface": first_published_surface,
            "first_published_url": first_published_url,
            "first_published_date": first_published_date,
        }
        return self.record(
            event_type="coined_term_created", entity_type="coined_term",
            entity_id=entity_id, project="Personal Brand", track="coined-terms",
            actor=actor, source_surface=source_surface or first_published_surface,
            summary=f"Coined term '{term}' ({domain})",
            payload=payload, status=memory.STATUS_ACTIVE,
            evidence_urls=[first_published_url] if first_published_url else None,
        )

    def reference_term(self, term: str, *, surface: str = "",
                       engagement: Optional[dict] = None, url: str = "",
                       actor: str = "Eva", productization_flag: str = "") -> dict[str, Any]:
        """Record a subsequent reference / traction datapoint for a coined term."""
        entity_id = memory.slugify(term)
        payload = {"term": term, "surface": surface,
                   "engagement_metrics": engagement or {}}
        if productization_flag:
            payload["productization_flag"] = productization_flag
        return self.record(
            event_type="coined_term_referenced", entity_type="coined_term",
            entity_id=entity_id, project="Personal Brand", track="coined-terms",
            actor=actor, source_surface=surface,
            summary=f"'{term}' referenced on {surface}",
            payload=payload, status=memory.STATUS_ACTIVE,
            evidence_urls=[url] if url else None,
        )

    # -- read (derived views) ------------------------------------------------
    def today(self) -> dict[str, Any]:
        return {
            "priorities": memory.daily_priorities(self.db_path),
            "open_blockers": memory.open_blockers(self.db_path),
            "pending_approvals": memory.pending_approvals(self.db_path),
            "coined_term_signals": [
                c for c in memory.coined_terms(self.db_path)
                if (c.get("reference_count") or 0) >= 1
            ],
        }

    def projects(self) -> list[dict]:
        return memory.project_state(self.db_path)

    def project_map(self) -> dict[str, Any]:
        return project_map.build_tree(self.db_path)

    def render_map(self, *, write_json: bool = True, write_html: bool = False,
                   publish: bool = False) -> dict[str, Any]:
        """Regenerate project_map.json (and optionally index.html).

        Publishing the rebuilt HTML to a live surface is the irreversible action
        and is gated behind the transport chokepoint (Stub offline).
        """
        result = project_map.render(self.db_path, write_json=write_json,
                                    write_html=write_html)
        if publish and write_html and result.get("html_path"):
            with open(result["html_path"], "r", encoding="utf-8") as fh:
                html = fh.read()
            result["publish"] = self.transport.publish_map(html, result["html_path"])
        return result

    def pending_approvals(self) -> list[dict]:
        return memory.pending_approvals(self.db_path)

    def recent_decisions(self, limit: int = 20) -> list[dict]:
        return memory.recent_decisions(limit, self.db_path)

    def open_blockers(self) -> list[dict]:
        return memory.open_blockers(self.db_path)

    def agent_health(self) -> list[dict]:
        return memory.agent_health(self.db_path)

    def coined_terms(self) -> list[dict]:
        return memory.coined_terms(self.db_path)

    def events(self, **filters) -> list[dict]:
        filters.setdefault("path", self.db_path)
        return memory.list_events(**filters)


__all__ = [
    "StateService",
    "StateTransport",
    "StubStateTransport",
    "SubprocessStateTransport",
    "NotFoundError",
    "ApprovalError",
]
