"""
EVA Backup — Google Drive transport (the single network chokepoint).

Follows the same Protocol + Stub + Real shape as
``modules/meet-ingest/drive_client.py``: all Drive I/O lives behind a
``DriveClient`` Protocol with a ``StubDriveClient`` (offline, in-memory — used in
tests, no network) and a ``RealDriveClient`` (the actual googleapiclient calls).
This is the *only* place real Drive network code lives.

Per the repo's no-shared-runtime-state rule, the small OAuth helper is duplicated
locally rather than imported from ``drive_organizer.py`` or ``meet-ingest`` — but
the conventions are identical:
  * token  : ~/.eva/drive_token.pickle
  * creds  : ~/.eva/drive_credentials.json
  * scope  : https://www.googleapis.com/auth/drive

Contract shared by both implementations (backup-specific):
  * ``upload_file(local_path, folder_id, name=None)`` -> {"id", "name"}.
    Uploads an archive into the configured Drive folder.
  * ``list_files(folder_id)`` -> list[dict] of files in the folder, each
    {"id", "name", "created_time"}, newest first — used for retention.
  * ``delete_file(file_id)`` -> None. Removes an archive past the retention
    window.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

# Drive OAuth conventions (identical to meet-ingest / drive_organizer.py).
SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = os.path.expanduser("~/.eva/drive_token.pickle")
CREDS_PATH = os.path.expanduser("~/.eva/drive_credentials.json")

# Archives are stored as gzipped tarballs.
ARCHIVE_MIME = "application/gzip"


class DriveError(RuntimeError):
    """Raised when a Drive operation cannot be performed."""


@runtime_checkable
class DriveClient(Protocol):
    """Transport interface for Google Drive. Implementations must not fake
    success: an unwired transport raises ``DriveError`` with a clear message."""

    name: str

    def upload_file(
        self, local_path: str, folder_id: str, name: Optional[str] = None
    ) -> dict: ...

    def list_files(self, folder_id: str) -> list[dict]: ...

    def delete_file(self, file_id: str) -> None: ...


# ---------------------------------------------------------------------------
# Stub (offline, in-memory) — used in tests. No network.
# ---------------------------------------------------------------------------

class StubDriveClient:
    """Offline DriveClient backed by an in-memory dict.

    Records uploads/deletes so tests can assert the archive was uploaded with the
    right params and that retention deletes the correct (oldest) files. Never
    touches the network.
    """

    name = "stub"

    def __init__(self, files: Optional[list[dict]] = None):
        # Each entry: {"id", "name", "created_time", "folder_id", "local_path"}.
        self._files: list[dict] = list(files) if files else []
        self._counter = len(self._files)
        # Audit trails for assertions.
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []

    def upload_file(
        self, local_path: str, folder_id: str, name: Optional[str] = None
    ) -> dict:
        self._counter += 1
        from datetime import datetime, timezone
        record = {
            "id": f"stub-file-{self._counter:04d}",
            "name": name or os.path.basename(local_path),
            "created_time": datetime.now(timezone.utc).isoformat(),
            "folder_id": folder_id,
            "local_path": local_path,
        }
        self._files.append(record)
        self.uploaded.append(record)
        return {"id": record["id"], "name": record["name"]}

    def list_files(self, folder_id: str) -> list[dict]:
        rows = [
            {"id": f["id"], "name": f["name"], "created_time": f["created_time"]}
            for f in self._files
            if f.get("folder_id") == folder_id
        ]
        # Newest first (matches RealDriveClient's orderBy createdTime desc).
        return sorted(rows, key=lambda r: r["created_time"], reverse=True)

    def delete_file(self, file_id: str) -> None:
        self._files = [f for f in self._files if f["id"] != file_id]
        self.deleted.append(file_id)


# ---------------------------------------------------------------------------
# Real (googleapiclient) — the only place real Drive network code lives.
# ---------------------------------------------------------------------------

class RealDriveClient:
    """Live Google Drive client. Requires Drive OAuth credentials at
    ``~/.eva/drive_credentials.json`` (the SAME file meet-ingest uses). First run
    opens a browser consent flow and caches a token at
    ``~/.eva/drive_token.pickle``. Raises ``DriveError`` with a clear message if
    credentials are missing — never silently stubbed."""

    name = "drive"

    def __init__(self, token_path: str = TOKEN_PATH, creds_path: str = CREDS_PATH):
        self.token_path = token_path
        self.creds_path = creds_path
        self._service = None

    # -- OAuth helper (duplicated locally per no-shared-runtime-state rule) --

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            import pickle

            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - requires google libs
            raise DriveError(
                "google-api-python-client / google-auth-oauthlib not installed. "
                "Run setup.sh (pip install -r requirements.txt)."
            ) from exc

        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, "rb") as fh:
                creds = pickle.load(fh)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.creds_path):
                    raise DriveError(
                        f"Drive OAuth credentials not found at {self.creds_path}. "
                        "Download an OAuth client_secret.json from Google Cloud and "
                        "save it there (the same file meet-ingest uses)."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, "wb") as fh:
                pickle.dump(creds, fh)
        self._service = build("drive", "v3", credentials=creds)
        return self._service

    # -- contract ----------------------------------------------------------

    def upload_file(
        self, local_path: str, folder_id: str, name: Optional[str] = None
    ) -> dict:
        from googleapiclient.http import MediaFileUpload

        if not folder_id:
            raise DriveError(
                "no Drive folder configured — set EVA_BACKUP_DRIVE_FOLDER_ID."
            )
        service = self._get_service()
        meta = {"name": name or os.path.basename(local_path), "parents": [folder_id]}
        media = MediaFileUpload(local_path, mimetype=ARCHIVE_MIME, resumable=False)
        created = service.files().create(
            body=meta, media_body=media, fields="id, name"
        ).execute()
        return {"id": created["id"], "name": created.get("name", "")}

    def list_files(self, folder_id: str) -> list[dict]:
        if not folder_id:
            raise DriveError(
                "no Drive folder configured — set EVA_BACKUP_DRIVE_FOLDER_ID."
            )
        service = self._get_service()
        q = f"'{folder_id}' in parents and trashed=false"
        res = service.files().list(
            q=q,
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc",
            pageSize=1000,
        ).execute()
        out = []
        for f in res.get("files", []):
            out.append({
                "id": f["id"],
                "name": f.get("name", ""),
                "created_time": f.get("createdTime", ""),
            })
        return out

    def delete_file(self, file_id: str) -> None:
        service = self._get_service()
        service.files().delete(fileId=file_id).execute()


def build_drive_client(name: Optional[str] = None) -> DriveClient:
    """Factory. Defaults to the stub unless EVA_BACKUP_DRIVE=real."""
    choice = (name or os.environ.get("EVA_BACKUP_DRIVE", "stub")).lower()
    if choice == "real":
        return RealDriveClient()
    return StubDriveClient()
