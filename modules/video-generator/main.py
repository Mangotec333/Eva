"""
EVA Video Generator — script-to-video backend (FastAPI microservice)
====================================================================
Port: 8794 (override with VIDEO_GEN_PORT)

Turns a text script/idea into a finished vertical (1080x1920) marketing video
with NO source footage: segment the script into scenes, render a branded Pillow
slide per scene, gate on human approval (the cost-discipline compute gate), then
synth a voiceover per scene and composite everything into one MP4 with ffmpeg
(Ken Burns motion, burned captions, branded lower-third, crossfades, loudnorm).

Fills the gap between content-engine (text drafts), eva-video-dna (reviews
existing founder videos) and media-editor (post-processes an existing file):
nothing else GENERATES a video from a script.

Pipeline / status: draft -> storyboard_ready -> approved -> rendering ->
rendered | failed.

Endpoints:
  GET  /health                     -> status + last-run summary
  POST /videos                     -> {title, script_text} OR {content_engine_draft_id}
  GET  /videos                     -> all videos, newest first
  GET  /videos/{id}                -> one video
  POST /videos/{id}/storyboard     -> segment + render branded slides
  POST /videos/{id}/approve        -> compute gate (human)
  POST /videos/{id}/render         -> async render; returns immediately
  GET  /videos/{id}/ledger         -> append-only event trail for this video
"""

from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import read_mission_and_goals
from service import (NotFoundError, StateError, VideoGenError,
                     VideoGeneratorService)

AGENT_VERSION = "0.1.0"
PORT = int(os.environ.get("VIDEO_GEN_PORT", "8794"))

# In-flight render tasks, keyed by video id, so /render is idempotent-ish.
_render_tasks: dict[str, asyncio.Task] = {}
_last_run: dict = {"video_id": None, "status": None, "at": None}


def _build_service() -> VideoGeneratorService:
    # Force Stub media (renderer/voice) when running fully offline, so the
    # service boots and works without ffmpeg/say wired up.
    offline = os.environ.get("EVA_VIDEO_OFFLINE") == "1"
    stub_media = os.environ.get("VIDEO_GEN_STUB_MEDIA") == "1"
    return VideoGeneratorService(offline=offline or None, stub_media=stub_media or None)


svc = _build_service()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Agent Intelligence Layer: read mission/goals at startup (graceful no-op).
    read_mission_and_goals()
    yield


app = FastAPI(
    title="EVA Video Generator",
    description=(
        "Turns a text script/idea into a finished vertical marketing video with "
        "no source footage: storyboard -> approve -> render (voiceover + ffmpeg "
        "Ken Burns, captions, branded lower-third) -> MP4."
    ),
    version=AGENT_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


class CreateVideo(BaseModel):
    title: Optional[str] = None
    script_text: Optional[str] = None
    content_engine_draft_id: Optional[str] = None


@app.get("/health", tags=["Meta"])
async def health():
    videos = svc.list_videos()
    return {
        "status": "ok",
        "module": "eva-video-generator",
        "version": AGENT_VERSION,
        "port": PORT,
        "offline": os.environ.get("EVA_VIDEO_OFFLINE") == "1",
        "videos_total": len(videos),
        "renders_in_flight": sum(1 for t in _render_tasks.values() if not t.done()),
        "last_run": _last_run,
    }


@app.post("/videos", tags=["Videos"], status_code=201)
async def create_video(body: CreateVideo):
    try:
        return svc.create_video(
            title=body.title, script_text=body.script_text,
            content_engine_draft_id=body.content_engine_draft_id, actor="api",
        )
    except VideoGenError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/videos", tags=["Videos"])
async def list_videos(status: Optional[str] = None):
    try:
        videos = svc.list_videos(status=status)
    except VideoGenError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"count": len(videos), "videos": videos}


@app.get("/videos/{video_id}", tags=["Videos"])
async def get_video(video_id: str):
    try:
        return svc.get_video(video_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/videos/{video_id}/storyboard", tags=["Pipeline"])
async def storyboard(video_id: str):
    try:
        return await asyncio.to_thread(svc.storyboard, video_id, "api")
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except VideoGenError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/videos/{video_id}/approve", tags=["Pipeline"])
async def approve(video_id: str):
    try:
        return svc.approve(video_id, actor="human")
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except StateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


async def _run_render(video_id: str) -> None:
    try:
        video = await asyncio.to_thread(svc.render, video_id, "api")
        _last_run.update({"video_id": video_id, "status": video["status"],
                          "at": video.get("updated_at")})
    finally:
        _render_tasks.pop(video_id, None)


@app.post("/videos/{video_id}/render", tags=["Pipeline"], status_code=202)
async def render(video_id: str):
    try:
        video = svc.get_video(video_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if video["status"] != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"render requires an approved video (is '{video['status']}')",
        )
    if video_id in _render_tasks and not _render_tasks[video_id].done():
        return {"video_id": video_id, "status": "rendering", "note": "already in flight"}
    _render_tasks[video_id] = asyncio.create_task(_run_render(video_id))
    return {"video_id": video_id, "status": "rendering"}


@app.get("/videos/{video_id}/ledger", tags=["Pipeline"])
async def ledger(video_id: str):
    try:
        svc.get_video(video_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    entries = svc.ledger(video_id)
    return {"count": len(entries), "ledger": entries}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Video Generator microservice")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
