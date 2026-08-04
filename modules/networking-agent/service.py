"""
EVA Networking-Agent — service layer (Layer A + Layer B share this brain).

One store, one approval loop, two entity types:
  * contacts (Layer A — Relationship Capital)
  * groups   (Layer B — Community Scout)

Enforced rules (code, not convention):
  * Any content that reaches a person — post, comment, connection_request, dm —
    MUST go through draft() → approve() → send()/post(). ``auto_action`` refuses
    to execute anything outside the ``autonomy.AUTO_ALLOWED`` whitelist.
  * The two whitelisted actions (join_public_group, monitor_keyword_mention) run
    immediately but are still logged to the append-only outcomes ledger.

Offline-safe, mirroring ``modules/brand-builder/service.py``: with
``EVA_NETWORKING_OFFLINE=1`` the eva-state client is a stub (no network). Every
public method returns a JSON-able dict; domain errors are caught and returned as
``{"ok": False, "error": ..., "code": ...}`` so nothing leaks to API callers.
"""

from __future__ import annotations

import os
from typing import Optional

import directives as directives_mod
import playbook
import scoring
from autonomy import AUTO_ALLOWED, AutonomyError, assert_auto_allowed
from discovery import get_provider
from state_client import StateLedgerClient, build_state_client
from store import OUTCOME_SIGNALS, Store, _now

QUALIFY_THRESHOLD = 0.5
KAIZEN_LEARNING_RATE = 0.5
CONTENT_ACTIONS = ("post", "comment", "connection_request", "dm")


