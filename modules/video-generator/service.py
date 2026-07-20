"""
EVA Video Generator — pipeline orchestration.

Ties the seams together into the module's state machine:

    draft -> storyboard_ready -> approved -> rendering -> rendered | failed

* ``create_video``    — capture a script (typed, or pulled from a content-engine
                        draft via the DraftClient Protocol). status=draft.
* ``storyboard``      — segment the script into scenes and render a branded
                        Pillow slide per scene. status=storyboard_ready.
* ``approve``         — the cost-discipline human gate BEFORE render compute is
                        spent. status=approved. (Only approved videos render.)
* ``render``          — synth a voiceover per scene, then the ffmpeg chokepoint
                        composites slides + audio (Ken Burns, captions, branded
                        lower-third, crossfades, loudnorm) into one MP4.

Every transition is written to the append-only ``video_ledger`` and emitted to
the Eva State Ledger. All transport (visuals, voice, draft pull, ledger) is
behind a Protocol so the whole pipeline runs offline with Stubs in tests.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from database import VALID_STATUSES, Store, read_mission_and_goals
from draft_client import DraftClient, build_draft_client
from ffmpeg_assembler import assemble
from renderer import build_renderer
from state_client import build_state_client
from voice import build_voice

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.environ.get("VIDEO_GEN_OUTPUT_DIR", os.path.join(MODULE_DIR, "out"))

MAX_SCENE_CHARS = 180
MAX_SCENES = 12


class VideoGenError(Exception):
    pass


class NotFoundError(VideoGenError):
    pass


class StateError(VideoGenError):
    """Raised on an illegal state transition (e.g. render before approve)."""


def segment_script(script: str, max_chars: int = MAX_SCENE_CHARS,
                   max_scenes: int = MAX_SCENES) -> list[str]:
    """Split a script into scene-sized chunks on sentence boundaries."""
    text = " ".join((script or "").split())
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scenes: list[str] = []
    cur = ""
    for sent in sentences:
        if not sent:
            continue
        if not cur:
            cur = sent
        elif len(cur) + 1 + len(sent) <= max_chars:
            cur = f"{cur} {sent}"
        else:
            scenes.append(cur)
            cur = sent
    if cur:
        scenes.append(cur)
    # Very long single sentences: hard-wrap so no scene is unreadable.
    wrapped: list[str] = []
    for s in scenes:
        while len(s) > max_chars * 1.5:
            cut = s.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            wrapped.append(s[:cut].strip())
            s = s[cut:].strip()
        wrapped.append(s)
    return wrapped[:max_scenes]


class VideoGeneratorService:
    def __init__(
        self,
        store: Optional[Store] = None,
        *,
        offline: Optional[bool] = None,
        output_dir: str = OUTPUT_DIR,
        draft_client: Optional[DraftClient] = None,
        state_client=None,
        stub_media: Optional[bool] = None,
    ) -> None:
        self.store = store or Store()
        self.output_dir = output_dir
        self.draft_client = draft_client or build_draft_client(offline=offline)
        self.state = state_client or build_state_client(offline=offline)
        # stub_media forces Stub renderer/voice (tests); default follows offline.
        self.stub_media = bool(stub_media) if stub_media is not None else False
        os.makedirs(self.output_dir, exist_ok=True)
        # Agent Intelligence Layer: read north-star docs once at construction.
        self._context = read_mission_and_goals()

    # -- emit helper --------------------------------------------------------

    def _record(self, event_type: str, video: dict, actor: str, summary: str = "",
                details: Optional[dict] = None) -> None:
        payload = details or {"status": video.get("status")}
        self.store.append_ledger(
            event_type=event_type, entity_type="video",
            entity_id=video["id"], actor=actor, details=payload,
        )
        try:
            self.state.emit(
                event_type=f"video.{event_type}",
                summary=summary or f"video {video['id']} -> {video.get('status')}",
                entity_id=video["id"], payload=payload,
            )
        except Exception:
            pass

    # -- create -------------------------------------------------------------

    def create_video(self, title: Optional[str] = None, script_text: Optional[str] = None,
                     content_engine_draft_id: Optional[str] = None,
                     actor: str = "system") -> dict:
        draft_id = None
        if content_engine_draft_id:
            res = self.draft_client.fetch_draft(content_engine_draft_id)
            if not res.get("ok"):
                raise VideoGenError(
                    f"could not pull content-engine draft "
                    f"{content_engine_draft_id}: {res.get('error')}"
                )
            draft_id = content_engine_draft_id
            title = title or res.get("title")
            script_text = script_text or res.get("script_text")
        if not (title and (script_text or "").strip()):
            raise VideoGenError("title and script_text (or a valid draft_id) are required")

        video = self.store.insert_video({
            "title": title,
            "script_text": script_text,
            "content_engine_draft_id": draft_id,
            "status": "draft",
        })
        self._record("created", video, actor,
                     summary=f"video draft captured: {title}",
                     details={"status": "draft", "draft_id": draft_id})
        return video

    # -- storyboard ---------------------------------------------------------

    def storyboard(self, video_id: str, actor: str = "system") -> dict:
        video = self._require(video_id)
        segments = segment_script(video["script_text"])
        if not segments:
            raise VideoGenError("script produced no scenes")

        scene_dir = os.path.join(self.output_dir, video_id, "scenes")
        renderer = build_renderer(scene_dir, stub=self.stub_media)
        scenes = []
        for i, text in enumerate(segments):
            image_path = renderer.render(text, i)
            scenes.append({"index": i, "text": text, "image": image_path})

        video = self.store.update_video(video_id, {
            "scenes": scenes, "status": "storyboard_ready", "error": "",
        })
        self._record("storyboard", video, actor,
                     summary=f"{len(scenes)} scenes storyboarded",
                     details={"status": "storyboard_ready", "scene_count": len(scenes)})
        self.store.remember(f"last_storyboard:{video_id}", str(len(scenes)), source="storyboard")
        return video

    # -- approve (the cost-discipline gate) ---------------------------------

    def approve(self, video_id: str, actor: str = "human") -> dict:
        video = self._require(video_id)
        if video["status"] not in ("storyboard_ready", "failed"):
            raise StateError(
                f"can only approve a storyboard_ready video (is '{video['status']}')"
            )
        video = self.store.update_video(video_id, {"status": "approved", "error": ""})
        self._record("approved", video, actor,
                     summary="approved for render (compute gate passed)",
                     details={"status": "approved"})
        return video

    # -- render -------------------------------------------------------------

    def render(self, video_id: str, actor: str = "system") -> dict:
        """Synchronous render. main.py wraps this in a background task."""
        video = self._require(video_id)
        if video["status"] != "approved":
            raise StateError(
                f"render requires an approved video (is '{video['status']}'); "
                "approval is the compute gate"
            )

        video = self.store.update_video(video_id, {"status": "rendering", "error": ""})
        self._record("rendering", video, actor, details={"status": "rendering"})

        try:
            result = self._do_render(video)
        except Exception as exc:  # defensive — never leave status stuck at rendering
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        if result.get("ok"):
            video = self.store.update_video(video_id, {
                "status": "rendered", "output_path": result["output"], "error": "",
            })
            self._record("rendered", video, actor,
                         summary=f"MP4 rendered: {result['output']}",
                         details={"status": "rendered", "output_path": result["output"]})
        else:
            video = self.store.update_video(video_id, {
                "status": "failed", "error": result.get("error", "unknown error"),
            })
            self._record("failed", video, actor,
                         summary=f"render failed: {result.get('error')}",
                         details={"status": "failed", "error": result.get("error")})
        return video

    def _do_render(self, video: dict) -> dict:
        scenes = video.get("scenes") or []
        if not scenes:
            return {"ok": False, "error": "no storyboard scenes; run storyboard first"}

        work_dir = os.path.join(self.output_dir, video["id"])
        audio_dir = os.path.join(work_dir, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        voice = build_voice(stub=self.stub_media, fallback_to_stub=True)

        render_scenes = []
        for scene in scenes:
            image = scene.get("image")
            if not (image and os.path.exists(image)):
                return {"ok": False, "error": f"missing scene image for scene {scene.get('index')}"}
            wav = os.path.join(audio_dir, f"scene_{scene['index']:03d}.wav")
            voice.synth(scene["text"], wav)
            render_scenes.append({"image": image, "audio": wav})

        output_path = os.path.join(work_dir, f"{video['id']}.mp4")
        log_path = os.path.join(work_dir, "ffmpeg.log")
        return assemble(render_scenes, output_path, log_path=log_path)

    # -- reads --------------------------------------------------------------

    def get_video(self, video_id: str) -> dict:
        return self._require(video_id)

    def list_videos(self, status: Optional[str] = None) -> list[dict]:
        if status and status not in VALID_STATUSES:
            raise VideoGenError(f"invalid status filter: {status}")
        return self.store.list_videos(status=status)

    def ledger(self, video_id: Optional[str] = None) -> list[dict]:
        return self.store.query_ledger(entity_id=video_id)

    def seed(self, actor: str = "cli") -> dict:
        """Idempotent demo seed — one sample script if none exist."""
        existing = self.store.list_videos()
        title = "Eva — Founder Acquisition Demo"
        for v in existing:
            if v["title"] == title:
                return {"created": 0, "video": v}
        script = (
            "Founders lose hours every week editing marketing videos by hand. "
            "Eva turns a script into a finished vertical video automatically. "
            "No footage, no editor, no studio. Just your idea, rendered and ready to post. "
            "Book a demo and get your first video today."
        )
        video = self.create_video(title=title, script_text=script, actor=actor)
        return {"created": 1, "video": video}

    def _require(self, video_id: str) -> dict:
        video = self.store.get_video(video_id)
        if not video:
            raise NotFoundError(f"unknown video: {video_id}")
        return video
