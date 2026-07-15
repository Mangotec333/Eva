"""
EVA Diracatron — service layer (poll → rank → queue → dispatch → learn)
=======================================================================

Sits between the HTTP/CLI surfaces and the brain's read surfaces, dispatcher,
local queue store, and the Eva State Ledger. The sources, dispatcher, and
state client are injected (Protocols) so the whole service runs offline in
tests with stubs and fires nothing real.

Three operations mirror the three routes:

  * ``queue()``       — the current ranked, still-open triage queue.
  * ``run_pass()``    — one full triage pass: poll every source, rank, and
    upsert candidates into the queue idempotently (cron-safe).
  * ``dispatch(id)``  — dispatch one queued item to its downstream agent, log
    the decision back to eva-state, and record it in the dispatch history.
"""

from __future__ import annotations

from typing import Optional

import diracatron
import store
from state_client import StateLedgerClient, build_state_client


class DiracatronService:
    def __init__(self, *, db_path: str = store.DB_PATH,
                 sources: Optional[list] = None,
                 dispatcher: Optional[diracatron.Dispatcher] = None,
                 state: Optional[StateLedgerClient] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline
        self.sources = sources if sources is not None else diracatron.build_sources(offline)
        self.dispatcher = dispatcher or diracatron.build_dispatcher(offline)
        self.state: StateLedgerClient = state or build_state_client(offline=offline)
        store.init_db(self.db_path)

    # -- reads ---------------------------------------------------------------

    def queue(self) -> dict:
        items = store.list_queue(status=store.STATUS_OPEN, path=self.db_path)
        return {"count": len(items), "items": items}

    def history(self, limit: int = 50) -> list[dict]:
        return store.list_dispatches(limit=limit, path=self.db_path)

    # -- one triage pass -----------------------------------------------------

    def run_pass(self) -> dict:
        """Poll every source, score, and idempotently upsert the ranked queue."""
        raw: list[dict] = []
        for src in self.sources:
            try:
                raw.extend(src.candidates())
            except Exception:  # a bad source never breaks the pass
                continue

        seen: set[str] = set()
        persisted: list[dict] = []
        for cand in raw:
            sig = store.signature(cand["kind"], cand.get("entity_id", ""),
                                  cand.get("source", ""))
            if sig in seen:
                continue
            seen.add(sig)
            item = store.upsert_item(
                kind=cand["kind"],
                entity_id=cand.get("entity_id", ""),
                source=cand.get("source", ""),
                summary=cand.get("summary", ""),
                priority=diracatron.score(cand),
                target_agent=diracatron.route_for(cand),
                payload=cand.get("payload") or {},
                path=self.db_path,
            )
            persisted.append(item)

        ranked = store.list_queue(status=store.STATUS_OPEN, path=self.db_path)
        self.state.emit(
            event_type="triage_pass",
            summary=f"Diracatron triage pass: {len(persisted)} candidates, "
                    f"{len(ranked)} open",
            entity_id="triage",
            payload={"candidates": len(persisted), "open": len(ranked)},
        )
        return {"candidates": len(persisted), "open": len(ranked), "queue": ranked}

    # -- dispatch one item ---------------------------------------------------

    def dispatch(self, item_id: str) -> dict:
        item = store.get_item(item_id, path=self.db_path)
        if not item:
            return {"ok": False, "error": f"item {item_id} not found"}
        if item["status"] != store.STATUS_OPEN:
            return {"ok": False, "error": f"item {item_id} is {item['status']}",
                    "item": item}

        kind = item["kind"]
        _, port, route = diracatron.ROUTES.get(kind, (item["target_agent"], None, "/"))
        agent = item["target_agent"] or (
            diracatron.ROUTES.get(kind, ("unknown",))[0])

        result = self.dispatcher.dispatch(agent=agent, route=route, port=port,
                                          item=item)

        store.set_status(item_id, store.STATUS_DISPATCHED, path=self.db_path)
        record = store.record_dispatch(
            item_id=item_id, signature=item["signature"], kind=kind,
            target_agent=agent, result=result, path=self.db_path)

        summary = f"Diracatron dispatched {kind} → {agent} " \
                  f"({'ok' if result.get('ok') else 'failed'})"
        self.state.emit(
            event_type="triage_dispatch",
            summary=summary,
            entity_id=item["entity_id"] or item_id,
            payload={"kind": kind, "agent": agent, "route": route,
                     "priority": item["priority"], "result": result},
        )
        return {"ok": bool(result.get("ok")), "item": store.get_item(item_id, path=self.db_path),
                "agent": agent, "dispatch": record, "result": result}


__all__ = ["DiracatronService"]
