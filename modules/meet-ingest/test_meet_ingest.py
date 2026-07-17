"""
Offline test suite for the EVA Meet Ingest module (Architecture Directive rule
#7). No network, no ffmpeg, no real whisper.cpp — every test uses the Stub
transports. Runs with ``python -m pytest`` from this directory.

Each test builds a fresh service backed by a throwaway SQLite file, a scratch
data dir, a ``StubDriveClient`` and a ``StubTranscriber``, so runs are isolated.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from database import Store, WATERMARK_KEY
from drive_client import StubDriveClient
from service import MeetIngestService, summarize
from transcriber import StubTranscriber


def _fresh_service(files=None, transcript=None):
    fd, path = tempfile.mkstemp(suffix=".db", prefix="eva-meet-test-")
    os.close(fd)
    os.unlink(path)  # let sqlite create it fresh
    data_dir = tempfile.mkdtemp(prefix="eva-meet-data-")
    drive = StubDriveClient(files=files)
    transcriber = StubTranscriber(text=transcript)
    svc = MeetIngestService(
        store=Store(path), drive=drive, transcriber=transcriber, data_dir=data_dir
    )
    return svc, drive, transcriber


# ---------------------------------------------------------------------------
# poll
# ---------------------------------------------------------------------------

def test_poll_inserts_pending_meetings():
    svc, drive, _ = _fresh_service()
    result = svc.poll()
    assert result["found"] == len(drive.files)
    assert result["created"] == len(drive.files)
    assert result["skipped"] == 0
    meetings = svc.list_meetings()
    assert len(meetings) == len(drive.files)
    assert all(m["status"] == "pending" for m in meetings)


def test_poll_is_idempotent():
    svc, drive, _ = _fresh_service()
    first = svc.poll()
    assert first["created"] == len(drive.files)
    # Second poll: watermark advanced, nothing new returned -> no dup inserts.
    second = svc.poll()
    assert second["created"] == 0
    assert len(svc.list_meetings()) == len(drive.files)


def test_poll_advances_watermark():
    svc, drive, _ = _fresh_service()
    svc.poll()
    wm = svc.get_memory(WATERMARK_KEY)
    newest = max(f["created_time"] for f in drive.files)
    assert wm == newest


def test_poll_respects_watermark_for_new_files():
    svc, drive, _ = _fresh_service()
    svc.poll()
    # A brand-new recording arrives after the watermark.
    drive.files.append({
        "id": "stub-file-003",
        "name": "New Call 2026-07-20.mp4",
        "created_time": "2026-07-20T10:00:00.000Z",
        "mime_type": "video/mp4",
    })
    result = svc.poll()
    assert result["created"] == 1


# ---------------------------------------------------------------------------
# process
# ---------------------------------------------------------------------------

def test_process_full_pipeline():
    svc, drive, _ = _fresh_service(transcript="Hello team, quick standup.")
    svc.poll()
    meeting = svc.list_meetings(status="pending")[0]
    result = svc.process(meeting["id"])
    assert result["reason"] == "done"
    done = svc.get_meeting(meeting["id"])
    assert done["status"] == "done"
    assert done["transcript_path"]
    assert os.path.exists(done["transcript_path"])
    with open(done["transcript_path"]) as fh:
        assert "standup" in fh.read()
    # Transcript + summary were filed into Drive under EVA/Meetings/<name>/.
    assert len(drive.uploaded) == 2
    assert all(u["folder"].startswith("EVA/Meetings/") for u in drive.uploaded)


def test_process_marks_failed_on_transcription_error(monkeypatch):
    svc, _, transcriber = _fresh_service()
    svc.poll()
    meeting = svc.list_meetings(status="pending")[0]

    def boom(_video_path):
        raise RuntimeError("whisper exploded")

    monkeypatch.setattr(transcriber, "transcribe", boom)
    result = svc.process(meeting["id"])
    assert result["reason"] == "failed"
    assert "whisper exploded" in result["error"]
    failed = svc.get_meeting(meeting["id"])
    assert failed["status"] == "failed"
    assert "whisper exploded" in failed["error"]


def test_process_already_done_is_noop():
    svc, _, _ = _fresh_service()
    svc.poll()
    meeting = svc.list_meetings(status="pending")[0]
    svc.process(meeting["id"])
    again = svc.process(meeting["id"])
    assert again["reason"] == "already_done"


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------

def test_tick_polls_then_processes_all():
    svc, drive, _ = _fresh_service()
    result = svc.tick()
    assert result["polled"]["created"] == len(drive.files)
    assert result["processed"] == len(drive.files)
    assert result["done"] == len(drive.files)
    assert result["failed"] == 0
    assert all(m["status"] == "done" for m in svc.list_meetings())


def test_tick_is_idempotent():
    svc, drive, _ = _fresh_service()
    svc.tick()
    # A second tick finds nothing new and re-processes nothing (all done).
    second = svc.tick()
    assert second["polled"]["created"] == 0
    assert second["processed"] == 0


# ---------------------------------------------------------------------------
# ledger (append-only)
# ---------------------------------------------------------------------------

def test_ledger_records_lifecycle_events():
    svc, _, _ = _fresh_service()
    svc.tick()
    events = {e["event_type"] for e in svc.query_ledger()}
    assert {"created", "downloaded", "transcribed", "uploaded"} <= events


def test_ledger_is_append_only():
    svc, _, _ = _fresh_service()
    svc.poll()
    rows = svc.query_ledger()
    assert rows
    store = svc.store
    with store._connect() as conn:
        with pytest.raises(Exception):
            conn.execute("UPDATE ledger SET actor='x' WHERE id=?", (rows[0]["id"],))
        with pytest.raises(Exception):
            conn.execute("DELETE FROM ledger WHERE id=?", (rows[0]["id"],))


# ---------------------------------------------------------------------------
# memory + summary
# ---------------------------------------------------------------------------

def test_memory_roundtrip():
    svc, _, _ = _fresh_service()
    svc.set_memory("k", "v", source="test")
    assert svc.get_memory("k") == "v"
    assert svc.get_memory("missing", "fallback") == "fallback"


def test_missing_mission_and_goals_is_graceful():
    # Constructing the service reads MISSION.md / CURRENT_GOALS.md if present and
    # must not crash when they are absent.
    svc, _, _ = _fresh_service()
    assert isinstance(svc.mission, str)
    assert isinstance(svc.current_goals, str)


def test_summarize_truncates():
    long = "Sentence one. " + ("word " * 500)
    out = summarize(long, max_chars=100)
    assert len(out) <= 101
    assert summarize("") == ""
