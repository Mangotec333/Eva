"""
EVA Meet Ingest — service layer (all core logic lives here).

The REST API and the CLI both call this one place so their behavior is identical.
Pipeline: Google Meet auto-records a call to Drive -> ``poll()`` discovers new
recordings past a watermark -> ``process(id)`` downloads the file, extracts audio
(ffmpeg), transcribes locally (whisper.cpp), writes the transcript + a short
summary stub, and files them into ``EVA/Meetings/<name>/`` in Drive.

Design contract (Architecture Directive):
  * ``poll()``    — idempotent: safe to call repeatedly / from cron. New Drive
    recordings become ``pending`` meeting rows; already-seen files are skipped;
    the watermark advances so re-polls do not re-insert.
  * ``process(id)`` — never raises past this boundary: any step exception marks
    the meeting ``failed`` with the error captured. Otherwise ``done``.
  * ``tick()``    — cron-safe entrypoint: poll() then process() every pending row.

Agent Intelligence Layer: reads ``docs/MISSION.md`` and ``docs/CURRENT_GOALS.md``
at startup (graceful no-op if absent) and keeps per-agent memory (watermark,
last-run summary) in its own SQLite ``memory`` table.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from database import DB_PATH, WATERMARK_KEY, Store
from drive_client import DriveClient, build_drive_client
from transcriber import Transcriber, build_transcriber

# Where downloaded recordings + transcripts are staged locally.
DATA_DIR = os.environ.get(
    "EVA_MEET_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "data"),
)

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
    """Read a small text artifact, or "" if absent — never crash on missing."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def summarize(transcript: str, max_chars: int = 400) -> str:
    """A short, zero-cost summary stub (no LLM call, per Cost Discipline).

    v1: the leading sentences of the transcript, truncated. A real summarizer is
    future work; this keeps the pipeline free while giving a usable preview.
    """
    text = " ".join(transcript.split())
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    # Prefer to end on a sentence boundary if there is one nearby.
    dot = clipped.rfind(". ")
    if dot >= max_chars // 2:
        return clipped[: dot + 1]
    return clipped.rstrip() + "…"


