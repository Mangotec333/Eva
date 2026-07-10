"""Eva Master Index writer — append agent outputs to the KB index (shared).

This is the one shared piece both new governed agents (monetizing-agent,
book-agent) need: an automated hook that appends a titled link/summary row to
the **Eva Master Index** Google Doc, mirroring ``drive_organizer.py``'s auth
(``~/.eva/drive_token.pickle``). Before this, agent→INDEX was a manual step.

Design (matches the module standard's transport-behind-a-Protocol rule):

- ``IndexTransport`` is a Protocol. ``StubIndexTransport`` is the offline
  implementation used in tests — it records rows in memory and never touches the
  network (and never fakes a real Docs write). ``GoogleDocsIndexTransport`` is
  the real implementation that calls the Google Docs API ``batchUpdate`` to
  insert a row at the top of the Master Index doc.
- ``append_to_index(title, summary, url)`` is the thin, FastAPI-free callable any
  agent module imports. It resolves a transport (real when Google creds are
  present, Stub otherwise) and appends one row.

The row format written to the doc is a single line::

    • <ISO-date> — <title>: <summary> (<url>)

Kept dependency-light: the real transport imports googleapiclient lazily so
importing this module offline (no google libs installed) never fails.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

# The Master Index Google Doc (see EVA_DEVELOPMENT_BACKLOG.md).
MASTER_INDEX_DOC_ID = "16T3kyMmvCuxpeGFVmVo48VHm_6O6FCM2CgIquKRR4X0"
MASTER_INDEX_URL = f"https://docs.google.com/document/d/{MASTER_INDEX_DOC_ID}/edit"

# Auth mirrors drive_organizer.py exactly.
TOKEN_PATH = os.path.expanduser("~/.eva/drive_token.pickle")
CREDS_PATH = os.path.expanduser("~/.eva/drive_credentials.json")
DOCS_SCOPES = ["https://www.googleapis.com/auth/documents"]


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def format_row(title: str, summary: str, url: str, *, when: Optional[str] = None) -> str:
    """Render a single index row line (the exact text inserted into the doc)."""
    date = when or _now_date()
    summary = (summary or "").strip().replace("\n", " ")
    line = f"• {date} — {title.strip()}: {summary}"
    if url:
        line += f" ({url.strip()})"
    return line + "\n"


# ---------------------------------------------------------------------------
# Transport seam
# ---------------------------------------------------------------------------

@runtime_checkable
class IndexTransport(Protocol):
    """Swap-and-play seam for writing a row into the Master Index doc."""

    def append_row(self, row: str) -> dict[str, Any]:
        """Append ``row`` to the index. Returns ``{ok: bool, ...}``.

        Must NEVER raise to the caller and must NEVER fake success — an
        unwired/failed transport returns ``ok=False`` with a clear ``error``.
        """


class StubIndexTransport:
    """Offline transport: records rows in memory, no network (used in tests).

    Honest about being a stub: results carry ``stub=True`` so callers/tests can
    assert the write was simulated, not real.
    """

    def __init__(self) -> None:
        self.rows: list[str] = []

    def append_row(self, row: str) -> dict[str, Any]:
        self.rows.append(row)
        return {"ok": True, "stub": True, "row": row, "count": len(self.rows)}


class GoogleDocsIndexTransport:
    """Real transport: inserts a row at the top of the Master Index via Docs API.

    Auth mirrors ``drive_organizer.py`` (``~/.eva/drive_token.pickle``). Google
    client libraries are imported lazily so this module stays importable offline.
    All failures are caught and returned as ``ok=False`` envelopes.
    """

    def __init__(
        self,
        document_id: str = MASTER_INDEX_DOC_ID,
        *,
        token_path: str = TOKEN_PATH,
        creds_path: str = CREDS_PATH,
    ) -> None:
        self.document_id = document_id
        self.token_path = token_path
        self.creds_path = creds_path
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        import pickle  # lazy

        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, "rb") as fh:
                creds = pickle.load(fh)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_path, DOCS_SCOPES)
                creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, "wb") as fh:
                pickle.dump(creds, fh)
        self._service = build("docs", "v1", credentials=creds)
        return self._service

    def append_row(self, row: str) -> dict[str, Any]:
        try:
            service = self._get_service()
            # Insert just after the document body start (index 1) so the newest
            # row lands at the top of the index.
            requests = [
                {"insertText": {"location": {"index": 1}, "text": row}}
            ]
            result = (
                service.documents()
                .batchUpdate(documentId=self.document_id, body={"requests": requests})
                .execute()
            )
            return {"ok": True, "stub": False, "row": row, "document_id": self.document_id,
                    "reply": result.get("replies", [])}
        except Exception as exc:  # noqa: BLE001 — transport never raises to caller
            return {"ok": False, "stub": False, "error": f"{type(exc).__name__}: {exc}"}


def make_index_transport(document_id: str = MASTER_INDEX_DOC_ID) -> IndexTransport:
    """Return the real transport when Google creds/libs are present, else Stub.

    Never raises: any import or credential problem degrades to the offline Stub
    so agents in the sandbox keep working.
    """
    if not (os.path.exists(TOKEN_PATH) or os.path.exists(CREDS_PATH)):
        return StubIndexTransport()
    try:  # only take the real path if the google libs are actually importable
        import googleapiclient.discovery  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
    except ImportError:
        return StubIndexTransport()
    return GoogleDocsIndexTransport(document_id)


# ---------------------------------------------------------------------------
# The one callable agents import
# ---------------------------------------------------------------------------

class IndexWriter:
    """Thin wrapper binding a transport to the append operation."""

    def __init__(self, transport: Optional[IndexTransport] = None) -> None:
        self.transport = transport or make_index_transport()

    def append(self, title: str, summary: str, url: str,
               *, when: Optional[str] = None) -> dict[str, Any]:
        return self.transport.append_row(format_row(title, summary, url, when=when))


def append_to_index(
    title: str,
    summary: str,
    url: str = "",
    *,
    transport: Optional[IndexTransport] = None,
    when: Optional[str] = None,
) -> dict[str, Any]:
    """Append one titled link/summary row to the Eva Master Index doc.

    Importable by any agent module. Pass ``transport`` to inject a Stub in tests;
    otherwise a transport is auto-resolved (real when creds exist, else Stub).
    """
    return IndexWriter(transport).append(title, summary, url, when=when)


__all__ = [
    "MASTER_INDEX_DOC_ID",
    "MASTER_INDEX_URL",
    "IndexTransport",
    "StubIndexTransport",
    "GoogleDocsIndexTransport",
    "IndexWriter",
    "make_index_transport",
    "append_to_index",
    "format_row",
]
