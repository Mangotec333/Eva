"""
EVA Media Editor — auto video-edit backend (FastAPI microservice)
=================================================================
Port: 8783 (override with MEDIA_EDITOR_PORT)

Auto-edits uploaded videos in the background:
  * covers a clipped bottom-left caption with a 64px branded lower-third,
  * burns "Eva-acquisition" (left) + "eva-acquisition.mangotec.ai" (right, teal),
  * normalizes voice audio (loudnorm I=-16 TP=-1.5 LRA=11),
  * optionally mixes/ducks background music (experimental).

Jobs run in the background via asyncio.create_subprocess_exec. Job state is
persisted to state/jobs.json on EVERY status transition (atomic write) so a
sandbox/restart loss cannot lose the ledger. On startup any job left "running"
is marked "interrupted"; interrupted jobs whose output is missing are re-queued.

Endpoints:
  GET  /health           -> {status, offline, jobs_running, ...}
  POST /edit             -> multipart `video` upload OR JSON {video_path}; returns {job_id}
  GET  /jobs/{job_id}    -> one job record
  GET  /jobs             -> all jobs, most recent first

Mirrors modules/ghl-agent conventions (FastAPI, launchd plist, /health, env
config, eva-state ledger emitter behind a client seam).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import UploadFile as StarletteUploadFile

from state_client import build_state_client

# ---------------------------------------------------------------------------
# Config (env vars with sane defaults)
# ---------------------------------------------------------------------------

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(MODULE_DIR, "assets")

AGENT_VERSION = "0.1.0"
PORT = int(os.environ.get("MEDIA_EDITOR_PORT", "8783"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(MODULE_DIR, "out"))
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
FONT_BOLD = os.environ.get("FONT_BOLD", os.path.join(ASSETS_DIR, "DejaVuSans-Bold.ttf"))
FONT_REG = os.environ.get("FONT_REG", os.path.join(ASSETS_DIR, "DejaVuSans.ttf"))

STATE_DIR = os.path.join(MODULE_DIR, "state")
JOBS_FILE = os.path.join(STATE_DIR, "jobs.json")

IN_DIR = os.path.join(OUTPUT_DIR, "in")
OUT_DIR = os.path.join(OUTPUT_DIR, "out")
LOG_DIR = os.path.join(OUTPUT_DIR, "logs")

# Defaults for the branded lower-third.
DEFAULT_CAPTION_LEFT = "Eva-acquisition"
DEFAULT_CAPTION_RIGHT = "eva-acquisition.mangotec.ai"
DEFAULT_ACCENT_HEX = "0x2dd4a7"
DEFAULT_MUSIC_DUCK_DB = -18


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    for d in (STATE_DIR, OUTPUT_DIR, IN_DIR, OUT_DIR, LOG_DIR):
        os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------------------
# Job store — the single source of truth, persisted atomically.
# ---------------------------------------------------------------------------


class JobStore:
    """In-memory job dict backed by an atomically-rewritten jobs.json.

    A single asyncio.Lock guards writes so overlapping transitions can't
    interleave a half-written file. Every mutation goes through _persist().
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.jobs: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    def load(self) -> None:
        """Load jobs.json from disk (called once at startup, sync)."""
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self.jobs = data.get("jobs", data)
            elif isinstance(data, list):
                self.jobs = {j["job_id"]: j for j in data}
        except FileNotFoundError:
            self.jobs = {}
        except (json.JSONDecodeError, KeyError):
            # Corrupt ledger — keep a backup, start clean rather than crash.
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass
            self.jobs = {}

    def _write_sync(self) -> None:
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"jobs": self.jobs, "updated_at": _now()}, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    async def persist(self) -> None:
        async with self._lock:
            self._write_sync()

    def persist_sync(self) -> None:
        self._write_sync()


store = JobStore(JOBS_FILE)
state_ledger = build_state_client()