class MeetIngestService:
    def __init__(
        self,
        store: Optional[Store] = None,
        drive: Optional[DriveClient] = None,
        transcriber: Optional[Transcriber] = None,
        data_dir: str = DATA_DIR,
    ):
        self.store = store or Store()
        self.drive = drive or build_drive_client()
        self.transcriber = transcriber or build_transcriber()
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self._load_alignment()

    # ------------------------------------------------------------------
    # Agent Intelligence Layer — mission + goals + memory
    # ------------------------------------------------------------------

    def _load_alignment(self) -> None:
        """Read the shared north-star docs at startup (graceful no-op if absent)."""
        self.mission = _read_if_present(MISSION_PATH)
        self.current_goals = _read_if_present(GOALS_PATH)

    def get_memory(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.store.get_memory_value(key, default)

    def set_memory(self, key: str, value: str, source: str = "system") -> dict:
        return self.store.set_memory(key, value, source=source)

    def list_memory(self) -> list[dict]:
        return self.store.list_memory()

    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------

    def list_meetings(self, status: Optional[str] = None) -> list[dict]:
        return self.store.list_meetings(status=status)

    def get_meeting(self, meeting_id: str) -> dict:
        m = self.store.get_meeting(meeting_id)
        if not m:
            raise NotFoundError(f"meeting {meeting_id!r} not found")
        return m

    # ------------------------------------------------------------------
    # poll — discover new recordings (idempotent)
    # ------------------------------------------------------------------

    def poll(self, actor: str = "system") -> dict:
        """Check Drive for recordings newer than the stored watermark and insert
        a ``pending`` meeting row for each new one. Idempotent: files already
        tracked (by drive_file_id) are skipped, and the watermark advances so a
        repeat poll does not re-insert."""
        watermark = self.get_memory(WATERMARK_KEY, "") or ""
        files = self.drive.list_new_recordings(watermark)

        created, skipped = [], []
        max_seen = watermark
        for f in files:
            created_time = f.get("created_time", "")
            if created_time > max_seen:
                max_seen = created_time
            existing = self.store.get_meeting_by_drive_file(f["id"])
            if existing:
                skipped.append(existing)
                continue
            meeting = self.store.insert_meeting({
                "drive_file_id": f["id"],
                "name": f.get("name", ""),
                "recorded_at": created_time,
                "status": "pending",
            })
            created.append(meeting)
            self.store.append_ledger(
                "created",
                entity_type="meeting",
                entity_id=meeting["id"],
                actor=actor,
                details={"drive_file_id": f["id"], "name": meeting["name"]},
            )

        if max_seen and max_seen != watermark:
            self.set_memory(WATERMARK_KEY, max_seen, source=actor)

        summary = {
            "polled_at": _now_iso(),
            "found": len(files),
            "created": len(created),
            "skipped": len(skipped),
            "watermark": max_seen,
        }
        self.set_memory("last_poll", _now_iso(), source=actor)
        return {**summary, "meetings": created}

    # ------------------------------------------------------------------
    # process — download -> extract -> transcribe -> upload
    # ------------------------------------------------------------------

    def process(self, meeting_id: str, actor: str = "system") -> dict:
        """Run the full pipeline for one meeting. Never raises past this
        boundary: any step failure marks the meeting ``failed`` and records the
        error. Idempotent-ish: a meeting already ``done`` is returned as-is."""
        meeting = self.get_meeting(meeting_id)
        if meeting["status"] == "done":
            return {"meeting": meeting, "reason": "already_done"}

        name = meeting["name"] or meeting["id"]
        meeting_dir = os.path.join(self.data_dir, meeting["id"])
        os.makedirs(meeting_dir, exist_ok=True)

        try:
            # 1. download
            self.store.update_meeting(meeting_id, {"status": "downloading", "error": ""})
            recording_path = os.path.join(meeting_dir, _safe_filename(name) or "recording")
            self.drive.download_file(meeting["drive_file_id"], recording_path)
            self.store.append_ledger(
                "downloaded", entity_type="meeting", entity_id=meeting_id,
                actor=actor, details={"path": recording_path},
            )

            # 2. extract audio + transcribe (local, zero API cost)
            self.store.update_meeting(meeting_id, {"status": "transcribing"})
            transcript = self.transcriber.transcribe(recording_path)
            transcript_path = os.path.join(meeting_dir, "transcript.txt")
            with open(transcript_path, "w", encoding="utf-8") as fh:
                fh.write(transcript)
            summary_text = summarize(transcript)
            summary_path = os.path.join(meeting_dir, "summary.txt")
            with open(summary_path, "w", encoding="utf-8") as fh:
                fh.write(summary_text)
            self.store.update_meeting(meeting_id, {"transcript_path": transcript_path})
            self.store.append_ledger(
                "transcribed", entity_type="meeting", entity_id=meeting_id,
                actor=actor,
                details={"transcript_path": transcript_path, "chars": len(transcript)},
            )

            # 3. file transcript + summary into Drive under EVA/Meetings/<name>/
            up = self.drive.upload_file(transcript_path, name, mime_type="text/plain")
            self.drive.upload_file(summary_path, name, mime_type="text/plain")
            self.store.update_meeting(
                meeting_id, {"status": "done", "drive_upload_id": up.get("id", "")}
            )
            self.store.append_ledger(
                "uploaded", entity_type="meeting", entity_id=meeting_id,
                actor=actor, details={"drive_upload_id": up.get("id", ""), "folder": up.get("folder", "")},
            )
            self.set_memory(
                f"meeting_summary:{meeting_id}", summary_text[:200], source=actor
            )
            return {"meeting": self.get_meeting(meeting_id), "reason": "done"}

        except Exception as exc:  # noqa: BLE001 — boundary: never raise past here
            error = f"{type(exc).__name__}: {exc}"
            updated = self.store.update_meeting(
                meeting_id, {"status": "failed", "error": error}
            )
            self.store.append_ledger(
                "failed", entity_type="meeting", entity_id=meeting_id,
                actor=actor, details={"error": error},
            )
            return {"meeting": updated, "reason": "failed", "error": error}

    # ------------------------------------------------------------------
    # tick — cron-safe: poll then process all pending
    # ------------------------------------------------------------------

    def tick(self, actor: str = "system") -> dict:
        """Poll for new recordings, then process every pending meeting. Safe to
        call repeatedly and from a cron."""
        poll_result = self.poll(actor=actor)
        processed = []
        for meeting in self.store.list_meetings(status="pending"):
            processed.append(self.process(meeting["id"], actor=actor))
        summary = {
            "ticked_at": _now_iso(),
            "polled": {k: poll_result[k] for k in ("found", "created", "skipped")},
            "processed": len(processed),
            "done": sum(1 for p in processed if p["reason"] == "done"),
            "failed": sum(1 for p in processed if p["reason"] == "failed"),
        }
        self.set_memory("last_tick", _now_iso(), source=actor)
        self.set_memory("last_run_summary", str(summary), source=actor)
        return {**summary, "results": processed}

    # ------------------------------------------------------------------
    # Status / ledger
    # ------------------------------------------------------------------

    def last_run(self) -> dict:
        return {
            "last_poll": self.get_memory("last_poll", ""),
            "last_tick": self.get_memory("last_tick", ""),
            "watermark": self.get_memory(WATERMARK_KEY, ""),
            "last_run_summary": self.get_memory("last_run_summary", ""),
        }

    def query_ledger(self, from_ts=None, to_ts=None, event_type=None) -> list[dict]:
        return self.store.query_ledger(from_ts=from_ts, to_ts=to_ts, event_type=event_type)

    @property
    def db_path(self) -> str:
        return getattr(self.store, "db_path", DB_PATH)


def _safe_filename(name: str) -> str:
    """Make a Drive filename safe for the local filesystem."""
    keep = "-_. ()[]"
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return cleaned
