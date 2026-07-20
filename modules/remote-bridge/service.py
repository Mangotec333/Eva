"""
EVA Remote-Bridge — service layer (receive → ack → dispatch → learn).

Sits between the HTTP/CLI surfaces and the SQLite store, Diracatron dispatch
client, and the Eva State Ledger. The dispatch and state clients are injected
(Protocols) so the whole service runs offline in tests with stubs and fires
nothing real.

The lifecycle is deliberately two-phase so the founder gets an instant receipt:

  * ``create_and_ack(goal, context)`` — persist the instruction as ``received``,
    audit it, and return the ``instruction_id`` immediately (never blocks on the
    downstream dispatch).
  * ``run_dispatch(instruction_id)`` — the background task: mark ``dispatched``,
    forward the goal to Diracatron, then record ``complete`` / ``failed``. This
    NEVER raises — a downstream failure is captured on the row, not crashed.
"""

from __future__ import annotations

from typing import Optional

import database as db
from database import Store
from dispatch_client import DispatchClient, build_dispatch_client
from state_client import StateLedgerClient, build_state_client


class RemoteBridgeService:
    def __init__(self, *, db_path: str = db.DB_PATH,
                 dispatcher: Optional[DispatchClient] = None,
                 state: Optional[StateLedgerClient] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline
        self.store = Store(db_path)
        self.dispatcher: DispatchClient = dispatcher or build_dispatch_client(offline)
        self.state: StateLedgerClient = state or build_state_client(offline=offline)

    def _emit(self, event_type: str, summary: str, entity_id: str,
              payload: Optional[dict] = None) -> None:
        """Audit to eva-state. Best-effort: an audit failure must never break
        the caller (the state client already returns honest failure, but guard
        anyway so a surprise never propagates)."""
        try:
            self.state.emit(event_type=event_type, summary=summary,
                            entity_id=entity_id, payload=payload or {})
        except Exception:
            pass

    # -- phase 1: receive + immediate ack -----------------------------------

    def create_and_ack(self, goal: str, context: Optional[dict] = None) -> dict:
        record = self.store.create_instruction(goal, context)
        iid = record["id"]
        self.store.append_ledger(
            event_type="remote_instruction_received", entity_id=iid,
            actor="founder", details={"goal": goal})
        self._emit(
            "remote_instruction_received",
            summary=f"Remote instruction received: {goal[:120]}",
            entity_id=iid, payload={"goal": goal, "context": context or {}})
        return record

    # -- phase 2: background dispatch (never raises) -------------------------

    def run_dispatch(self, instruction_id: str) -> dict:
        record = self.store.get_instruction(instruction_id)
        if record is None:
            return {"ok": False, "error": f"instruction {instruction_id} not found"}

        goal = record["goal"]
        context = record.get("context") or {}

        self.store.update_instruction(
            instruction_id, {"status": db.STATUS_DISPATCHED})
        self.store.append_ledger(
            event_type="remote_instruction_dispatched", entity_id=instruction_id,
            actor="eva", details={"goal": goal})
        self._emit(
            "remote_instruction_dispatched",
            summary=f"Remote instruction dispatched to Diracatron: {goal[:120]}",
            entity_id=instruction_id, payload={"goal": goal})

        try:
            result = self.dispatcher.dispatch(goal=goal, context=context)
        except Exception as exc:  # downstream blew up — capture, do not crash
            error = f"{type(exc).__name__}: {exc}"
            self.store.update_instruction(
                instruction_id, {"status": db.STATUS_FAILED, "error": error})
            self.store.append_ledger(
                event_type="remote_instruction_failed", entity_id=instruction_id,
                actor="eva", details={"error": error})
            self._emit(
                "remote_instruction_failed",
                summary=f"Remote instruction dispatch failed: {error}",
                entity_id=instruction_id, payload={"error": error})
            return {"ok": False, "error": error}

        ok = bool(result.get("ok"))
        if ok:
            self.store.update_instruction(
                instruction_id,
                {"status": db.STATUS_COMPLETE, "dispatch_result": result})
            self.store.append_ledger(
                event_type="remote_instruction_complete", entity_id=instruction_id,
                actor="eva", details={"result": result})
            self._emit(
                "remote_instruction_complete",
                summary="Remote instruction complete",
                entity_id=instruction_id, payload={"result": result})
        else:
            error = result.get("error", "dispatch reported not ok")
            self.store.update_instruction(
                instruction_id,
                {"status": db.STATUS_FAILED, "error": error,
                 "dispatch_result": result})
            self.store.append_ledger(
                event_type="remote_instruction_failed", entity_id=instruction_id,
                actor="eva", details={"error": error, "result": result})
            self._emit(
                "remote_instruction_failed",
                summary=f"Remote instruction failed: {error}",
                entity_id=instruction_id, payload={"error": error, "result": result})
        return {"ok": ok, "result": result}

    # -- reads --------------------------------------------------------------

    def get(self, instruction_id: str) -> Optional[dict]:
        return self.store.get_instruction(instruction_id)

    def list(self, limit: int = 20) -> list[dict]:
        return self.store.list_instructions(limit)

    def ledger(self, instruction_id: str) -> list[dict]:
        return self.store.query_ledger(instruction_id)


__all__ = ["RemoteBridgeService"]
