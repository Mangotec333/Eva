"""
EVA Channels — service layer (all enforced rules live here).

Mirrors postcards' ``PostcardsService`` and projects' ``ProjectsService``: the
REST API and the CLI both call this one place so their behaviour is identical.
Responsibilities:

  * CRUD for channel items (create draft, list, get, update).
  * Approval gate: publishing is irreversible, so ``publish`` releases only
    ``approved`` items. ``draft`` items are rejected; nothing auto-publishes.
  * Idempotent publish: re-publishing an already-``posted`` item is a no-op that
    returns the existing ``post_url`` (no double-post).
  * Per-platform transport dispatch through the ``Publisher`` registry.
  * ``tick``: publish the next approved-due item and advance ``next_due``. Safe
    to call repeatedly from cron.
  * Agent intelligence layer: ``memory`` read/write + graceful reads of
    ``docs/MISSION.md`` and ``docs/CURRENT_GOALS.md``.

Every mutating action appends to the append-only channels ledger.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import DB_PATH, Store
from models import ITEM_TRANSITIONS, PLATFORMS
from publisher import Publisher, PublishResult, build_publisher

# Repo-root docs consumed by the agent intelligence layer (graceful no-op).
_DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
MISSION_PATH = os.environ.get("EVA_MISSION_PATH", os.path.join(_DOCS_DIR, "MISSION.md"))
GOALS_PATH = os.environ.get("EVA_GOALS_PATH", os.path.join(_DOCS_DIR, "CURRENT_GOALS.md"))


class ChannelError(Exception):
    """Raised when a rule blocks an action. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class ChannelsService:
    def __init__(
        self,
        store: Optional[Store] = None,
        publishers: Optional[dict[str, Publisher]] = None,
    ):
        self.store = store or Store()
        # A {platform: Publisher} registry. Injected in tests (fake-success /
        # not-wired stubs); built from the real transports otherwise.
        self.publishers: dict[str, Publisher] = publishers or {
            platform: build_publisher(platform, self.store.get_config(platform))
            for platform in PLATFORMS
        }
        self.read_mission_and_goals()

    # ------------------------------------------------------------------
    # Items — CRUD
    # ------------------------------------------------------------------

    def create_item(self, payload: dict) -> dict:
        platform = payload.get("platform", "")
        if platform not in PLATFORMS:
            raise ChannelError(
                "invalid_platform",
                f"unknown platform {platform!r}; expected one of {PLATFORMS}",
            )
        item = self.store.insert_item(payload)
        self.store.append_ledger(
            "item_created",
            entity_type="item",
            entity_id=item["id"],
            actor=payload.get("actor", "system"),
            details={"platform": item["platform"], "title": item["title"]},
        )
        return item

    def list_items(self, status: Optional[str] = None,
                   platform: Optional[str] = None) -> list[dict]:
        return self.store.list_items(status=status, platform=platform)

    def get_item(self, item_id: str) -> dict:
        item = self.store.get_item(item_id)
        if not item:
            raise NotFoundError(f"item {item_id!r} not found")
        return item

    def update_item(self, item_id: str, fields: dict, actor: str = "system") -> dict:
        self.get_item(item_id)
        status = fields.pop("status", None)
        clean = {k: v for k, v in fields.items() if v is not None and k != "actor"}
        updated = self.store.update_item(item_id, clean) if clean else self.get_item(item_id)
        if clean:
            self.store.append_ledger(
                "item_updated",
                entity_type="item",
                entity_id=item_id,
                actor=actor,
                details={"changed": list(clean.keys())},
            )
        if status is not None:
            updated = self._transition(item_id, status, actor)
        return updated

    def _transition(self, item_id: str, status: str, actor: str) -> dict:
        item = self.get_item(item_id)
        if status == item["status"]:
            return item
        allowed_prior = ITEM_TRANSITIONS.get(status)
        if allowed_prior is None:
            raise ChannelError("invalid_status", f"unknown item status {status!r}")
        if item["status"] not in allowed_prior:
            raise ChannelError(
                "invalid_transition",
                f"cannot move item from {item['status']!r} to {status!r}",
            )
        updated = self.store.update_item(item_id, {"status": status})
        self.store.append_ledger(
            f"item_{status}",
            entity_type="item",
            entity_id=item_id,
            actor=actor,
            details={"from": item["status"], "to": status},
        )
        return updated

    def approve_item(self, item_id: str, actor: str = "system") -> dict:
        return self._transition(item_id, "approved", actor)

    # ------------------------------------------------------------------
    # Publishing (approval-gated + idempotent)
    # ------------------------------------------------------------------

    def _publisher_for(self, platform: str) -> Publisher:
        pub = self.publishers.get(platform)
        if pub is None:
            pub = build_publisher(platform, self.store.get_config(platform))
            self.publishers[platform] = pub
        return pub

    def publish_item(self, item_id: str, actor: str = "system") -> dict:
        """Release an item through its platform transport.

        Rules:
          * Only ``approved`` items publish. ``draft``/``failed`` are rejected
            (publishing is irreversible — never auto-publish).
          * Idempotent: an already-``posted`` item is a no-op that returns the
            existing ``post_url`` (no double-post).
        """
        item = self.get_item(item_id)

        # Idempotency: never double-post.
        if item["status"] == "posted":
            self.store.append_ledger(
                "publish_noop",
                entity_type="item",
                entity_id=item_id,
                actor=actor,
                details={"reason": "already_posted", "post_url": item["post_url"]},
            )
            return {
                "item": item,
                "result": {
                    "ok": True,
                    "provider": item["platform"],
                    "post_url": item["post_url"],
                    "error": "",
                    "needs_manual_publish": False,
                    "noop": True,
                },
            }

        # Approval gate.
        if item["status"] != "approved":
            self.store.append_ledger(
                "publish_rejected",
                entity_type="item",
                entity_id=item_id,
                actor=actor,
                details={"status": item["status"], "reason": "not_approved"},
            )
            return {
                "item": item,
                "result": {
                    "ok": False,
                    "provider": item["platform"],
                    "post_url": "",
                    "error": f"item not approved (status={item['status']})",
                    "needs_manual_publish": False,
                    "rejected": True,
                },
            }

        return self._release(item, actor)

    def _release(self, item: dict, actor: str) -> dict:
        """Send an approved item to its transport and record the outcome."""
        publisher = self._publisher_for(item["platform"])
        result: PublishResult = publisher.publish(item)

        if not result.ok:
            updated = self.store.update_item(
                item["id"], {"status": "failed", "error": result.error}
            )
            self.store.append_ledger(
                "item_failed",
                entity_type="item",
                entity_id=item["id"],
                actor=actor,
                details={
                    "provider": result.provider,
                    "error": result.error,
                    "needs_manual_publish": result.needs_manual_publish,
                },
            )
            self.store.set_memory(
                "last_run",
                json.dumps({
                    "ts": _now_iso(), "item_id": item["id"],
                    "platform": item["platform"], "ok": False,
                    "error": result.error,
                }),
                source="publish",
            )
            return {"item": updated, "result": _result_dict(result)}

        posted_at = _now_iso()
        updated = self.store.update_item(
            item["id"],
            {"status": "posted", "posted_at": posted_at,
             "post_url": result.post_url, "error": ""},
        )
        self.store.append_ledger(
            "item_posted",
            entity_type="item",
            entity_id=item["id"],
            actor=actor,
            details={
                "provider": result.provider,
                "post_url": result.post_url,
                "posted_at": posted_at,
            },
        )
        self.store.set_memory(
            "last_run",
            json.dumps({
                "ts": posted_at, "item_id": item["id"],
                "platform": item["platform"], "ok": True,
                "post_url": result.post_url,
            }),
            source="publish",
        )
        return {"item": updated, "result": _result_dict(result)}

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def tick(self, actor: str = "system", now: Optional[datetime] = None) -> dict:
        """Publish the next approved-due item and advance ``next_due``.

        Safe to call repeatedly: if nothing is approved-due, nothing happens.
        """
        now_dt = now or _now()
        now_iso = now_dt.isoformat()
        sched = self.store.get_schedule()
        cadence_days = int(sched.get("cadence_days", 1))
        next_due = sched.get("next_due", "")

        # Schedule-clock gate: nothing releases before next_due (if set).
        if next_due and now_iso < next_due:
            return {"posted": None, "reason": "not_due", "next_due": next_due}

        item = self.store.next_due_item(now_iso)
        if not item:
            return {"posted": None, "reason": "no_due_item", "next_due": next_due}

        outcome = self._release(item, actor)
        result = outcome["result"]
        if not result["ok"]:
            return {
                "posted": None, "reason": "publish_failed",
                "item": outcome["item"], "error": result["error"],
                "next_due": next_due,
            }

        new_next_due = self._advance_next_due(next_due, now_dt, cadence_days)
        self.store.update_schedule({"next_due": new_next_due})
        return {"posted": outcome["item"], "reason": "posted",
                "next_due": new_next_due, "result": result}

    @staticmethod
    def _advance_next_due(next_due: str, now_dt: datetime, cadence_days: int) -> str:
        base = _parse_dt(next_due) or now_dt
        return (base + timedelta(days=cadence_days)).isoformat()

    # ------------------------------------------------------------------
    # Platform config + schedule
    # ------------------------------------------------------------------

    def get_config(self, platform: str) -> dict:
        if platform not in PLATFORMS:
            raise NotFoundError(f"platform {platform!r} not found")
        return self.store.get_config(platform)

    def update_config(self, platform: str, values: dict, actor: str = "system") -> dict:
        if platform not in PLATFORMS:
            raise NotFoundError(f"platform {platform!r} not found")
        clean = {k: v for k, v in values.items() if v is not None}
        updated = self.store.update_config(platform, clean)
        # Refresh the live publisher so subsequent publishes use the new config.
        self.publishers[platform] = build_publisher(platform, updated)
        self.store.append_ledger(
            "config_updated",
            entity_type="config",
            entity_id=platform,
            actor=actor,
            details={"changed": list(clean.keys())},
        )
        return updated

    def get_schedule(self) -> dict:
        return self.store.get_schedule()

    def update_schedule(self, fields: dict, actor: str = "system") -> dict:
        clean = {k: v for k, v in fields.items() if v is not None and k != "actor"}
        updated = self.store.update_schedule(clean)
        self.store.append_ledger(
            "schedule_updated",
            entity_type="schedule",
            entity_id="",
            actor=actor,
            details=clean,
        )
        return updated

    # ------------------------------------------------------------------
    # Agent intelligence layer — memory + mission/goals
    # ------------------------------------------------------------------

    def set_memory(self, key: str, value: str, source: str = "cli") -> dict:
        return self.store.set_memory(key, value, source=source)

    def get_memory(self, key: str) -> Optional[dict]:
        return self.store.get_memory(key)

    def all_memory(self) -> list[dict]:
        return self.store.all_memory()

    def read_mission_and_goals(self) -> dict:
        """Read the founder's mission + current goals at startup. Absent files
        are a graceful no-op (never crash)."""
        mission = _read_text(MISSION_PATH)
        goals = _read_text(GOALS_PATH)
        if mission:
            self.store.set_memory("mission", mission, source="docs/MISSION.md")
        if goals:
            self.store.set_memory("current_goals", goals, source="docs/CURRENT_GOALS.md")
        return {"mission": mission, "current_goals": goals}

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        last = self.store.get_memory("last_run")
        return {
            "providers": list(PLATFORMS),
            "last_run": last["value"] if last else "",
            "pending_approved": self.store.count_by_status("approved"),
            "posted_count": self.store.count_by_status("posted"),
        }

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def query_ledger(self, from_ts=None, to_ts=None, event_type=None) -> list[dict]:
        return self.store.query_ledger(from_ts=from_ts, to_ts=to_ts, event_type=event_type)

    def export_ledger(self, fmt: str = "json") -> str:
        import csv
        import io

        rows = self.store.query_ledger()
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["id", "ts", "event_type", "entity_type", "entity_id", "actor", "details_json"]
            )
            for r in rows:
                writer.writerow(
                    [r["id"], r["ts"], r["event_type"], r["entity_type"],
                     r["entity_id"], r["actor"], r.get("details_json", "{}")]
                )
            return buf.getvalue()
        return json.dumps(rows, indent=2, default=str)

    @property
    def db_path(self) -> str:
        return getattr(self.store, "db_path", DB_PATH)


def _result_dict(result: PublishResult) -> dict:
    return {
        "ok": result.ok,
        "provider": result.provider,
        "post_url": result.post_url,
        "error": result.error,
        "needs_manual_publish": result.needs_manual_publish,
    }


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (FileNotFoundError, OSError):
        return ""
