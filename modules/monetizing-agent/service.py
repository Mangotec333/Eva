"""
EVA Monetizing Agent — service layer (approval gate + execution chokepoint)
===========================================================================

Sits between the HTTP/CLI surfaces and the scan/memory core. Owns two governed
concerns from the module standard:

- **Approval gate.** Every irreversible action (sending a drafted SMS/email,
  moving a pipeline, creating a proposal doc) is gated. A freshly scanned brief
  is ``pending-approval``; ``approve(brief_id)`` flips its plays to
  ``approved``. Nothing executes until approved.
- **Execution behind a Protocol with a subprocess chokepoint.** Executing an
  approved play routes its artifact through an ``ExecutionTransport``.
  ``StubExecutionTransport`` is offline (tests) and never fakes success beyond
  recording intent. ``SubprocessExecutionTransport`` is the single place real
  side effects would happen — it shells out to a chokepoint script; when the
  chokepoint is absent it returns ``ok=False`` (honest, not a fake success).
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Optional, Protocol, runtime_checkable

import memory
from scan import run_scan


class ApprovalError(RuntimeError):
    """Raised when an irreversible action is attempted without approval."""


class NotFoundError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Execution transport (irreversible-action chokepoint)
# ---------------------------------------------------------------------------

@runtime_checkable
class ExecutionTransport(Protocol):
    def execute(self, play: dict) -> dict[str, Any]:
        """Perform the play's packaged artifact. Returns ``{ok, ...}``."""


class StubExecutionTransport:
    """Offline transport used in tests. Records intent; performs no side effect."""

    def __init__(self) -> None:
        self.executed: list[dict] = []

    def execute(self, play: dict) -> dict[str, Any]:
        self.executed.append(play)
        return {"ok": True, "stub": True, "play_id": play.get("play_id"),
                "route": (play.get("action_artifact") or {}).get("route", "")}


class SubprocessExecutionTransport:
    """Real transport: shells the artifact to a single subprocess chokepoint.

    The chokepoint (``execute_play.py``) is the only place live side effects
    (GHL sends, pipeline moves, Drive writes) would run. Absent/failed → honest
    ``ok=False`` (never a faked success).
    """

    def __init__(self, chokepoint: Optional[str] = None) -> None:
        self.chokepoint = chokepoint or os.path.join(
            os.path.dirname(__file__), "execute_play.py")

    def execute(self, play: dict) -> dict[str, Any]:
        if not os.path.exists(self.chokepoint):
            return {"ok": False, "stub": False,
                    "error": f"chokepoint not wired: {self.chokepoint}"}
        try:
            import json
            result = subprocess.run(
                ["python3", self.chokepoint, json.dumps(play, default=str)],
                capture_output=True, text=True, timeout=60,
            )
            return {"ok": result.returncode == 0, "stub": False,
                    "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "stub": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MonetizingService:
    def __init__(self, *, db_path: str = memory.DB_PATH,
                 execution_transport: Optional[ExecutionTransport] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline
        self.execution_transport = execution_transport or (
            StubExecutionTransport() if self._is_offline() else SubprocessExecutionTransport()
        )
        memory.init_db(self.db_path)

    def _is_offline(self) -> bool:
        if self.offline is not None:
            return self.offline
        return os.environ.get("EVA_MONETIZE_OFFLINE") == "1"

    # -- scan ----------------------------------------------------------------
    def scan(self, **kwargs) -> dict[str, Any]:
        kwargs.setdefault("db_path", self.db_path)
        kwargs.setdefault("offline", self.offline)
        return run_scan(**kwargs)

    # -- read ----------------------------------------------------------------
    def latest_brief(self) -> Optional[dict]:
        brief = memory.latest_brief(self.db_path)
        if not brief:
            return None
        brief["plays"] = memory.list_plays(brief_id=brief["id"], path=self.db_path)
        return brief

    def get_brief(self, brief_id: str) -> dict:
        brief = memory.get_brief(brief_id, self.db_path)
        if not brief:
            raise NotFoundError(f"brief {brief_id!r} not found")
        brief["plays"] = memory.list_plays(brief_id=brief_id, path=self.db_path)
        return brief

    # -- approval gate -------------------------------------------------------
    def approve(self, brief_id: str) -> dict[str, Any]:
        """The approval gate: flip a brief's pending plays to approved."""
        brief = memory.get_brief(brief_id, self.db_path)
        if not brief:
            raise NotFoundError(f"brief {brief_id!r} not found")
        n = memory.approve_plays(brief_id, self.db_path)
        memory.set_brief_status(brief_id, memory.STATUS_APPROVED, self.db_path)
        return {"brief_id": brief_id, "approved_plays": n,
                "status": memory.STATUS_APPROVED}

    # -- execution (gated) ---------------------------------------------------
    def execute(self, brief_id: str) -> dict[str, Any]:
        """Execute the approved plays of a brief through the transport.

        Refuses any play that is not APPROVED — the irreversible action gate.
        """
        brief = memory.get_brief(brief_id, self.db_path)
        if not brief:
            raise NotFoundError(f"brief {brief_id!r} not found")
        plays = memory.list_plays(brief_id=brief_id, path=self.db_path)
        results = []
        for play in plays:
            if play["status"] != memory.STATUS_APPROVED:
                results.append({"play_id": play["play_id"], "skipped": True,
                                "reason": f"not approved (status={play['status']})"})
                continue
            import json
            play["action_artifact"] = _loads(play.get("action_artifact"))
            res = self.execution_transport.execute(play)
            outcome = "executed" if res.get("ok") else f"failed: {res.get('error','')}"
            memory.mark_executed(play["play_id"], outcome=outcome, path=self.db_path)
            results.append({"play_id": play["play_id"], **res})
        executed = [r for r in results if r.get("ok")]
        if executed:
            memory.set_brief_status(brief_id, memory.STATUS_EXECUTED, self.db_path)
        return {"brief_id": brief_id, "results": results,
                "executed": len(executed), "total": len(plays)}

    # -- learn (follow-up feedback capture) ----------------------------------
    def record_outcome(self, play_id: str, play_type: str, outcome: str,
                       lesson: str = "") -> str:
        return memory.record_learning(play_id, play_type, outcome, lesson,
                                      path=self.db_path)


def _loads(v: Any) -> Any:
    import json
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return {}
    return v or {}


__all__ = [
    "MonetizingService",
    "ExecutionTransport",
    "StubExecutionTransport",
    "SubprocessExecutionTransport",
    "ApprovalError",
    "NotFoundError",
]