class NetworkingAgentService:
    def __init__(self, *, store: Optional[Store] = None,
                 state: Optional[StateLedgerClient] = None,
                 offline: Optional[bool] = None) -> None:
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_NETWORKING_OFFLINE") == "1")
        self.store = store or Store()
        self.state = state or build_state_client(offline=self.offline)

    # -- meta ---------------------------------------------------------------

    def status(self) -> dict:
        return {
            "status": "ok",
            "module": "eva-networking-agent",
            "offline": self.offline,
            "ventures": directives_mod.VENTURES,
            "auto_allowed": sorted(AUTO_ALLOWED),
            "groups": len(self.store.list_groups()),
            "contacts": len(self.store.list_contacts()),
            "drafts_pending": len(self.store.list_drafts(status="draft")),
            "outcome_signals": list(OUTCOME_SIGNALS),
        }

    def get_directive(self, venture: str) -> dict:
        return directives_mod.get_directive(venture)

    # -- seeding ------------------------------------------------------------

    def seed(self) -> dict:
        """Initialise the store + snapshot directives for all ventures."""
        self.store.init_db()
        directive_map = {v: directives_mod.get_directive(v)
                         for v in directives_mod.VENTURES}
        self.state.emit(
            event_type="networking_seeded",
            summary=f"Seeded networking-agent for {len(directive_map)} ventures",
            entity_id="networking-agent",
            payload={"ventures": list(directive_map)})
        return {"ok": True, "ventures": list(directive_map),
                "directives": directive_map}

    # -- planning -----------------------------------------------------------

    def plan(self, venture: str) -> dict:
        """Directive-aware plan: current groups/contacts by stage + next actions."""
        directive = directives_mod.get_directive(venture)
        if directive.get("error"):
            return {"ok": False, "error": directive["error"]}

        groups = self.store.list_groups(venture=venture)
        contacts = self.store.list_contacts(venture=venture)

        group_actions = [{
            "group_id": g["id"], "name": g["name"], "stage": g["status"],
            "next_best_action": playbook.next_best_action("group", g["status"]),
        } for g in groups]
        contact_actions = [{
            "contact_id": c["id"], "name": c["name"], "stage": c["stage"],
            "next_best_action": playbook.next_best_action("contact", c["stage"]),
        } for c in contacts]

        return {
            "ok": True,
            "venture": venture,
            "directive": directive,
            "keywords": directive.get("keywords", []),
            "tactics": playbook.TACTICS,
            "groups": group_actions,
            "contacts": contact_actions,
        }

    # -- discovery ----------------------------------------------------------

    def discover(self, venture: str, seed_data=None,
                 provider: str = "manual_seed") -> dict:
        directive = directives_mod.get_directive(venture)
        if directive.get("error"):
            return {"ok": False, "error": directive["error"]}
        try:
            prov = get_provider(provider)
            candidates = prov.discover(venture, seed_data)
        except NotImplementedError as exc:
            return {"ok": False, "error": str(exc), "code": "provider_not_wired"}
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "code": "unknown_provider"}

        created, skipped = [], []
        for cand in candidates:
            if not cand.get("name"):
                continue
            existing = self.store.get_group_by_url(cand.get("url", ""))
            if existing and cand.get("url"):
                skipped.append(existing["id"])
                continue
            cand = {**cand, "venture_tag": venture,
                    "discovered_via": prov.name, "status": "candidate"}
            scored = scoring.score_group(cand)
            cand["score"] = scored["score"]
            group = self.store.insert_group(cand)
            created.append(group)
            self.store.append_outcome(
                "group", group["id"], "discovered", signal="",
                action="discover", actor=prov.name,
                details={"venture": venture, "confidence": scored["confidence"]})

        self.state.emit(
            event_type="groups_discovered",
            summary=f"Discovered {len(created)} groups for {venture} via {prov.name}",
            entity_id=venture,
            payload={"created": len(created), "skipped": len(skipped),
                     "provider": prov.name})
        return {"ok": True, "venture": venture, "provider": prov.name,
                "created": created, "created_count": len(created),
                "skipped_count": len(skipped)}

    # -- scoring ------------------------------------------------------------

    def score(self, group_id: str) -> dict:
        group = self.store.get_group(group_id)
        if not group:
            return {"ok": False, "error": f"group {group_id!r} not found",
                    "code": "not_found"}
        scored = scoring.score_group(group)
        fields = {"score": scored["score"]}
        if group["status"] == "candidate" and scored["score"] >= QUALIFY_THRESHOLD:
            fields["status"] = "qualified"
        updated = self.store.update_group(group_id, fields)
        self.state.emit(
            event_type="group_scored",
            summary=f"Scored group {group['name']}: {scored['score']} ({scored['confidence']})",
            entity_id=group_id, payload=scored)
        return {"ok": True, "group": updated, **scored}

    # -- draft → approve → send/post ---------------------------------------

    def draft(self, entity_type: str, entity_id: str, content: str,
              action: str = "post") -> dict:
        if entity_type not in ("group", "contact"):
            return {"ok": False, "error": f"unknown entity_type: {entity_type!r}",
                    "code": "bad_entity_type"}
        entity = (self.store.get_group(entity_id) if entity_type == "group"
                  else self.store.get_contact(entity_id))
        if not entity:
            return {"ok": False, "error": f"{entity_type} {entity_id!r} not found",
                    "code": "not_found"}
        draft = self.store.insert_draft({
            "entity_type": entity_type, "entity_id": entity_id,
            "action": action, "content": content})
        self.store.append_outcome(
            entity_type, entity_id, "drafted", signal="", action=action,
            actor="system", details={"draft_id": draft["id"]})
        return {"ok": True, "draft": draft}

    def approve(self, draft_id: str, approved_by: str = "founder") -> dict:
        draft = self.store.get_draft(draft_id)
        if not draft:
            return {"ok": False, "error": f"draft {draft_id!r} not found",
                    "code": "not_found"}
        if draft["status"] != "draft":
            return {"ok": False, "error": f"cannot approve draft in status {draft['status']!r}",
                    "code": "invalid_state"}
        updated = self.store.update_draft(draft_id, {
            "status": "approved", "approved_by": approved_by,
            "approved_at": _now()})
        self.store.append_outcome(
            draft["entity_type"], draft["entity_id"], "approved", signal="",
            action=draft["action"], actor=approved_by,
            details={"draft_id": draft_id})
        return {"ok": True, "draft": updated}

    def send(self, draft_id: str, actor: str = "system") -> dict:
        """Send/post an approved draft. Blocks unless status == approved."""
        draft = self.store.get_draft(draft_id)
        if not draft:
            return {"ok": False, "error": f"draft {draft_id!r} not found",
                    "code": "not_found"}
        if draft["status"] != "approved":
            self.store.append_outcome(
                draft["entity_type"], draft["entity_id"], "send_blocked",
                signal="", action=draft["action"], actor=actor,
                details={"draft_id": draft_id, "reason": "not_approved",
                         "status": draft["status"]})
            return {"ok": False, "error": "draft must be approved before sending",
                    "code": "not_approved"}
        updated = self.store.update_draft(draft_id, {
            "status": "sent", "sent_at": _now(), "error": ""})
        self.store.append_outcome(
            draft["entity_type"], draft["entity_id"], "sent", signal="",
            action=draft["action"], actor=actor,
            details={"draft_id": draft_id})
        self.state.emit(
            event_type="draft_sent",
            summary=f"Sent {draft['action']} for {draft['entity_type']} {draft['entity_id']}",
            entity_id=draft["entity_id"], payload={"draft_id": draft_id,
                                                   "action": draft["action"]})
        return {"ok": True, "draft": updated}

    # ``post`` is an alias for ``send`` (both close the approval loop).
    def post(self, draft_id: str, actor: str = "system") -> dict:
        return self.send(draft_id, actor=actor)

    # -- autonomous actions (whitelist-gated) ------------------------------

    def auto_action(self, action: str, entity_id: str,
                    entity_type: str = "group", actor: str = "auto") -> dict:
        """Execute a whitelisted action immediately. Anything not in
        AUTO_ALLOWED is rejected — this is the enforced guardrail."""
        try:
            assert_auto_allowed(action)
        except AutonomyError as exc:
            self.store.append_outcome(
                entity_type, entity_id, "auto_action_rejected", signal="",
                action=action, actor=actor, details={"code": exc.code})
            return {"ok": False, "error": exc.message, "code": exc.code}

        signal = "joined" if action == "join_public_group" else "keyword_mention_found"
        outcome = self.store.append_outcome(
            entity_type, entity_id, "auto_action", signal=signal,
            action=action, actor=actor, details={"whitelisted": True})

        # join_public_group advances a candidate group to qualified.
        if action == "join_public_group" and entity_type == "group":
            g = self.store.get_group(entity_id)
            if g and g["status"] == "candidate":
                self.store.update_group(entity_id, {"status": "qualified"})

        self.state.emit(
            event_type="auto_action",
            summary=f"Auto action {action} on {entity_type} {entity_id}",
            entity_id=entity_id, payload={"action": action, "signal": signal})
        return {"ok": True, "action": action, "signal": signal,
                "outcome": outcome}

    # -- outcome logging + KAIZEN ------------------------------------------

    def log_outcome(self, entity_type: str, entity_id: str, outcome: str,
                    signal: str = "", actor: str = "system") -> dict:
        if signal and signal not in OUTCOME_SIGNALS:
            return {"ok": False,
                    "error": f"unknown signal {signal!r}; known {list(OUTCOME_SIGNALS)}",
                    "code": "unknown_signal"}
        rec = self.store.append_outcome(
            entity_type, entity_id, outcome, signal=signal, actor=actor)
        return {"ok": True, "outcome": rec}

    def kaizen_reweight(self) -> dict:
        """Weekly loop: re-weight the 10 outcome signals from observed
        prevalence. Deterministic — always derived from the base taxonomy plus
        the current outcome distribution, so repeated runs converge, not drift.

            new = base + LEARNING_RATE * base * (share - mean_share)

        A signal seen more often than the uniform share is reinforced in its own
        direction (positive signals up, negative signals more negative)."""
        outcomes = [o for o in self.store.list_outcomes() if o.get("signal")]
        counts: dict[str, int] = {s: 0 for s in OUTCOME_SIGNALS}
        for o in outcomes:
            if o["signal"] in counts:
                counts[o["signal"]] += 1
        total = sum(counts.values())

        n = len(OUTCOME_SIGNALS)
        mean_share = 1.0 / n if n else 0.0
        new_weights: dict[str, float] = {}
        for signal, base in OUTCOME_SIGNALS.items():
            if total == 0:
                new = base
            else:
                share = counts[signal] / total
                new = base + KAIZEN_LEARNING_RATE * base * (share - mean_share)
                new = max(-1.0, min(1.0, new))
            new = round(new, 4)
            new_weights[signal] = new
            self.store.set_weight(signal, new)

        self.state.emit(
            event_type="kaizen_reweight",
            summary=f"KAIZEN reweight over {total} signalled outcomes",
            entity_id="networking-agent",
            payload={"total_signals": total, "weights": new_weights})
        return {"ok": True, "total_signals": total, "counts": counts,
                "weights": new_weights}

    # -- reads --------------------------------------------------------------

    def list_groups(self, venture=None, platform=None, status=None) -> list[dict]:
        return self.store.list_groups(venture=venture, platform=platform, status=status)

    def get_group(self, group_id: str) -> Optional[dict]:
        return self.store.get_group(group_id)

    def list_contacts(self, venture=None, stage=None, status=None) -> list[dict]:
        return self.store.list_contacts(venture=venture, stage=stage, status=status)

    def add_contact(self, data: dict) -> dict:
        contact = self.store.insert_contact(data)
        self.store.append_outcome(
            "contact", contact["id"], "created", signal="", actor="system")
        return {"ok": True, "contact": contact}

    def list_drafts(self, status=None) -> list[dict]:
        return self.store.list_drafts(status=status)

    def list_outcomes(self, entity_type=None, entity_id=None, signal=None) -> list[dict]:
        return self.store.list_outcomes(entity_type=entity_type,
                                        entity_id=entity_id, signal=signal)

    def get_weights(self) -> dict[str, float]:
        return self.store.get_weights()


__all__ = ["NetworkingAgentService", "QUALIFY_THRESHOLD",
           "KAIZEN_LEARNING_RATE", "CONTENT_ACTIONS"]
