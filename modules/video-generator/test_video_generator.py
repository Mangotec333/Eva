"""
EVA Video Generator — offline test suite.

Runs with ZERO outbound network calls: Stub renderer + Stub voice + Stub draft
client + Stub state ledger. The render test drives the full lifecycle end-to-end
and produces a real, playable MP4 via the locally-installed ffmpeg (ffmpeg makes
no network calls, so this stays offline-runnable).

Covers:
  * DB schema + append-only ledger immutability trigger
  * script segmentation
  * full draft -> storyboard -> approve -> render -> rendered lifecycle (real MP4)
  * approval gate (cannot render before approve)
  * content-engine draft-pull via the DraftClient Stub
  * memory table (Agent Intelligence Layer)

Run:  python -m pytest -q   (from modules/video-generator)
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import struct
import wave

try:
    import pytest
except ImportError:  # pragma: no cover - sandbox fallback when pytest is absent
    import _pytest_shim as pytest  # local shim so the suite runs without pytest

from database import Store
from draft_client import StubDraftClient
from ffmpeg_assembler import build_ffmpeg_args
from service import VideoGeneratorService, StateError, VideoGenError, segment_script
from state_client import StubStateLedgerClient
from voice import StubVoiceSynth, wav_duration_seconds

HAS_FFMPEG = shutil.which(os.environ.get("FFMPEG_PATH", "ffmpeg")) is not None


@pytest.fixture()
def store(tmp_path):
    return Store(db_path=str(tmp_path / "test.db"))


@pytest.fixture()
def svc(tmp_path, store):
    return VideoGeneratorService(
        store=store,
        output_dir=str(tmp_path / "out"),
        draft_client=StubDraftClient(),
        state_client=StubStateLedgerClient(),
        stub_media=True,
    )


# --------------------------------------------------------------------------- #
# DB schema + ledger immutability
# --------------------------------------------------------------------------- #

def test_schema_tables_exist(store):
    with sqlite3.connect(store.db_path) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"videos", "video_ledger", "memory"} <= names


def test_ledger_is_append_only(store):
    entry = store.append_ledger("created", entity_type="video", entity_id="v1")
    with sqlite3.connect(store.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE video_ledger SET event_type='x' WHERE id=?",
                         (entry["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM video_ledger WHERE id=?", (entry["id"],))


def test_memory_roundtrip(store):
    store.remember("k", "v1", source="test")
    assert store.recall("k") == "v1"
    store.remember("k", "v2", source="test")  # upsert
    assert store.recall("k") == "v2"
    assert store.all_memory()["k"] == "v2"


# --------------------------------------------------------------------------- #
# Segmentation + voice/ffmpeg unit behaviour
# --------------------------------------------------------------------------- #

def test_segment_script_splits_on_sentences():
    scenes = segment_script("One sentence. Two sentence. Three sentence four.")
    assert len(scenes) >= 1
    assert all(scenes)


def test_segment_empty_is_empty():
    assert segment_script("   ") == []


def test_stub_voice_writes_real_wav(tmp_path):
    out = str(tmp_path / "a.wav")
    StubVoiceSynth().synth("hello world this is a test", out)
    with wave.open(out, "rb") as wf:
        assert wf.getnframes() > 0
    assert wav_duration_seconds(out) > 1.0


def test_ffmpeg_args_interleave_inputs(tmp_path):
    scenes = []
    for i in range(2):
        img = str(tmp_path / f"s{i}.png")
        wav = str(tmp_path / f"s{i}.wav")
        open(img, "wb").close()
        with wave.open(wav, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
            wf.writeframes(struct.pack("<h", 0) * 44100)  # 2s
        scenes.append({"image": img, "audio": wav})
    args = build_ffmpeg_args(scenes, str(tmp_path / "o.mp4"))
    assert "-filter_complex" in args
    assert args.count("-loop") == 2      # one per scene image
    assert "[vout]" in " ".join(args) and "[aout]" in " ".join(args)


# --------------------------------------------------------------------------- #
# Draft-pull via content-engine Stub
# --------------------------------------------------------------------------- #

def test_draft_client_stub_hit_and_miss():
    client = StubDraftClient()
    client.add("d1", "This is the drafted script.", hook="A hook")
    ok = client.fetch_draft("d1")
    assert ok["ok"] and ok["script_text"] == "This is the drafted script."
    assert ok["title"] == "A hook"
    miss = client.fetch_draft("nope")
    assert miss["ok"] is False


def test_create_from_content_engine_draft(tmp_path, store):
    dc = StubDraftClient()
    dc.add("draft-42", "Founders waste time. Eva fixes that. Book a demo now.")
    s = VideoGeneratorService(store=store, output_dir=str(tmp_path / "out"),
                              draft_client=dc, state_client=StubStateLedgerClient(),
                              stub_media=True)
    video = s.create_video(content_engine_draft_id="draft-42", actor="test")
    assert video["content_engine_draft_id"] == "draft-42"
    assert "Eva fixes that" in video["script_text"]


def test_create_from_missing_draft_raises(svc):
    with pytest.raises(VideoGenError):
        svc.create_video(content_engine_draft_id="does-not-exist")


# --------------------------------------------------------------------------- #
# Lifecycle + approval gate
# --------------------------------------------------------------------------- #

def test_cannot_render_before_approve(svc):
    v = svc.create_video(title="T", script_text="One. Two. Three.")
    svc.storyboard(v["id"])
    with pytest.raises(StateError):
        svc.render(v["id"])


def test_approve_requires_storyboard(svc):
    v = svc.create_video(title="T", script_text="One. Two. Three.")
    with pytest.raises(StateError):
        svc.approve(v["id"])


def test_storyboard_produces_scenes_and_slides(svc):
    v = svc.create_video(title="T", script_text="Scene one here. Scene two here. Scene three.")
    out = svc.storyboard(v["id"])
    assert out["status"] == "storyboard_ready"
    assert len(out["scenes"]) >= 1
    for scene in out["scenes"]:
        assert os.path.exists(scene["image"])


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_full_lifecycle_produces_playable_mp4(svc):
    v = svc.create_video(
        title="Eva Demo",
        script_text=(
            "Founders lose hours every single week editing marketing videos by hand. "
            "Eva turns a plain text script into a finished vertical video automatically. "
            "There is no source footage to shoot, no editor to hire, and no studio to book. "
            "Your idea becomes a branded, captioned, narrated clip in minutes. "
            "Book a demo today and get your very first Eva video ready to post."),
    )
    assert v["status"] == "draft"

    v = svc.storyboard(v["id"])
    assert v["status"] == "storyboard_ready"
    n_scenes = len(v["scenes"])
    assert n_scenes >= 2

    v = svc.approve(v["id"])
    assert v["status"] == "approved"

    v = svc.render(v["id"])
    assert v["status"] == "rendered", v.get("error")
    assert os.path.exists(v["output_path"])
    assert os.path.getsize(v["output_path"]) > 1000

    # It is a real MP4 container.
    with open(v["output_path"], "rb") as fh:
        head = fh.read(12)
    assert b"ftyp" in head

    # Ledger recorded every transition for this video.
    events = {e["event_type"] for e in svc.ledger(v["id"])}
    assert {"created", "storyboard", "approved", "rendering", "rendered"} <= events


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_single_scene_renders(svc):
    v = svc.create_video(title="One", script_text="Just one short scene here.")
    svc.storyboard(v["id"])
    svc.approve(v["id"])
    out = svc.render(v["id"])
    assert out["status"] == "rendered", out.get("error")
    assert os.path.exists(out["output_path"])


def test_seed_is_idempotent(svc):
    first = svc.seed()
    assert first["created"] == 1
    second = svc.seed()
    assert second["created"] == 0


def test_list_filter_validation(svc):
    with pytest.raises(VideoGenError):
        svc.list_videos(status="bogus")


if __name__ == "__main__":  # standalone runner when real pytest is unavailable
    import sys
    if hasattr(pytest, "_run"):
        sys.exit(pytest._run(dict(globals())))
    sys.exit(pytest.main([__file__, "-q"]))
