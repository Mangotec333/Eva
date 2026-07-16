"""
EVA Brand-Builder — service layer (the strategy/orchestration brain).

Position in the stack: the Brand Builder sits ABOVE content-engine (:8767, which
makes content) and social-scheduler (:8787, which approves + posts). It writes
content BRIEFS and NEVER posts. Approval stays L1 — drafts only, the user
approves before anything goes out (``approval_required: true`` on every pipeline
and brief).

Responsibilities wired here:
  * seed    — parse a blueprint markdown → pipeline.json + blueprint.json +
              persona configs (the seed md is the source of truth).
  * plan    — turn a pipeline + blueprint + personas into a weekly set of briefs.
  * queue   — emit each brief to content-engine via an eva-state
              ``brand_brief_created`` event (content-engine picks them up).
  * refresh — re-check blueprints for staleness (version older than 7 days →
              ``brand_blueprint_stale``).

Offline-safe: with ``EVA_BRAND_OFFLINE=1`` the state client is a stub (no
network) and missing pipelines/blueprints fall back to mocked objects so every
endpoint still returns a usable shape.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import blueprint as blueprint_mod
import personas as personas_mod
import planner
import store
from state_client import StateLedgerClient, build_state_client

STALE_AFTER_DAYS = 7
FIRST_PIPELINE_ID = "eva-growth-agency"


def default_seed_md() -> str:
    """Locate the seed blueprint markdown (env → module seed/ → workspace)."""
    env = os.environ.get("EVA_BRAND_SEED_MD", "").strip()
    if env and Path(env).exists():
        return env
    local = Path(__file__).parent / "seed" / "brand_blueprint_eva_growth_agency.md"
    if local.exists():
        return str(local)
    ws = Path.home() / "workspace" / "brand_blueprint_eva_growth_agency.md"
    return str(ws)


class BrandBuilderService:
    def __init__(self, *, state: StateLedgerClient | None = None,
                 offline: bool | None = None) -> None:
        self.offline = offline if offline is not None else (
            os.environ.get("EVA_BRAND_OFFLINE") == "1")
        self.state = state or build_state_client(offline=self.offline)

    # -- seeding -------------------------------------------------------------

    def seed(self, *, pipeline_id: str = FIRST_PIPELINE_ID,
             md_path: str | None = None) -> dict:
        """Parse the blueprint md → pipeline + blueprint + personas; persist all."""
        path = md_path or default_seed_md()
        pipeline, bp = blueprint_mod.parse_file(path, pipeline_id)

        store.save_blueprint(pipeline["category"], bp)
        store.save_pipeline(pipeline)
        persona_map = personas_mod.default_personas(bp)
        for name, persona in persona_map.items():
            store.save_persona(name, persona)

        self.state.emit(
            event_type="brand_pipeline_seeded",
            summary=f"Seeded pipeline '{pipeline_id}' from blueprint ({pipeline['category']})",
            entity_id=pipeline_id,
            payload={"category": pipeline["category"],
                     "blueprint_version": pipeline["blueprint_version"],
                     "market_patterns": len(bp["market_patterns"]),
                     "personas": list(persona_map.keys()),
                     "source_md": path})
        return {"ok": True, "pipeline": pipeline, "blueprint_category": pipeline["category"],
                "personas": list(persona_map.keys())}

    # -- reads ---------------------------------------------------------------

    def get_pipeline(self, pipeline_id: str) -> dict | None:
        p = store.get_pipeline(pipeline_id)
        if p is None and self.offline:
            return self._mock_pipeline(pipeline_id)
        return p

    def list_pipelines(self) -> list[dict]:
        pipelines = store.list_pipelines()
        if not pipelines and self.offline:
            return [self._mock_pipeline(FIRST_PIPELINE_ID)]
        return pipelines

    def get_blueprint(self, category: str) -> dict | None:
        b = store.get_blueprint(category)
        if b is None and self.offline:
            return self._mock_blueprint(category)
        return b

    def list_briefs(self, status: str | None = None) -> list[dict]:
        return store.list_briefs(status=status)

    def status(self) -> dict:
        pipelines = store.list_pipelines()
        blueprints = store.list_blueprints()
        stale = [b["category"] for b in blueprints
                 if self.is_stale(b.get("blueprint_version", ""))]
        return {
            "status": "ok",
            "module": "eva-brand-builder",
            "offline": self.offline,
            "sits_above": ["content-engine:8767", "social-scheduler:8787"],
            "writes": "content briefs (never posts)",
            "approval": "L1 — drafts only, user approves before posting",
            "pipelines": [p["pipeline_id"] for p in pipelines],
            "blueprints": [b["category"] for b in blueprints],
            "personas": [p["name"] for p in store.list_personas()],
            "briefs_pending": len(store.list_briefs(status=store.STATUS_PENDING)),
            "briefs_queued": len(store.list_briefs(status=store.STATUS_QUEUED)),
            "stale_blueprints": stale,
        }

    # -- planning ------------------------------------------------------------

    def plan(self, *, pipeline_id: str, timeframe: str = "week",
             start_date: str | None = None, persist: bool = True) -> dict:
        """Generate a weekly content plan (list of briefs) and persist them."""
        pipeline = self.get_pipeline(pipeline_id)
        if pipeline is None:
            return {"ok": False, "error": f"unknown pipeline: {pipeline_id}"}
        bp = self.get_blueprint(pipeline["category"]) or self._mock_blueprint(pipeline["category"])
        persona_map = {p["name"]: p for p in store.list_personas()} or \
            personas_mod.default_personas(bp)

        briefs = planner.generate_plan(
            pipeline, bp, persona_map, timeframe=timeframe, start_date=start_date)

        if persist and not self.offline:
            briefs = [store.save_brief(b) for b in briefs]
        elif persist and self.offline:
            # offline still persists to the (temp/overridden) store so the flow
            # is exercisable end-to-end without network.
            briefs = [store.save_brief(b) for b in briefs]

        by_channel: dict[str, int] = {}
        for b in briefs:
            by_channel[b["channel"]] = by_channel.get(b["channel"], 0) + 1

        self.state.emit(
            event_type="brand_plan_created",
            summary=f"Weekly plan for '{pipeline_id}': {len(briefs)} briefs ({timeframe})",
            entity_id=pipeline_id,
            payload={"count": len(briefs), "timeframe": timeframe,
                     "by_channel": by_channel})
        return {"ok": True, "pipeline_id": pipeline_id, "timeframe": timeframe,
                "count": len(briefs), "by_channel": by_channel, "briefs": briefs}

    # -- queue (emit to content-engine) --------------------------------------

    def queue(self, *, brief_ids: list[str] | None = None,
              pipeline_id: str | None = None) -> dict:
        """Emit pending briefs to content-engine via brand_brief_created events."""
        if brief_ids:
            briefs = [b for b in (store.get_brief(bid) for bid in brief_ids) if b]
        else:
            briefs = store.list_briefs(status=store.STATUS_PENDING)
            if pipeline_id:
                briefs = [b for b in briefs if b.get("pipeline_id") == pipeline_id]

        emitted = []
        for b in briefs:
            res = self.state.emit(
                event_type="brand_brief_created",
                summary=f"[{b['channel']}] {b['archetype']} — {b['hook'][:60]}",
                entity_id=b["brief_id"],
                payload={
                    "brief_id": b["brief_id"],
                    "pipeline_id": b.get("pipeline_id", ""),
                    "channel": b.get("channel", ""),
                    "archetype": b.get("archetype", ""),
                    "persona": b.get("persona", ""),
                    "tone": b.get("tone", ""),
                    "hook": b.get("hook", ""),
                    "angle": b.get("angle", ""),
                    "cta": b.get("cta", ""),
                    "proof_asset": b.get("proof_asset", ""),
                    "voice_rules": b.get("voice_rules", []),
                    "do_not_say": b.get("do_not_say", []),
                    "scheduled_day": b.get("scheduled_day", ""),
                    "approval_required": b.get("approval_required", True),
                })
            store.update_brief(b["brief_id"], {"status": store.STATUS_QUEUED})
            emitted.append({"brief_id": b["brief_id"], "emit": res})

        return {"ok": True, "queued": len(emitted), "briefs": emitted}

    # -- staleness / refresh -------------------------------------------------

    def is_stale(self, blueprint_version: str, now: date | None = None) -> bool:
        """A blueprint is stale if its version date is older than 7 days."""
        v = _parse_version_date(blueprint_version)
        if v is None:
            return True  # unparseable/unknown version → treat as stale
        today = now or date.today()
        return (today - v) > timedelta(days=STALE_AFTER_DAYS)

    def refresh(self) -> dict:
        """Re-check every blueprint; emit brand_blueprint_stale for stale ones."""
        checked, stale = [], []
        for b in store.list_blueprints():
            cat = b.get("category", "")
            version = b.get("blueprint_version", "")
            checked.append(cat)
            if self.is_stale(version):
                stale.append(cat)
                self.state.emit(
                    event_type="brand_blueprint_stale",
                    summary=f"Blueprint stale (>{STALE_AFTER_DAYS}d): {cat} @ {version}",
                    entity_id=store.slugify(cat),
                    payload={"category": cat, "blueprint_version": version,
                             "stale_after_days": STALE_AFTER_DAYS})
        return {"ok": True, "checked": checked, "stale": stale,
                "fresh": [c for c in checked if c not in stale]}

    # -- offline mocks -------------------------------------------------------

    def _mock_blueprint(self, category: str) -> dict:
        today = date.today().isoformat()
        return {
            "category": category or "mock-category",
            "date": today,
            "audience": {"segments": [{"segment": "Mock buyers"}]},
            "market_patterns": [{
                "pattern": "Mock durability shift", "summary": "Mocked pattern.",
                "date": today, "source_url": "https://example.com", "confidence": "med"}],
            "channels": [{"rank": "1", "channel": "LinkedIn", "confidence": "high"},
                         {"rank": "2", "channel": "X (Twitter)", "confidence": "med"}],
            "content_archetypes": [{"name": "Deal Teardowns", "summary": "Mock", "confidence": "high"},
                                   {"name": "Data/Proof Posts", "summary": "Mock", "confidence": "high"},
                                   {"name": "Build-in-Public", "summary": "Mock", "confidence": "high"}],
            "authority_signals": [{"name": "Proprietary Data", "summary": "Mock", "confidence": "high"}],
            "awareness_loops": [{"name": "Weekly Teardown", "hook": "Mock hook", "distribution_motion": "Mock"}],
            "cadence": {"X (Twitter)": "Daily (1 post/day)", "LinkedIn": "3x/week", "Newsletter": "Weekly (1x/week)"},
            "cta_ladder": [{"stage": "Stage 3: Free Deal Audit", "cta": "Mock audit CTA", "goal": "Mock"}],
            "do_not_say": ["Guaranteed returns"],
            "kpis": [{"kpi": "Booked audits/month", "target": "5-10", "confidence": "med"}],
            "blueprint_version": today,
        }

    def _mock_pipeline(self, pipeline_id: str) -> dict:
        return blueprint_mod.derive_pipeline(pipeline_id, self._mock_blueprint("mock-category"))


def _parse_version_date(version: str) -> date | None:
    v = (version or "").strip()[:10]
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


__all__ = ["BrandBuilderService", "STALE_AFTER_DAYS", "FIRST_PIPELINE_ID", "default_seed_md"]
