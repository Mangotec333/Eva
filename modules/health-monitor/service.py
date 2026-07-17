"""
EVA Health Monitor — service layer (all core logic lives here).

Cross-module watchdog: on each ``tick()`` it probes every monitored module's
``/health`` endpoint (through the ``HealthClient`` chokepoint), records the
status (up/down + latency + http_code) to its own SQLite, and — if a module has
been down for ``failure_threshold`` consecutive ticks — raises an alert (writes
an ``alerts`` row + a ledger event + logs). When a previously-down module
recovers, its open alert is resolved.

The alert *delivery* is deliberately a single seam: ``_deliver_alert`` just logs
in v1. Wiring Slack / GHL / email later is a one-line swap there (set
``self.alert_sink``) — no other code changes needed.

Agent Intelligence Layer: reads ``docs/MISSION.md`` and ``docs/CURRENT_GOALS.md``
at startup (graceful no-op if absent) and keeps per-agent memory (last-run
summary) in its own SQLite ``memory`` table.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Callable, Optional

from config import (
    DEFAULT_FAILURE_THRESHOLD,
    DEFAULT_TIMEOUT_SECONDS,
    load_targets,
)
from database import (
    ALERT_OPEN,
    DB_PATH,
    STATUS_DOWN,
    STATUS_UP,
    Store,
)
from http_client import HealthClient, build_health_client

logger = logging.getLogger("eva.health_monitor")

# Shared read-only alignment artifacts (repo root is two levels up).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MISSION_PATH = os.path.join(_REPO_ROOT, "docs", "MISSION.md")
GOALS_PATH = os.path.join(_REPO_ROOT, "docs", "CURRENT_GOALS.md")


class NotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _read_if_present(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


class HealthMonitorService:
    def __init__(
        self,
        store: Optional[Store] = None,
        client: Optional[HealthClient] = None,
        targets: Optional[list[dict]] = None,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        alert_sink: Optional[Callable[[dict], None]] = None,
    ):
        self.store = store or Store()
        self.client = client or build_health_client()
        self.targets = targets if targets is not None else load_targets()
        self.failure_threshold = max(1, int(failure_threshold))
        self.timeout = timeout
        # The one-line-swap seam for real alert delivery (Slack/GHL/email later).
        self.alert_sink = alert_sink
        self._load_alignment()

    # ------------------------------------------------------------------
    # Agent Intelligence Layer — mission + goals + memory
    # ------------------------------------------------------------------

    def _load_alignment(self) -> None:
        self.mission = _read_if_present(MISSION_PATH)
        self.current_goals = _read_if_present(GOALS_PATH)

    def get_memory(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.store.get_memory_value(key, default)

    def set_memory(self, key: str, value: str, source: str = "system") -> dict:
        return self.store.set_memory(key, value, source=source)

    def list_memory(self) -> list[dict]:
        return self.store.list_memory()

    # ------------------------------------------------------------------
    # Targets / status
    # ------------------------------------------------------------------

    def list_targets(self) -> list[dict]:
        return list(self.targets)

    def status(self) -> list[dict]:
        """Latest known status per module, enriched with consecutive failures."""
        latest = {c["module"]: c for c in self.store.latest_checks()}
        out = []
        for t in self.targets:
            check = latest.get(t["name"])
            out.append({
                "module": t["name"],
                "url": t["url"],
                "status": check["status"] if check else "unknown",
                "latency_ms": check["latency_ms"] if check else -1,
                "http_code": check["http_code"] if check else 0,
                "checked_at": check["checked_at"] if check else "",
                "consecutive_failures": self.store.consecutive_failures(t["name"]),
            })
        return out

    # ------------------------------------------------------------------
    # tick — probe every module, record, alert (cron-safe, idempotent)
    # ------------------------------------------------------------------

    def tick(self, actor: str = "system") -> dict:
        """Probe every monitored module's /health, record a check row, and raise
        or resolve alerts. Safe to call repeatedly / from a cron: each tick just
        appends the current observation; no duplicate alerts are opened while one
        is already open for a module."""
        checked_at = _now_iso()
        results = []
        up_count = 0
        new_alerts = []
        resolved_alerts = []

        for target in self.targets:
            name, url = target["name"], target["url"]
            probe = self.client.probe(url, timeout=self.timeout)
            status = STATUS_UP if probe.ok else STATUS_DOWN
            if probe.ok:
                up_count += 1
            self.store.insert_check({
                "module": name,
                "url": url,
                "status": status,
                "latency_ms": probe.latency_ms,
                "http_code": probe.http_code,
                "error": probe.error,
                "checked_at": checked_at,
            })
            self.store.append_ledger(
                "checked", entity_type="module", entity_id=name, actor=actor,
                details={"status": status, "http_code": probe.http_code,
                         "latency_ms": probe.latency_ms, "error": probe.error},
            )

            consecutive = self.store.consecutive_failures(name)
            open_alert = self.store.open_alert_for(name)

            if status == STATUS_DOWN and consecutive >= self.failure_threshold and not open_alert:
                alert = self._raise_alert(name, url, consecutive, actor)
                new_alerts.append(alert)
            elif status == STATUS_UP and open_alert:
                resolved = self._resolve_alert(open_alert, actor)
                resolved_alerts.append(resolved)

            results.append({
                "module": name, "status": status,
                "latency_ms": probe.latency_ms, "http_code": probe.http_code,
                "consecutive_failures": consecutive, "error": probe.error,
            })

        summary = {
            "ticked_at": checked_at,
            "monitored": len(self.targets),
            "up": up_count,
            "down": len(self.targets) - up_count,
            "new_alerts": len(new_alerts),
            "resolved_alerts": len(resolved_alerts),
        }
        self.set_memory("last_tick", checked_at, source=actor)
        self.set_memory("last_run_summary", str(summary), source=actor)
        return {**summary, "results": results,
                "alerts_opened": new_alerts, "alerts_resolved": resolved_alerts}

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _raise_alert(self, module: str, url: str, consecutive: int, actor: str) -> dict:
        message = (
            f"{module} has been DOWN for {consecutive} consecutive checks "
            f"(threshold {self.failure_threshold}). URL: {url}"
        )
        alert = self.store.insert_alert({
            "module": module, "url": url, "status": ALERT_OPEN,
            "consecutive_failures": consecutive, "message": message,
        })
        self.store.append_ledger(
            "alert_opened", entity_type="module", entity_id=module, actor=actor,
            details={"consecutive_failures": consecutive, "message": message},
        )
        self._deliver_alert(alert)
        return alert

    def _resolve_alert(self, open_alert: dict, actor: str) -> dict:
        resolved = self.store.resolve_alert(open_alert["id"])
        self.store.append_ledger(
            "alert_resolved", entity_type="module", entity_id=open_alert["module"],
            actor=actor, details={"alert_id": open_alert["id"]},
        )
        return resolved or open_alert

    def _deliver_alert(self, alert: dict) -> None:
        """The single delivery seam. v1 logs; wiring Slack / GHL / email later is
        a one-line swap: pass an ``alert_sink`` callable to the service (or set
        ``self.alert_sink``) and it is invoked here with the alert dict."""
        logger.warning("[health-monitor] ALERT: %s", alert.get("message", ""))
        if self.alert_sink is not None:
            try:
                self.alert_sink(alert)
            except Exception as exc:  # noqa: BLE001 — delivery must never break a tick
                logger.error("[health-monitor] alert_sink failed: %s", exc)

    def list_alerts(self, status: Optional[str] = None) -> list[dict]:
        return self.store.list_alerts(status=status)

    # ------------------------------------------------------------------
    # Checks / ledger / status helpers
    # ------------------------------------------------------------------

    def recent_checks(self, module: Optional[str] = None, limit: int = 100) -> list[dict]:
        return self.store.recent_checks(module=module, limit=limit)

    def last_run(self) -> dict:
        return {
            "last_tick": self.get_memory("last_tick", ""),
            "last_run_summary": self.get_memory("last_run_summary", ""),
        }

    def query_ledger(self, from_ts=None, to_ts=None, event_type=None) -> list[dict]:
        return self.store.query_ledger(from_ts=from_ts, to_ts=to_ts, event_type=event_type)

    @property
    def db_path(self) -> str:
        return getattr(self.store, "db_path", DB_PATH)
