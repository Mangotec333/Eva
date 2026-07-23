#!/usr/bin/env python3
"""
Autonomy graduation tracker
===========================
Operationalizes the modules/README.md "Two-phase release standard": every module
ships, then earns autonomous mode after a 2-week (14-day) manual-testing window.
"Autonomous mode is earned, not assumed."

This tracker only **computes and surfaces** graduation eligibility. It NEVER
self-promotes a module — graduation is always a human action
(``POST /autonomy/{module}/graduate`` on the launcher). Reverting is symmetric.

Storage is config-file-primary (mirrors ``~/.eva/local_exec_allowlist.json`` and
friends): the record store lives at ``~/.eva/autonomy_status.json`` with an
in-code default when the file is absent. The append-only history is a JSON-lines
log at ``~/.eva/autonomy_history.jsonl`` — nothing ever rewrites or deletes a
prior line (the immutability pattern used by postcards / local-exec ledgers,
expressed as an append-only file).

Every record: ``{module, status, shipped_at, graduated_at}``. ``status`` is
``"manual_testing"`` (default on ship) or ``"autonomous"`` (graduated).
Derived, calculated-on-read (never persisted): ``graduation_eligible``,
``days_since_shipped``, ``days_until_eligible``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# The window a module must spend in manual testing before it may graduate.
GRADUATION_WINDOW_DAYS = 14

STATUS_MANUAL = "manual_testing"
STATUS_AUTONOMOUS = "autonomous"

_DEFAULT_STORE = Path.home() / ".eva" / "autonomy_status.json"
_DEFAULT_HISTORY = Path.home() / ".eva" / "autonomy_history.jsonl"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _module_dir_for(cmd: str) -> Optional[str]:
    """Extract the ``modules/<dir>`` component from a SERVICES cmd string.

    Returns the directory name (e.g. ``"triage-brain"``) or None when the cmd
    doesn't run out of a module dir (e.g. the external ``screenpipe`` binary).
    """
    if not cmd:
        return None
    marker = "modules/"
    idx = cmd.find(marker)
    if idx == -1:
        return None
    rest = cmd[idx + len(marker):]
    # dir name ends at the next path separator or whitespace
    for sep in ("/", " ", "&"):
        pos = rest.find(sep)
        if pos != -1:
            rest = rest[:pos]
    rest = rest.strip()
    return rest or None


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # tolerate a trailing Z
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class AutonomyTracker:
    """JSON-file-primary autonomy-graduation tracker (config-file convention)."""

    def __init__(
        self,
        services: dict,
        *,
        store_path: Optional[os.PathLike | str] = None,
        history_path: Optional[os.PathLike | str] = None,
        repo_root: Optional[os.PathLike | str] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.services = services or {}
        self.store_path = Path(store_path) if store_path else _DEFAULT_STORE
        self.history_path = Path(history_path) if history_path else _DEFAULT_HISTORY
        # Repo root for git-log shipped_at derivation. Default: two levels up
        # from this file (modules/launcher/ -> repo root).
        self.repo_root = (
            Path(repo_root)
            if repo_root
            else Path(__file__).resolve().parents[2]
        )
        self.clock = clock or _utcnow

    # ── storage ────────────────────────────────────────────────────────────
    def _load(self) -> dict:
        if not self.store_path.exists():
            return {}
        try:
            data = json.loads(self.store_path.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, records: dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(records, indent=2, sort_keys=True))
        tmp.replace(self.store_path)

    def _append_history(self, entry: dict) -> None:
        """Append one immutable JSON line. Never rewrites/deletes prior lines."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    # ── shipped_at derivation ────────────────────────────────────────────────
    def _derive_shipped_at(self, name: str) -> Optional[str]:
        """First-add commit date for a service's module dir, via git log.

        Wrapped so a missing git / unresolvable path NEVER crashes seed — falls
        back to None (which surfaces as "unknown" shipped state).
        """
        info = self.services.get(name, {})
        module_dir = _module_dir_for(info.get("cmd", ""))
        if not module_dir:
            return None
        try:
            result = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%aI",
                 "--", f"modules/{module_dir}"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        if not lines:
            return None
        return lines[-1].strip()  # oldest add = first commit adding the dir

    # ── seed ──────────────────────────────────────────────────────────────
    def seed(self) -> dict:
        """Idempotent: add a record for every SERVICES key not already present.

        Existing records are never reset or mutated. Safe to call repeatedly.
        """
        records = self._load()
        added = []
        for name in self.services:
            if name in records:
                continue
            records[name] = {
                "module": name,
                "status": STATUS_MANUAL,
                "shipped_at": self._derive_shipped_at(name),
                "graduated_at": None,
            }
            added.append(name)
        if added:
            self._save(records)
        return {"seeded": added, "total": len(records)}

    # ── derived read ──────────────────────────────────────────────────────
    def _decorate(self, record: dict) -> dict:
        """Attach calculated-on-read fields (never persisted)."""
        out = dict(record)
        shipped = _parse_iso(record.get("shipped_at"))
        status = record.get("status", STATUS_MANUAL)
        days_since = None
        days_until = None
        eligible = False
        if shipped is not None:
            delta_days = (self.clock() - shipped).days
            days_since = delta_days
            remaining = GRADUATION_WINDOW_DAYS - delta_days
            days_until = max(0, remaining)
            eligible = (
                delta_days >= GRADUATION_WINDOW_DAYS
                and status == STATUS_MANUAL
            )
        out["graduation_eligible"] = eligible
        out["days_since_shipped"] = days_since
        out["days_until_eligible"] = days_until
        return out

    def get(self, module: str) -> Optional[dict]:
        record = self._load().get(module)
        if record is None:
            return None
        return self._decorate(record)

    def list_all(self) -> list:
        records = self._load()
        return [self._decorate(records[name]) for name in sorted(records)]

    def status_of(self, module: str) -> Optional[str]:
        """Compact status string for the launcher /status route."""
        record = self._load().get(module)
        return record.get("status") if record else None

    # ── transitions (human-triggered only) ───────────────────────────────────
    def _transition(self, module: str, to_status: str, action: str) -> Optional[dict]:
        records = self._load()
        record = records.get(module)
        if record is None:
            return None
        from_status = record.get("status", STATUS_MANUAL)
        record["status"] = to_status
        record["graduated_at"] = (
            self.clock().isoformat() if to_status == STATUS_AUTONOMOUS else None
        )
        records[module] = record
        self._save(records)
        self._append_history({
            "ts": self.clock().isoformat(),
            "module": module,
            "from_status": from_status,
            "to_status": to_status,
            "action": action,
        })
        return self._decorate(record)

    def graduate(self, module: str) -> Optional[dict]:
        """Human-triggered promotion to autonomous. None if unknown module."""
        return self._transition(module, STATUS_AUTONOMOUS, "graduate")

    def revert(self, module: str) -> Optional[dict]:
        """Human-triggered demotion back to manual_testing. None if unknown."""
        return self._transition(module, STATUS_MANUAL, "revert")

    def history(self, module: str) -> list:
        """That module's append-only history, newest first."""
        if not self.history_path.exists():
            return []
        entries = []
        try:
            for line in self.history_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("module") == module:
                    entries.append(entry)
        except OSError:
            return []
        entries.reverse()
        return entries
