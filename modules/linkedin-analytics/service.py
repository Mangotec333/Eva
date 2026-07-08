"""
EVA LinkedIn Analytics — service layer (all enforced rules live here).

Mirrors projects' ``ProjectsService`` and postcards' ``PostcardsService``: the
REST API and the CLI both call this one place so their behaviour is identical.
Responsibilities:

  * ``sync()`` — call the transport, upsert posts + analytics snapshots,
    compute engagement_rate canonically, append the ledger, update last_sync_at
    and next_due. Idempotent: re-syncing the same window upserts, never
    duplicates (enforced by the UNIQUE constraint in the DB).
  * ``tick()`` — sync only if due (next_due has arrived). Safe to call
    repeatedly from a cron; a no-op when not due or unconfigured.
  * Reading analytics is read-only / non-irreversible, so there is NO human
    approval gate on sync (unlike postcards publish). Every sync is still
    recorded in the append-only analytics ledger.

Agent intelligence layer (PR #16 section 2):
  * ``memory`` key/value store — read on task start, written on decision /
    learning.
  * Reads ``docs/MISSION.md`` and ``docs/CURRENT_GOALS.md`` at startup with a
    graceful no-op if absent (never crash on a missing mission/goals file).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from client import AnalyticsClient, FetchResult, PostMetrics, build_client
from database import DB_PATH, Store

# Shared, read-only alignment artifacts live at the repo root under docs/.
# Env overrides let the host relocate them; absence is a graceful no-op.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MISSION_PATH = os.environ.get(
    "EVA_MISSION_PATH", os.path.join(_REPO_ROOT, "docs", "MISSION.md")
)
GOALS_PATH = os.environ.get(
    "EVA_CURRENT_GOALS_PATH", os.path.join(_REPO_ROOT, "docs", "CURRENT_GOALS.md")
)


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


def compute_engagement_rate(
    reactions: int, comments: int, shares: int, impressions: int
) -> float:
    """(reactions + comments + shares) / impressions, guarding division by 0."""
    if not impressions:
        return 0.0
    return (reactions + comments + shares) / impressions


class NotFoundError(Exception):
    pass


class LinkedInAnalyticsService:
    def __init__(
        self,
        store: Optional[Store] = None,
        client: Optional[AnalyticsClient] = None,
    ):
        self.store = store or Store()
        self.client = client or build_client()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def get_config(self) -> dict:
        return self.store.get_config()

    def set_config(self, fields: dict, actor: str = "system") -> dict:
        clean = {
            k: v
            for k, v in fields.items()
            if v is not None and k not in ("actor",)
        }
        updated = self.store.set_config(clean) if clean else self.get_config()
        self.store.append_ledger(
            "config_updated",
            entity_type="config",
            actor=actor,
            details=clean,
        )
        return updated

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync(self, actor: str = "system", now: Optional[datetime] = None) -> dict:
        """Pull latest analytics and upsert posts + snapshots. Idempotent.

        Reading analytics is non-irreversible, so there is no approval gate.
        Every attempt — success or failure — is recorded in the ledger.
        """
        now_dt = now or _now()
        cfg = self.store.get_config()
        author_urn = cfg.get("author_urn", "")
        window_days = int(cfg.get("sync_window_days") or 28)

        if not author_urn:
            error = "no author_urn configured — set it via config first"
            self.store.append_ledger(
                "sync_skipped",
                entity_type="sync",
                actor=actor,
                details={"reason": "no_author_urn"},
            )
            return {"ok": False, "provider": self.client.name, "posts_synced": 0,
                    "snapshots_upserted": 0, "error": error}

        result: FetchResult = self.client.fetch(author_urn, window_days)

        if not result.ok:
            self.store.append_ledger(
                "sync_failed",
                entity_type="sync",
                actor=actor,
                details={"provider": result.provider, "error": result.error,
                         "author_urn": author_urn, "window_days": window_days},
            )
            return {"ok": False, "provider": result.provider, "posts_synced": 0,
                    "snapshots_upserted": 0, "error": result.error}

        # Deterministic window (date granularity) so two syncs on the same day
        # target the same snapshot row -> idempotent upsert, no duplicates.
        window_end = now_dt.date().isoformat()
        window_start = (now_dt - timedelta(days=window_days)).date().isoformat()
        snapshot_ts = now_dt.isoformat()

        posts_synced = 0
        snapshots_upserted = 0
        for pm in result.posts:
            self._store_post(pm, author_urn)
            self._store_snapshot(
                pm, result.provider, window_start, window_end, snapshot_ts
            )
            posts_synced += 1
            snapshots_upserted += 1

        last_sync_at = now_dt.isoformat()
        next_due = (now_dt + timedelta(days=1)).isoformat()
        self.store.set_config({"last_sync_at": last_sync_at, "next_due": next_due})
        self.store.append_ledger(
            "sync_completed",
            entity_type="sync",
            actor=actor,
            details={
                "provider": result.provider,
                "author_urn": author_urn,
                "posts_synced": posts_synced,
                "snapshots_upserted": snapshots_upserted,
                "window_start": window_start,
                "window_end": window_end,
            },
        )
        return {"ok": True, "provider": result.provider,
                "posts_synced": posts_synced,
                "snapshots_upserted": snapshots_upserted, "error": ""}

    def _store_post(self, pm: PostMetrics, author_urn: str) -> dict:
        return self.store.upsert_post(
            {
                "post_urn": pm.post_urn,
                "share_urn": pm.share_urn,
                "author_urn": pm.author_urn or author_urn,
                "posted_at": pm.posted_at,
                "text": pm.text,
                "post_url": pm.post_url,
            }
        )

    def _store_snapshot(
        self,
        pm: PostMetrics,
        source: str,
        window_start: str,
        window_end: str,
        snapshot_ts: str,
    ) -> dict:
        engagement_rate = compute_engagement_rate(
            pm.reactions, pm.comments, pm.shares, pm.impressions
        )
        return self.store.upsert_snapshot(
            {
                "post_urn": pm.post_urn,
                "snapshot_ts": snapshot_ts,
                "window_start": window_start,
                "window_end": window_end,
                "impressions": pm.impressions,
                "unique_impressions": pm.unique_impressions,
                "clicks": pm.clicks,
                "reactions": pm.reactions,
                "comments": pm.comments,
                "shares": pm.shares,
                "engagement_rate": engagement_rate,
                "raw_json": json.dumps(pm.raw, default=str),
                "source": source,
            }
        )

    # ------------------------------------------------------------------
    # Tick (sync if due) — idempotent, cron-safe
    # ------------------------------------------------------------------

    def tick(self, actor: str = "system", now: Optional[datetime] = None) -> dict:
        """Sync only if due. No-op when unconfigured or not yet due."""
        now_dt = now or _now()
        cfg = self.store.get_config()

        if not cfg.get("author_urn"):
            return {"synced": False, "reason": "not_configured",
                    "next_due": cfg.get("next_due", "")}

        next_due = cfg.get("next_due", "")
        if next_due and now_dt.isoformat() < next_due:
            return {"synced": False, "reason": "not_due", "next_due": next_due}

        result = self.sync(actor=actor, now=now_dt)
        return {"synced": True, "reason": "due", "result": result,
                "next_due": self.store.get_config().get("next_due", "")}

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_posts(self) -> list[dict]:
        return self.store.list_posts()

    def get_post(self, post_urn: str) -> dict:
        post = self.store.get_post(post_urn)
        if not post:
            raise NotFoundError(f"post {post_urn!r} not found")
        post["snapshots"] = self.store.list_snapshots(post_urn)
        return post

    def list_snapshots(self, post_urn: str) -> list[dict]:
        if not self.store.get_post(post_urn):
            raise NotFoundError(f"post {post_urn!r} not found")
        return self.store.list_snapshots(post_urn)

    def summary(self, days: int = 28) -> dict:
        since = (_now() - timedelta(days=days)).isoformat()
        top = self.store.top_post_by_impressions(since_ts=None)
        cfg = self.store.get_config()
        return {
            "post_count": self.store.count_posts(),
            "snapshot_count": self.store.count_snapshots(),
            "provider": self.client.name,
            "last_sync_at": cfg.get("last_sync_at", ""),
            "author_urn": cfg.get("author_urn", ""),
            "window_days": days,
            "since": since,
            "top_post": top,
        }

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def query_ledger(
        self,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        return self.store.query_ledger(from_ts, to_ts, event_type)

    def export_ledger(self, fmt: str = "json") -> str:
        rows = self.store.query_ledger()
        if fmt == "json":
            return json.dumps(rows, indent=2, default=str)
        # CSV
        import csv
        import io

        buf = io.StringIO()
        fields = ["id", "ts", "event_type", "entity_type", "entity_id", "actor",
                  "details_json"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Health / last-run summary
    # ------------------------------------------------------------------

    def health(self) -> dict:
        cfg = self.store.get_config()
        return {
            "provider": self.client.name,
            "last_sync_at": cfg.get("last_sync_at", ""),
            "post_count": self.store.count_posts(),
            "snapshot_count": self.store.count_snapshots(),
        }

    # ------------------------------------------------------------------
    # Agent intelligence layer — memory + mission/goals
    # ------------------------------------------------------------------

    def memory_set(self, key: str, value: str, source: str = "system") -> dict:
        return self.store.memory_set(key, value, source)

    def memory_get(self, key: str) -> Optional[dict]:
        return self.store.memory_get(key)

    def memory_all(self) -> list[dict]:
        return self.store.memory_all()

    @staticmethod
    def _read_text_file(path: str) -> Optional[str]:
        """Read a text file, returning None if absent (graceful no-op)."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except (FileNotFoundError, IsADirectoryError, OSError):
            return None

    def read_mission(self) -> Optional[str]:
        """Read the shared, read-only mission. None if absent (no crash)."""
        return self._read_text_file(MISSION_PATH)

    def read_goals(self) -> Optional[str]:
        """Read the time-varying current goals. None if absent (no crash)."""
        return self._read_text_file(GOALS_PATH)

    def load_alignment(self) -> dict:
        """Read mission + goals at task start. Absent files are a graceful
        no-op (present=False), never an exception."""
        mission = self.read_mission()
        goals = self.read_goals()
        return {
            "mission_present": mission is not None,
            "goals_present": goals is not None,
            "mission": mission or "",
            "goals": goals or "",
        }
