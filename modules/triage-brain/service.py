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
from dispatch_brain import Planner, build_planner
from registry import AgentRegistry, Invoker, build_invoker, build_registry
from state_client import StateLedgerClient, build_state_client


class DiracatronService:
    def __init__(self, *, db_path: str = store.DB_PATH,
                 sources: Optional[list] = None,
                 dispatcher: Optional[diracatron.Dispatcher] = None,
                 state: Optional[StateLedgerClient] = None,
                 registry: Optional[AgentRegistry] = None,
                 planner: Optional[Planner] = None,
                 invoker: Optional[Invoker] = None,
                 offline: Optional[bool] = None) -> None:
        self.db_path = db_path
        self.offline = offline
        self.sources = sources if sources is not None else diracatron.build_sources(offline)
        self.dispatcher = dispatcher or diracatron.build_dispatcher(offline)
        self.state: StateLedgerClient = state or build_state_client(offline=offline)
        self.registry: AgentRegistry = registry or build_registry()
        self.planner: Planner = planner or build_planner(self.registry, offline)
        self.invoker: Invoker = invoker or build_invoker(offline)
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
            # Stamp the Elon-style first-principles "why this, why now" onto the
            # item so the ranked queue carries its own rationale (ruthless
            # stack-rank, not a bare priority integer).
            payload = dict(cand.get("payload") or {})
            payload["rationale"] = diracatron.first_principles_rationale(cand)
            item = store.upsert_item(
                kind=cand["kind"],
                entity_id=cand.get("entity_id", ""),
                source=cand.get("source", ""),
                summary=cand.get("summary", ""),
                priority=diracatron.score(cand),
                target_agent=diracatron.route_for(cand),
                payload=payload,
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

    # -- dispatch a GOAL (Eva's dispatch brain) ------------------------------

    def dispatch_goal(self, goal: str, *, context: Optional[dict] = None) -> dict:
        """Turn a goal/intent into action: LLM decides which lobes to invoke
        (first-principles), invoke them via the registry, collect results, and
        log the decision + every outcome back to eva-state so Eva learns.

        This is Eva's dispatch brain — the ``/triage/dispatch`` verb for a
        free-form goal (as opposed to dispatching one already-queued item).
        """
        goal = (goal or "").strip()
        if not goal:
            return {"ok": False, "error": "goal is required"}

        plan = self.planner.plan(goal, context=context)
        steps = plan.get("steps", [])

        # Log the decision itself first — the plan is an artefact worth learning
        # from even if some steps later fail.
        self.state.emit(
            event_type="triage_decision",
            summary=f"Diracatron planned {len(steps)} step(s) for goal: {goal[:120]}",
            entity_id="dispatch",
            payload={"goal": goal, "planner": plan.get("planner"),
                     "rationale": plan.get("rationale", ""), "steps": steps},
        )

        results: list[dict] = []
        for step in steps:
            agent = self.registry.get(step["agent"])
            if agent is None:  # validated already, but stay defensive
                results.append({"ok": False, "agent": step["agent"],
                                "error": "agent not in registry"})
                continue
            outcome = self.invoker.invoke(
                agent, action=step.get("action"),
                payload=step.get("payload") or {})
            record = store.record_dispatch(
                item_id=f"goal:{agent.slug}", signature="", kind="goal_dispatch",
                target_agent=agent.slug, result=outcome, path=self.db_path)
            # Log each outcome back to the ledger (the self-learning moat).
            self.state.emit(
                event_type="triage_dispatch",
                summary=f"Diracatron invoked {agent.slug}.{step.get('action')} "
                        f"({'ok' if outcome.get('ok') else 'failed'})",
                entity_id=agent.slug,
                payload={"goal": goal, "agent": agent.slug,
                         "action": step.get("action"),
                         "rationale": step.get("rationale", ""),
                         "result": outcome},
            )
            results.append({**outcome, "rationale": step.get("rationale", ""),
                            "dispatch_id": record.get("id")})

        ok = bool(results) and all(r.get("ok") for r in results)
        return {"ok": ok, "goal": goal, "planner": plan.get("planner"),
                "rationale": plan.get("rationale", ""), "steps": steps,
                "results": results}

    # -- nightly digest ------------------------------------------------------

    def digest(self, *, run_first: bool = True, top: int = 10,
               alert: bool = False) -> dict:
        """A prioritized stack-rank of open doors + market potential.

        Runs a fresh triage pass (so the queue reflects reality), then returns
        the ruthless top-N with first-principles rationale. Best-effort Slack
        post when ``alert`` is set. This is the payload the nightly scheduled
        job posts.
        """
        if run_first:
            self.run_pass()
        ranked = store.list_queue(status=store.STATUS_OPEN, path=self.db_path)
        top_items = ranked[:top]

        lines = ["*Diracatron nightly stack-rank — open doors by leverage*"]
        for i, it in enumerate(top_items, 1):
            why = (it.get("payload") or {}).get("rationale", "")
            lines.append(
                f"{i}. [{it['priority']}] {it['summary']} "
                f"→ {it['target_agent']}\n   {why}")
        if not top_items:
            lines.append("_No open doors — queue is clear._")
        text = "\n".join(lines)

        self.state.emit(
            event_type="triage_digest",
            summary=f"Diracatron nightly digest: {len(ranked)} open, "
                    f"top {len(top_items)} ranked",
            entity_id="digest",
            payload={"open": len(ranked), "top": top_items},
        )

        alert_result = None
        if alert:
            alert_result = diracatron.slack_alert(text)
        return {"open": len(ranked), "count": len(top_items),
                "digest": text, "items": top_items, "alert": alert_result}


__all__ = ["DiracatronService"]
