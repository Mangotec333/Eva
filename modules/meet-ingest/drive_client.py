"""
EVA Meet Ingest — Google Drive transport (the single network chokepoint).

Per the Architecture Directive (rules #2/#3): all Drive I/O lives behind a
``DriveClient`` Protocol with a ``StubDriveClient`` (offline, canned data — used
in tests, no network) and a ``RealDriveClient`` (the actual googleapiclient
calls). This is the *only* place real Drive network code lives.

The OAuth helper is duplicated locally on purpose — we do NOT import
``modules/drive_organizer/drive_organizer.py`` (that would reach into a sibling
module's internals, violating rule #2). The small helper mirrors its
token/creds/scope conventions:
  * token  : ~/.eva/drive_token.pickle
  * creds  : ~/.eva/drive_credentials.json
  * scope  : https://www.googleapis.com/auth/drive

Contract shared by both implementations:
  * ``list_new_recordings(watermark)`` -> list[dict] of files in Google's
    default "Meet Recordings" folder created after ``watermark`` (RFC3339 or "").
    Each dict: {"id", "name", "created_time", "mime_type"}.
  * ``download_file(file_id, dest_path)`` -> local path written.
  * ``upload_file(local_path, meeting_name, ...)`` -> {"id", "name", "folder"}.
    Uploads into ``EVA/Meetings/<meeting-name>/``.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

# Drive OAuth conventions (mirrors drive_organizer.py, duplicated per rule #2/#3).
SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = os.path.expanduser("~/.eva/drive_token.pickle")
CREDS_PATH = os.path.expanduser("~/.eva/drive_credentials.json")

# Google names the auto-recording destination folder "Meet Recordings".
MEET_RECORDINGS_FOLDER = "Meet Recordings"
# Where transcripts + recordings are filed.
MEETINGS_ROOT = "EVA/Meetings"


class DriveError(RuntimeError):
    """Raised when a Drive operation cannot be performed."""


@runtime_checkable
class DriveClient(Protocol):
    """Transport interface for Google Drive. Implementations must not fake
    success: an unwired transport raises ``DriveError`` with a clear message."""

    name: str

    def list_new_recordings(self, watermark: str = "") -> list[dict]: ...

    def download_file(self, file_id: str, dest_path: str) -> str: ...

    def upload_file(
        self, local_path: str, meeting_name: str, mime_type: str = "text/plain"
    ) -> dict: ...


# ---------------------------------------------------------------------------
# Stub (offline, canned) — used in tests. No network.
# ---------------------------------------------------------------------------

class StubDriveClient:
    """Offline DriveClient with a canned recording list.

    Returns a fixed set of "Meet Recordings" newer than the watermark, writes a
    placeholder file on download, and records uploads in an in-memory sink so
    tests can inspect what *would* have been filed into Drive. Never touches the
    network.
    """

    name = "stub"

    def __init__(self, files: Optional[list[dict]] = None):
        # Canned recordings. created_time is RFC3339 so watermark filtering works.
        self.files: list[dict] = files if files is not None else [
            {
                "id": "stub-file-001",
                "name": "Weekly Sync 2026-07-15.mp4",
                "created_time": "2026-07-15T18:03:00.000Z",
                "mime_type": "video/mp4",
            },
            {
                "id": "stub-file-002",
                "name": "Investor Update 2026-07-16.mp4",
                "created_time": "2026-07-16T21:30:00.000Z",
                "mime_type": "video/mp4",
            },
        ]
        self.uploaded: list[dict] = []

    def list_new_recordings(self, watermark: str = "") -> list[dict]:
        if not watermark:
            return list(self.files)
        return [f for f in self.files if f["created_time"] > watermark]

    def download_file(self, file_id: str, dest_path: str) -> str:
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        # Write a small placeholder standing in for the downloaded recording.
        with open(dest_path, "wb") as fh:
            fh.write(b"stub-recording-bytes")
        return dest_path

    def upload_file(
        self, local_path: str, meeting_name: str, mime_type: str = "text/plain"
    ) -> dict:
        folder = f"{MEETINGS_ROOT}/{meeting_name}"
        record = {
            "id": f"stub-upload-{len(self.uploaded) + 1:03d}",
            "name": os.path.basename(local_path),
            "folder": folder,
        }
        self.uploaded.append({**record, "local_path": local_path})
        return record


# ---------------------------------------------------------------------------
# Real (googleapiclient) — the only place real Drive network code lives.
# ---------------------------------------------------------------------------

class RealDriveClient:
    """Live Google Drive client. Requires Drive OAuth credentials at
    ``~/.eva/drive_credentials.json`` (first run opens a browser consent flow and
    caches a token at ``~/.eva/drive_token.pickle``). Raises ``DriveError`` with
    a clear message if credentials are missing — never silently stubbed."""

    name = "drive"

    def __init__(self, token_path: str = TOKEN_PATH, creds_path: str = CREDS_PATH):
        self.token_path = token_path
        self.creds_path = creds_path
        self._service = None

    # -- OAuth helper (duplicated locally per rule #2/#3) -------------------

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
                        "Download an OAuth client_secret.json from Google Cloud "
                        "and save it there before using the real Drive transport."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, "wb") as fh:
                pickle.dump(creds, fh)
        self._service = build("drive", "v3", credentials=creds)
        return self._service

    def _find_folder_id(self, service, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        q = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        )
        if parent_id:
            q += f" and '{parent_id}' in parents"
        res = service.files().list(q=q, fields="files(id)").execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def _get_or_create_folder(self, service, path: str) -> str:
        """Create nested path like EVA/Meetings/<name>. Returns final folder ID.
        Mirrors drive_organizer.get_or_create_folder (duplicated per rule #2)."""
        parent_id = None
        for part in path.split("/"):
            found = self._find_folder_id(service, part, parent_id)
            if found:
                parent_id = found
            else:
                meta = {"name": part, "mimeType": "application/vnd.google-apps.folder"}
                if parent_id:
                    meta["parents"] = [parent_id]
                folder = service.files().create(body=meta, fields="id").execute()
                parent_id = folder["id"]
        return parent_id

    # -- contract ----------------------------------------------------------

    def list_new_recordings(self, watermark: str = "") -> list[dict]:
        service = self._get_service()
        folder_id = self._find_folder_id(service, MEET_RECORDINGS_FOLDER)
        if not folder_id:
            # No auto-recording folder yet — nothing to ingest.
            return []
        q = f"'{folder_id}' in parents and trashed=false"
        if watermark:
            q += f" and createdTime > '{watermark}'"
        res = service.files().list(
            q=q,
            fields="files(id, name, createdTime, mimeType)",
            orderBy="createdTime",
            pageSize=100,
        ).execute()
        out = []
        for f in res.get("files", []):
            out.append({
                "id": f["id"],
                "name": f.get("name", ""),
                "created_time": f.get("createdTime", ""),
                "mime_type": f.get("mimeType", ""),
            })
        return out

    def download_file(self, file_id: str, dest_path: str) -> str:
        from googleapiclient.http import MediaIoBaseDownload

        service = self._get_service()
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        request = service.files().get_media(fileId=file_id)
        with open(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return dest_path

    def upload_file(
        self, local_path: str, meeting_name: str, mime_type: str = "text/plain"
    ) -> dict:
        from googleapiclient.http import MediaFileUpload

        service = self._get_service()
        folder = f"{MEETINGS_ROOT}/{meeting_name}"
        folder_id = self._get_or_create_folder(service, folder)
        meta = {"name": os.path.basename(local_path), "parents": [folder_id]}
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=False)
        created = service.files().create(
            body=meta, media_body=media, fields="id, name"
        ).execute()
        return {"id": created["id"], "name": created.get("name", ""), "folder": folder}


def build_drive_client(name: Optional[str] = None) -> DriveClient:
    """Factory. Defaults to the stub unless EVA_MEET_DRIVE=real."""
    choice = (name or os.environ.get("EVA_MEET_DRIVE", "stub")).lower()
    if choice == "real":
        return RealDriveClient()
    return StubDriveClient()
