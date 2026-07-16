"""
EVA IP-Scout — service layer (the prior-art triage brain).

IP-Scout is an **L1-autonomy** lobe: it triages invention-idea seeds against
prior art and reports what's worth a **patent attorney's review**. It NEVER
files, submits, or asserts patentability.

Two sensors feed it:
  * user-seeded ideas in ``~/.eva/ip_ideas.json`` (id/title/description/category/
    seeded_at/status), and
  * Eva-activity mining — repeatable process patterns mined from the eva-state
    ledger (``mining.py``) proposed as machine-sourced disclosure candidates.

A **scan** turns each pending idea into an **invention disclosure**:
  {idea_id, title, abstract, claims_draft, sensor_source, created_at,
   novelty_score, confidence_band, prior_art_hits[], status,
   attorney_review_needed, recommendation}
via a pluggable prior-art provider (PatentsView; mocked offline) + deterministic
novelty scoring, then writes a daily markdown report and logs everything to
eva-state. Resilient: every provider call is caught — a scan never crashes.

Offline-safe: with ``EVA_IP_OFFLINE=1`` the provider is mocked, eva-state is a
stub, and no network is touched.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

import mining
import novelty
import store
from provider import PriorArtProvider, build_provider, tokenize
from state_client import StateLedgerClient, build_state_client

logger = logging.getLogger("ip_scout.service")

MAX_CLAIMS = 5


class IPScoutService:
    def __init__(self, *, state: StateLedgerClient | None = None,
                 provider: PriorArtProvider | None = None,
                 offline: bool | None = None) -> None:
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_IP_OFFLINE") == "1")
        self.state = state or build_state_client(offline=self.offline)
        self.provider = provider or build_provider(offline=self.offline)

    # -- sensors -------------------------------------------------------------

    def seed_idea(self, *, title: str, description: str = "",
                  category: str = "uncategorized", idea_id: str | None = None,
                  sensor_source: str = "user-seed") -> dict:
        """Add (or update) a user idea seed and persist it to ip_ideas.json."""
        idea = store.save_idea({
            "id": idea_id, "title": title, "description": description,
            "category": category, "status": store.STATUS_PENDING,
            "sensor_source": sensor_source,
        })
        self.state.emit(
            event_type="ip_idea_seeded",
            summary=f"IP idea seeded: {title[:80]}",
            entity_id=idea["id"],
            payload={"idea_id": idea["id"], "category": idea["category"],
                     "sensor_source": sensor_source})
        return idea

    def mine_ideas(self, *, min_occurrences: int | None = None,
                   persist: bool = True) -> list[dict]:
        """Mine eva-state activity for candidate ideas; optionally persist them."""
        events = []
        try:
            events = self.state.read_events(limit=1000)
        except Exception as exc:  # noqa: BLE001 — mining never crashes a run
            logger.warning("activity mining read failed: %s", exc)
        known = {i["id"] for i in store.list_ideas()}
        kwargs = {}
        if min_occurrences is not None:
            kwargs["min_occurrences"] = min_occurrences
        candidates = mining.mine_activity(events, known_idea_ids=known, **kwargs)
        if persist:
            for c in candidates:
                store.save_idea({
                    "id": c["id"], "title": c["title"],
                    "description": c["description"], "category": c["category"],
                    "status": store.STATUS_PENDING,
                    "sensor_source": c["sensor_source"],
                })
        return candidates

    # -- disclosure building -------------------------------------------------

    def _draft_claims(self, idea: dict) -> list[str]:
        """Deterministically draft claim language from the idea. This is a
        drafting AID for an attorney — never a legal claim."""
        title = idea.get("title", "").strip()
        desc = idea.get("description", "").strip()
        claims = []
        if title:
            claims.append(
                f"A system or method for {title[0].lower() + title[1:]}, "
                f"comprising the steps described herein.")
        # Dependent claims from description sentences.
        for sentence in [s.strip() for s in desc.replace("\n", " ").split(".") if s.strip()]:
            claims.append(f"The system or method wherein {sentence[0].lower() + sentence[1:]}.")
            if len(claims) >= MAX_CLAIMS:
                break
        return claims or [f"A system or method relating to {idea.get('category', 'the disclosed subject')}."]

    def triage_idea(self, idea: dict, *, run_id: str = "") -> dict:
        """Triage one idea → an invention disclosure. NEVER raises."""
        title = idea.get("title", "")
        desc = idea.get("description", "")
        idea_text = f"{title} {desc}".strip()
        claims = self._draft_claims(idea)

        res = {"ok": True, "hits": [], "source": self.provider.name}
        try:
            res = self.provider.search(idea_text or title or idea.get("id", ""))
        except Exception as exc:  # noqa: BLE001 — provider must never crash triage
            logger.warning("provider.search failed for %s: %s", idea.get("id"), exc)
            res = {"ok": False, "hits": [], "source": self.provider.name,
                   "error": f"{type(exc).__name__}: {exc}"}

        hits = res.get("hits", []) or []
        scored = novelty.score(idea_text, hits, claims, provider_ok=res.get("ok", False))

        abstract = desc or (
            f"An invention disclosure for '{title}' in the {idea.get('category', 'general')} area.")

        disclosure = {
            "idea_id": idea.get("id", ""),
            "title": title,
            "abstract": abstract,
            "claims_draft": claims,
            "sensor_source": idea.get("sensor_source", "user-seed"),
            "created_at": store.now_iso(),
            "novelty_score": scored["novelty_score"],
            "confidence_band": scored["confidence_band"],
            "prior_art_hits": hits,
            "status": store.STATUS_TRIAGED,
            "attorney_review_needed": scored["attorney_review_needed"],
            "recommendation": scored["recommendation"],
            "run_id": run_id,
            "provider_ok": res.get("ok", False),
            "provider_error": res.get("error", ""),
        }
        return disclosure

    # -- scan (a full triage run over pending ideas) -------------------------

    def scan(self, *, report_date: str | None = None,
             mine: bool = True) -> dict:
        """Run a triage pass over all pending ideas → disclosures + report.

        This is the daily incremental loop's unit of work. NEVER raises.
        """
        run = store.save_run({
            "started_at": store.now_iso(),
            "offline": self.offline, "provider": self.provider.name,
        })
        run_id = run["run_id"]
        report_date = report_date or date.today().isoformat()

        if mine:
            try:
                self.mine_ideas()
            except Exception as exc:  # noqa: BLE001
                logger.warning("mine_ideas failed: %s", exc)

        pending = store.list_ideas(status=store.STATUS_PENDING)
        disclosures = []
        for idea in pending:
            disc = self.triage_idea(idea, run_id=run_id)
            store.save_disclosure(disc)
            store.update_idea(idea["id"], {"status": store.STATUS_TRIAGED})
            self.state.emit(
                event_type="ip_disclosure_created",
                summary=(f"[{disc['recommendation']}] {disc['title'][:60]} — "
                         f"novelty {disc['novelty_score']:.2f} "
                         f"({disc['confidence_band']} conf)"),
                entity_id=disc["disclosure_id"],
                payload={
                    "idea_id": disc["idea_id"],
                    "disclosure_id": disc["disclosure_id"],
                    "novelty_score": disc["novelty_score"],
                    "confidence_band": disc["confidence_band"],
                    "recommendation": disc["recommendation"],
                    "attorney_review_needed": disc["attorney_review_needed"],
                    "prior_art_count": len(disc["prior_art_hits"]),
                    "sensor_source": disc["sensor_source"],
                })
            disclosures.append(disc)

        report_md = self._render_and_store_report(report_date, disclosures)
        report_path = store.save_report(report_date, report_md)

        summary = self._summarize(disclosures)
        store.save_run({
            "run_id": run_id, "started_at": run["started_at"],
            "finished_at": store.now_iso(), "report_date": report_date,
            "ideas_scanned": len(pending), "disclosures_created": len(disclosures),
            "offline": self.offline, "provider": self.provider.name,
            "report_path": report_path, "summary": summary,
        })
        self.state.emit(
            event_type="ip_scan_run",
            summary=(f"IP-Scout scan: {len(disclosures)} disclosures "
                     f"({summary.get('file', 0)} file / {summary.get('monitor', 0)} "
                     f"monitor / {summary.get('drop', 0)} drop)"),
            entity_id=run_id,
            payload={"run_id": run_id, "report_date": report_date, **summary,
                     "report_path": report_path})
        self.state.emit(
            event_type="ip_report_written",
            summary=f"IP-Scout daily report written for {report_date}",
            entity_id=report_date,
            payload={"report_date": report_date, "report_path": report_path})

        return {
            "ok": True, "run_id": run_id, "report_date": report_date,
            "ideas_scanned": len(pending), "disclosures_created": len(disclosures),
            "report_path": report_path, "offline": self.offline,
            "provider": self.provider.name, **summary,
            "disclosures": disclosures,
        }

    def _render_and_store_report(self, report_date: str, disclosures: list[dict]) -> str:
        import report as report_mod
        return report_mod.render_report(
            report_date, disclosures, offline=self.offline, provider=self.provider.name)

    @staticmethod
    def _summarize(disclosures: list[dict]) -> dict:
        s = {"file": 0, "monitor": 0, "drop": 0, "attorney_review": 0}
        for d in disclosures:
            s[d.get("recommendation", "monitor")] = s.get(d.get("recommendation", "monitor"), 0) + 1
            if d.get("attorney_review_needed"):
                s["attorney_review"] += 1
        return s

    # -- reads ---------------------------------------------------------------

    def status(self) -> dict:
        ideas = store.list_ideas()
        runs = store.list_runs(limit=1)
        return {
            "status": "ok",
            "module": "eva-ip-scout",
            "autonomy": "L1 — triage + report only; never files or submits anything",
            "offline": self.offline,
            "provider": self.provider.name,
            "sensors": ["user-seed (~/.eva/ip_ideas.json)", "activity-mining (eva-state)"],
            "ideas_total": len(ideas),
            "ideas_pending": len([i for i in ideas if i.get("status") == store.STATUS_PENDING]),
            "ideas_triaged": len([i for i in ideas if i.get("status") == store.STATUS_TRIAGED]),
            "last_run": runs[0] if runs else None,
            "reports": store.list_report_dates(),
        }

    def list_ideas(self, status: str | None = None) -> list[dict]:
        return store.list_ideas(status=status)

    def get_idea(self, idea_id: str) -> dict | None:
        idea = store.get_idea(idea_id)
        if idea is None:
            return None
        idea = dict(idea)
        idea["latest_disclosure"] = store.latest_disclosure_for_idea(idea_id)
        return idea

    def history(self, limit: int | None = None) -> list[dict]:
        return store.list_runs(limit=limit)

    def get_report(self, report_date: str) -> str | None:
        return store.get_report(report_date)


__all__ = ["IPScoutService", "MAX_CLAIMS"]
