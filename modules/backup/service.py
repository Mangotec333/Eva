"""
EVA Backup — service brain (framework-free, offline-testable).

``tick()`` is the cron-safe, idempotent entry point. On each tick it:

  1. Scans ``modules/*/*.db`` (every module's local SQLite files) at runtime.
  2. tar+gzips them into a single timestamped archive under a scratch dir.
  3. Uploads the archive to the configured Drive folder
     (``EVA_BACKUP_DRIVE_FOLDER_ID``) via the injected ``DriveClient``.
  4. Applies retention: keeps the newest N archives in the folder, deletes older.
  5. Logs success/failure + every retention delete to its own ``memory`` and the
     append-only ``backup_ledger`` (canonical postcards pattern).

Idempotent / cron-safe: a fresh tick simply produces the next timestamped
archive; retention converges the folder to N archives regardless of how many
ticks fired. No shared runtime state; the Drive transport is injected so tests
run fully offline with ``StubDriveClient``.
"""

from __future__ import annotations

import glob
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Optional

from database import Store
from drive_client import DriveClient, DriveError, build_drive_client

# Default retention: keep the newest N archives in Drive.
DEFAULT_RETENTION = int(os.environ.get("EVA_BACKUP_RETENTION", "14"))

# The archives we manage are named with this prefix so retention only ever
# touches our own uploads and never anything else in the folder.
ARCHIVE_PREFIX = "eva-backup-"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(now: Optional[datetime] = None) -> str:
    return (now or _now()).strftime("%Y%m%dT%H%M%SZ")


