"""
EVA Backup — offline tests (zero network).

Everything runs against ``StubDriveClient`` and temp dirs, so no Drive/OAuth is
touched. Deliberately framework-free imports (no fastapi) so the suite runs on a
bare python with only stdlib + pytest.

Covered:
  * scan finds module *.db files (and skips its own db / node_modules)
  * tar+gzip archive is created and contains the scanned dbs
  * upload is called with the correct folder id + archive name
  * a full tick logs backup_ok to the append-only ledger + memory
  * retention keeps the newest N and deletes the older archives
  * missing folder id -> ok=False + backup_error ledger row (no upload)
  * the ledger really is append-only (UPDATE/DELETE blocked)
"""

from __future__ import annotations

import os
import sqlite3
import tarfile

import pytest

from database import Store
from drive_client import StubDriveClient
from service import ARCHIVE_PREFIX, BackupService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_modules_tree(root: str, modules: dict[str, list[str]]) -> None:
    """Create ``root/<module>/<dbfile>`` with a tiny valid sqlite db in each."""
    for module, dbs in modules.items():
        mod_dir = os.path.join(root, module)
        os.makedirs(mod_dir, exist_ok=True)
        for db in dbs:
            path = os.path.join(mod_dir, db)
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (1)")
            conn.commit()
            conn.close()


@pytest.fixture
def store(tmp_path):
    return Store(db_path=str(tmp_path / "eva-backup.db"))


@pytest.fixture
def modules_root(tmp_path):
    root = tmp_path / "modules"
    root.mkdir()
    _make_modules_tree(str(root), {
        "postcards": ["eva-postcards.db"],
        "finance-tracker": ["treasurer.db"],
        "empty-module": [],
    })
    return str(root)


def _service(store, modules_root, tmp_path, drive=None, folder_id="folder-123",
             retention=14):
    return BackupService(
        store=store,
        drive=drive or StubDriveClient(),
        folder_id=folder_id,
        modules_root=modules_root,
        retention=retention,
        scratch_dir=str(tmp_path / "scratch"),
    )


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def test_find_db_files_discovers_module_dbs(store, modules_root, tmp_path):
    svc = _service(store, modules_root, tmp_path)
    found = svc.find_db_files()
    names = sorted(os.path.basename(f) for f in found)
    assert names == ["eva-postcards.db", "treasurer.db"]


def test_find_db_files_skips_own_db(tmp_path):
    # Put the backup's own db inside the scanned modules tree.
    root = tmp_path / "modules"
    (root / "backup").mkdir(parents=True)
    own = root / "backup" / "eva-backup.db"
    store = Store(db_path=str(own))
    _make_modules_tree(str(root), {"postcards": ["eva-postcards.db"]})
    svc = _service(store, str(root), tmp_path)
    found = [os.path.basename(f) for f in svc.find_db_files()]
    assert "eva-backup.db" not in found
    assert "eva-postcards.db" in found


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def test_build_archive_contains_dbs(store, modules_root, tmp_path):
    svc = _service(store, modules_root, tmp_path)
    archive = svc.build_archive(svc.find_db_files())
    assert os.path.exists(archive)
    assert os.path.basename(archive).startswith(ARCHIVE_PREFIX)
    assert archive.endswith(".tar.gz")
    with tarfile.open(archive, "r:gz") as tar:
        members = sorted(tar.getnames())
    assert members == ["finance-tracker/treasurer.db", "postcards/eva-postcards.db"]


# ---------------------------------------------------------------------------
# Tick + upload params
# ---------------------------------------------------------------------------

def test_tick_uploads_with_correct_params(store, modules_root, tmp_path):
    drive = StubDriveClient()
    svc = _service(store, modules_root, tmp_path, drive=drive, folder_id="folder-XYZ")
    result = svc.tick()

    assert result["ok"] is True
    assert len(drive.uploaded) == 1
    up = drive.uploaded[0]
    assert up["folder_id"] == "folder-XYZ"
    assert up["name"].startswith(ARCHIVE_PREFIX)
    assert up["name"].endswith(".tar.gz")
    assert result["uploaded"]["id"] == up["id"]


def test_tick_logs_backup_ok_to_ledger_and_memory(store, modules_root, tmp_path):
    svc = _service(store, modules_root, tmp_path)
    svc.tick()

    ok_events = store.query_ledger(event_type="backup_ok")
    assert len(ok_events) == 1
    assert ok_events[0]["details"]["db_count"] == 2
    assert set(ok_events[0]["details"]["modules"]) == {"postcards", "finance-tracker"}

    assert store.recall("last_tick")
    assert store.recall("last_archive_id")
    assert store.recall("last_archive_name").startswith(ARCHIVE_PREFIX)


def test_tick_without_folder_is_error_and_no_upload(store, modules_root, tmp_path):
    drive = StubDriveClient()
    svc = _service(store, modules_root, tmp_path, drive=drive, folder_id="")
    result = svc.tick()
    assert result["ok"] is False
    assert "EVA_BACKUP_DRIVE_FOLDER_ID" in result["error"]
    assert drive.uploaded == []
    assert len(store.query_ledger(event_type="backup_error")) == 1


def test_tick_with_no_databases_is_ok_noop(store, tmp_path):
    empty_root = tmp_path / "modules"
    empty_root.mkdir()
    svc = _service(store, str(empty_root), tmp_path)
    result = svc.tick()
    assert result["ok"] is True
    assert result["uploaded"] is None
    # recorded as a (zero-db) backup_ok, not an error
    assert store.query_ledger(event_type="backup_ok")


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def test_retention_keeps_newest_n_and_deletes_older(store, modules_root, tmp_path):
    drive = StubDriveClient()
    svc = _service(store, modules_root, tmp_path, drive=drive,
                   folder_id="folder-123", retention=3)

    # Fire 5 ticks -> 5 archives uploaded, but only 3 should remain.
    for _ in range(5):
        svc.tick()

    remaining = [f for f in drive.list_files("folder-123")
                 if f["name"].startswith(ARCHIVE_PREFIX)]
    assert len(remaining) == 3
    # 5 uploaded, 2 deleted
    assert len(drive.uploaded) == 5
    assert len(drive.deleted) == 2
    # retention deletes were logged
    assert len(store.query_ledger(event_type="retention_delete")) == 2


def test_retention_only_touches_our_archives(store, modules_root, tmp_path):
    # Seed the folder with an unrelated file that must never be deleted.
    drive = StubDriveClient(files=[{
        "id": "keep-me", "name": "someone-elses-file.txt",
        "created_time": "2000-01-01T00:00:00+00:00", "folder_id": "folder-123",
    }])
    svc = _service(store, modules_root, tmp_path, drive=drive,
                   folder_id="folder-123", retention=1)
    for _ in range(3):
        svc.tick()

    assert "keep-me" not in drive.deleted
    names = {f["name"] for f in drive.list_files("folder-123")}
    assert "someone-elses-file.txt" in names


# ---------------------------------------------------------------------------
# Append-only ledger immutability
# ---------------------------------------------------------------------------

def test_ledger_is_append_only(store):
    row = store.append_ledger(event_type="backup_ok", actor="test")
    conn = sqlite3.connect(store.db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE backup_ledger SET actor='x' WHERE id=?", (row["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM backup_ledger WHERE id=?", (row["id"],))
    conn.close()