def _emit(event_type: str, job: dict, summary: str = "") -> None:
    """Best-effort append to the eva-state ledger. Never raises."""
    try:
        state_ledger.emit(
            event_type=event_type,
            summary=summary or f"media-editor job {job['job_id']} -> {job['status']}",
            entity_id=job["job_id"],
            payload={"status": job["status"], "input": job.get("input"),
                     "output": job.get("output"), "error": job.get("error")},
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ffmpeg command construction — the validated, tested pipeline.
# ---------------------------------------------------------------------------


def _build_filter_complex(opts: dict) -> str:
    """The validated filter_complex: lower-third bar + two captions + loudnorm.

    Text values are single-quote-escaped for ffmpeg's drawtext (which parses
    its own args), so untrusted caption text can't break out of the filter.
    """
    left = _escape_drawtext(opts["caption_left"])
    right = _escape_drawtext(opts["caption_right"])
    accent = opts["accent_hex"]

    video = (
        f"[0:v]drawbox=x=0:y=ih-64:w=iw:h=64:color=black:t=fill,"
        f"drawtext=fontfile={FONT_BOLD}:text='{left}':x=28:y=h-46:"
        f"fontcolor=white:fontsize=30,"
        f"drawtext=fontfile={FONT_REG}:text='{right}':x=w-tw-28:y=h-44:"
        f"fontcolor={accent}:fontsize=26[v]"
    )

    if opts.get("music_path"):
        # Experimental: duck looped music under normalized voice, then mix.
        duck_db = opts.get("music_duck_db", DEFAULT_MUSIC_DUCK_DB)
        vol = _db_to_linear(duck_db)
        audio = (
            f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[voice];"
            f"[1:a]volume={vol:.4f}[music];"
            f"[voice][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
    else:
        audio = "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]"

    return f"{video};{audio}"


def _escape_drawtext(text: str) -> str:
    """Escape a string for use inside a single-quoted ffmpeg drawtext text=."""
    # Backslash and single-quote are the dangerous ones inside 'text=...'.
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def _db_to_linear(db: float) -> float:
    return float(10 ** (float(db) / 20.0))


def _build_ffmpeg_args(job: dict) -> list[str]:
    opts = job["options"]
    args = [FFMPEG_PATH, "-y", "-i", job["input"]]

    music = opts.get("music_path")
    if music:
        # Loop the music input to cover the full video duration.
        args += ["-stream_loop", "-1", "-i", music]

    args += [
        "-filter_complex", _build_filter_complex(opts),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
    ]
    if music:
        # -shortest so the looped music stops with the video.
        args += ["-shortest"]
    args += [job["output"]]
    return args


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


async def _run_job(job_id: str) -> None:
    job = store.jobs.get(job_id)
    if job is None:
        return

    job["status"] = "running"
    job["started_at"] = _now()
    await store.persist()
    _emit("media.edit.running", job)

    log_path = os.path.join(LOG_DIR, f"{job_id}.log")
    args = _build_ffmpeg_args(job)

    try:
        with open(log_path, "wb") as logf:
            logf.write(f"# {_now()} exec: {' '.join(args)}\n\n".encode())
            logf.flush()
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.DEVNULL, stderr=logf)
            returncode = await proc.wait()
    except FileNotFoundError as exc:
        job["status"] = "failed"
        job["error"] = f"ffmpeg not found: {exc}"
        job["finished_at"] = _now()
        await store.persist()
        _emit("media.edit.failed", job)
        return
    except Exception as exc:  # pragma: no cover - defensive
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["finished_at"] = _now()
        await store.persist()
        _emit("media.edit.failed", job)
        return

    job["finished_at"] = _now()
    if returncode == 0 and os.path.exists(job["output"]):
        job["status"] = "done"
        job["error"] = None
        _emit("media.edit.done", job)
    else:
        job["status"] = "failed"
        job["error"] = f"ffmpeg exited {returncode}; see logs/{job_id}.log"
        _emit("media.edit.failed", job)
    await store.persist()


def _new_job(input_path: str, options: dict) -> dict:
    job_id = uuid.uuid4().hex[:12]
    output_path = os.path.join(OUT_DIR, f"{job_id}.mp4")
    return {
        "job_id": job_id,
        "status": "queued",
        "input": input_path,
        "output": output_path,
        "options": options,
        "log": os.path.join(LOG_DIR, f"{job_id}.log"),
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "error": None,
    }


def _normalize_options(raw: dict) -> dict:
    try:
        duck = float(raw.get("music_duck_db"))
    except (TypeError, ValueError):
        duck = DEFAULT_MUSIC_DUCK_DB
    return {
        "caption_left": (raw.get("caption_left") or DEFAULT_CAPTION_LEFT),
        "caption_right": (raw.get("caption_right") or DEFAULT_CAPTION_RIGHT),
        "accent_hex": (raw.get("accent_hex") or DEFAULT_ACCENT_HEX),
        "music_path": (raw.get("music_path") or None),
        "music_duck_db": duck,
    }


# ---------------------------------------------------------------------------
# Startup recovery — the CRITICAL persistence guarantee.
# ---------------------------------------------------------------------------


async def _recover_on_startup() -> None:
    """Reload jobs.json; mark stale 'running' as 'interrupted'; re-queue those
    whose output is missing so KeepAlive restarts don't strand work."""
    store.load()
    requeue: list[str] = []
    changed = False
    for job in store.jobs.values():
        if job.get("status") == "running":
            job["status"] = "interrupted"
            job["error"] = "process lost before completion (restart/sandbox loss)"
            job["finished_at"] = _now()
            changed = True
            _emit("media.edit.interrupted", job)
            if job.get("input") and os.path.exists(job["input"]) and not (
                job.get("output") and os.path.exists(job["output"])
            ):
                requeue.append(job["job_id"])
    if changed:
        store.persist_sync()
    for job_id in requeue:
        job = store.jobs[job_id]
        job["status"] = "queued"
        job["error"] = None
        store.persist_sync()
        asyncio.create_task(_run_job(job_id))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_dirs()
    await _recover_on_startup()
    yield


app = FastAPI(
    title="EVA Media Editor",
    description=(
        "Auto-edits videos in the background: branded lower-third over clipped "
        "captions, voice loudness normalization, optional music mix. Job state "
        "is persisted atomically to survive restarts."
    ),
    version=AGENT_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _jobs_running() -> int:
    return sum(1 for j in store.jobs.values() if j.get("status") in ("queued", "running"))


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-media-editor",
        "version": AGENT_VERSION,
        "port": PORT,
        "offline": False,
        "jobs_running": _jobs_running(),
        "jobs_total": len(store.jobs),
        "output_dir": OUTPUT_DIR,
        "state_file": JOBS_FILE,
    }


@app.post("/edit", tags=["Edit"])
async def edit(request: Request):
    """Start an async edit. Accepts either a multipart `video` upload or a JSON
    body `{video_path, ...options}`. Returns {job_id} immediately.

    The request is parsed manually off the raw Request so the app can boot and
    serve JSON edits even when python-multipart isn't installed; multipart
    uploads require it (it's listed in requirements.txt for the Mac).
    """
    _ensure_dirs()

    content_type = (request.headers.get("content-type") or "").lower()
    raw_opts: dict = {}
    input_path: str | None = None

    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
        except Exception as exc:  # python-multipart missing or malformed body
            raise HTTPException(
                status_code=400,
                detail=f"multipart parsing failed ({exc}); install python-multipart "
                       "or POST JSON {video_path}")
        upload = form.get("video")
        if isinstance(upload, StarletteUploadFile):
            fname = os.path.basename(upload.filename or "upload.mp4")
            dest = os.path.join(IN_DIR, f"{uuid.uuid4().hex[:12]}_{fname}")
            with open(dest, "wb") as fh:
                shutil.copyfileobj(upload.file, fh)
            input_path = dest
        else:
            input_path = (str(form.get("video_path") or "").strip() or None)
            if input_path and not os.path.exists(input_path):
                raise HTTPException(status_code=422, detail=f"video_path not found: {input_path}")
        raw_opts = {k: form.get(k) for k in
                    ("caption_left", "caption_right", "accent_hex", "music_path", "music_duck_db")}
    else:
        # JSON body path.
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        input_path = (str(data.get("video_path") or "").strip() or None)
        if input_path and not os.path.exists(input_path):
            raise HTTPException(status_code=422, detail=f"video_path not found: {input_path}")
        raw_opts = data

    if not input_path:
        raise HTTPException(status_code=422, detail="provide a `video` upload or `video_path`")

    opts = _normalize_options(raw_opts)
    if opts["music_path"] and not os.path.exists(opts["music_path"]):
        raise HTTPException(status_code=422, detail=f"music_path not found: {opts['music_path']}")

    job = _new_job(input_path, opts)
    store.jobs[job["job_id"]] = job
    await store.persist()
    _emit("media.edit.queued", job)

    asyncio.create_task(_run_job(job["job_id"]))
    return {"job_id": job["job_id"], "status": job["status"]}


def _public(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "input": job.get("input"),
        "output": job.get("output"),
        "options": job.get("options"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "error": job.get("error"),
    }


@app.get("/jobs/{job_id}", tags=["Jobs"])
async def get_job(job_id: str):
    job = store.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {job_id}")
    return _public(job)


@app.get("/jobs", tags=["Jobs"])
async def list_jobs():
    ordered = sorted(store.jobs.values(), key=lambda j: j.get("created_at") or "", reverse=True)
    return {"count": len(ordered), "jobs": [_public(j) for j in ordered]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Media Editor microservice")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