def _modules_root() -> str:
    # modules/backup/service.py -> modules/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BackupService:
    """Orchestrates scan -> archive -> upload -> retention.

    Args:
        store: persistence layer (memory + append-only ledger).
        drive: injected DriveClient (StubDriveClient in tests).
        folder_id: Drive folder to upload into. Defaults to
            ``EVA_BACKUP_DRIVE_FOLDER_ID``.
        modules_root: root dir scanned for ``*/*.db``. Defaults to the repo's
            ``modules/`` dir (so real ticks back up every module).
        retention: number of archives to keep in Drive.
        scratch_dir: where archives are built before upload. Defaults to a
            ``backups/`` dir beside this module (gitignored).
    """

    def __init__(
        self,
        store: Optional[Store] = None,
        drive: Optional[DriveClient] = None,
        folder_id: Optional[str] = None,
        modules_root: Optional[str] = None,
        retention: int = DEFAULT_RETENTION,
        scratch_dir: Optional[str] = None,
    ):
        self.store = store or Store()
        self.drive = drive or build_drive_client()
        self.folder_id = (
            folder_id if folder_id is not None
            else os.environ.get("EVA_BACKUP_DRIVE_FOLDER_ID", "")
        )
        self.modules_root = modules_root or _modules_root()
        self.retention = retention
        self.scratch_dir = scratch_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "backups"
        )

    # -- scan ---------------------------------------------------------------

    def find_db_files(self) -> list[str]:
        """All module SQLite files: ``modules/*/*.db`` (sorted, deduped).

        Skips this module's own ``eva-backup.db`` so a backup never races its
        own live DB write, and skips node_modules noise.
        """
        own_db = os.path.abspath(self.store.db_path)
        found = []
        for path in glob.glob(os.path.join(self.modules_root, "*", "*.db")):
            ap = os.path.abspath(path)
            if ap == own_db:
                continue
            if "node_modules" in ap:
                continue
            found.append(ap)
        return sorted(set(found))

    # -- archive ------------------------------------------------------------

    def build_archive(self, db_files: list[str], now: Optional[datetime] = None) -> str:
        """tar+gzip the given db files into a timestamped archive. Returns path.

        Each file is stored under an arcname of ``<module_dir>/<file>`` so the
        archive is self-describing (you can see which module each db came from).
        """
        os.makedirs(self.scratch_dir, exist_ok=True)
        name = f"{ARCHIVE_PREFIX}{_timestamp(now)}.tar.gz"
        archive_path = os.path.join(self.scratch_dir, name)
        with tarfile.open(archive_path, "w:gz") as tar:
            for f in db_files:
                module_dir = os.path.basename(os.path.dirname(f))
                arcname = os.path.join(module_dir, os.path.basename(f))
                tar.add(f, arcname=arcname)
        return archive_path

    # -- retention ----------------------------------------------------------

    def apply_retention(self, actor: str = "tick") -> list[str]:
        """Keep the newest ``retention`` archives in the folder; delete older.

        Only files matching ``ARCHIVE_PREFIX`` are considered, so nothing else in
        the folder is ever touched. Returns the list of deleted file ids.
        """
        files = [
            f for f in self.drive.list_files(self.folder_id)
            if f.get("name", "").startswith(ARCHIVE_PREFIX)
        ]
        # list_files returns newest-first; everything past retention is stale.
        stale = files[self.retention:] if self.retention > 0 else []
        deleted = []
        for f in stale:
            self.drive.delete_file(f["id"])
            deleted.append(f["id"])
            self.store.append_ledger(
                event_type="retention_delete",
                entity_type="file",
                entity_id=f["id"],
                actor=actor,
                details={"name": f.get("name", ""),
                         "created_time": f.get("created_time", "")},
            )
        return deleted

    # -- tick (cron-safe entry point) ---------------------------------------

    def tick(self, actor: str = "tick") -> dict:
        """One backup cycle. Never raises: failures are logged + returned."""
        db_files = self.find_db_files()

        if not self.folder_id:
            err = "no Drive folder configured — set EVA_BACKUP_DRIVE_FOLDER_ID."
            self.store.append_ledger(
                event_type="backup_error", actor=actor,
                details={"error": err, "db_count": len(db_files)},
            )
            self.store.remember("last_error", err, source=actor)
            return {"ok": False, "error": err, "db_files": db_files}

        if not db_files:
            # Nothing to back up yet (fresh repo). Not an error — record and stop.
            self.store.append_ledger(
                event_type="backup_ok", entity_type="archive", actor=actor,
                details={"db_count": 0, "skipped": "no module databases found"},
            )
            self.store.remember("last_tick", _now().isoformat(), source=actor)
            return {"ok": True, "uploaded": None, "db_files": [],
                    "note": "no module databases found"}

        now = _now()
        archive_path = self.build_archive(db_files, now=now)
        archive_name = os.path.basename(archive_path)
        size_bytes = os.path.getsize(archive_path)

        try:
            uploaded = self.drive.upload_file(
                archive_path, self.folder_id, name=archive_name
            )
        except DriveError as exc:
            self.store.append_ledger(
                event_type="backup_error", entity_type="archive",
                actor=actor,
                details={"error": str(exc), "archive": archive_name,
                         "db_count": len(db_files)},
            )
            self.store.remember("last_error", str(exc), source=actor)
            return {"ok": False, "error": str(exc), "archive": archive_name,
                    "db_files": db_files}

        self.store.append_ledger(
            event_type="backup_ok", entity_type="archive",
            entity_id=uploaded.get("id", ""), actor=actor,
            details={"archive": archive_name, "size_bytes": size_bytes,
                     "db_count": len(db_files),
                     "modules": sorted({os.path.basename(os.path.dirname(f))
                                        for f in db_files})},
        )
        self.store.remember("last_tick", now.isoformat(), source=actor)
        self.store.remember("last_archive_id", uploaded.get("id", ""), source=actor)
        self.store.remember("last_archive_name", archive_name, source=actor)

        deleted = self.apply_retention(actor=actor)

        return {
            "ok": True,
            "uploaded": uploaded,
            "archive": archive_name,
            "size_bytes": size_bytes,
            "db_files": db_files,
            "retention_deleted": deleted,
        }

    # -- status -------------------------------------------------------------

    def status(self) -> dict:
        """Current view: config, last run, and what's in Drive right now."""
        remote: list[dict] = []
        drive_error = None
        if self.folder_id:
            try:
                remote = [
                    f for f in self.drive.list_files(self.folder_id)
                    if f.get("name", "").startswith(ARCHIVE_PREFIX)
                ]
            except DriveError as exc:
                drive_error = str(exc)
        return {
            "drive": self.drive.name,
            "folder_id": self.folder_id or None,
            "retention": self.retention,
            "modules_root": self.modules_root,
            "db_files": self.find_db_files(),
            "last_tick": self.store.recall("last_tick"),
            "last_archive_id": self.store.recall("last_archive_id"),
            "last_archive_name": self.store.recall("last_archive_name"),
            "last_error": self.store.recall("last_error"),
            "archives_in_drive": len(remote),
            "drive_error": drive_error,
        }
