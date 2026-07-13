"""Video DNA ingest integrity gate (scaffold stub).

Wraps a local ``ffprobe`` subprocess to answer one question at ingest time:
is this file a playable video we can build a Video DNA record from? It
specifically detects the classic broken-upload failure mode — a missing
``moov`` atom (an MP4 that was truncated or never finalized on export) — and
returns ``playable=False`` with an actionable re-export/re-record message.

This is a dependency-light scaffold: stdlib + subprocess only, no network,
no third-party packages. Transcription, keyframe extraction, and OCR (see
SPEC.md sections 1-2) are future work wired when a valid sample video exists.
"""

from __future__ import annotations

import json
import shutil
import subprocess


def probe_integrity(path: str) -> dict:
    """Probe a video file with ``ffprobe`` and report its integrity.

    Args:
        path: Filesystem path to the video file to probe.

    Returns:
        A dict with keys:
            playable (bool): True if ffprobe parsed a usable video stream.
            has_moov (bool): True if the moov atom is present (MP4/MOV).
            duration (float | None): Container duration in seconds.
            width (int | None): Video width in pixels.
            height (int | None): Video height in pixels.
            orientation (str | None): "vertical", "horizontal", or "square".
            audio_present (bool): True if at least one audio stream exists.
            error (str | None): Human-readable failure message, else None.
    """
    result: dict = {
        "playable": False,
        "has_moov": False,
        "duration": None,
        "width": None,
        "height": None,
        "orientation": None,
        "audio_present": False,
        "error": None,
    }

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        result["error"] = "ffprobe not found on PATH — install ffmpeg to run the ingest integrity gate."
        return result

    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        result["error"] = f"File not found: {path}"
        return result
    except subprocess.TimeoutExpired:
        result["error"] = "ffprobe timed out — file may be corrupt or truncated. Re-export and re-upload."
        return result

    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0 or not completed.stdout.strip():
        lowered = stderr.lower()
        if "moov atom not found" in lowered:
            result["error"] = (
                "Missing moov atom — the file is truncated or was never finalized on export. "
                "Re-export (enable 'faststart' / finalize the MP4) or re-record, then re-upload."
            )
        else:
            result["error"] = stderr or "ffprobe could not read the file. Re-export / re-record and re-upload."
        return result

    # ffprobe returned success and JSON: the moov atom was readable.
    result["has_moov"] = True

    try:
        probe = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result["error"] = "ffprobe returned unparseable output. Re-export / re-record and re-upload."
        return result

    fmt = probe.get("format", {})
    duration_raw = fmt.get("duration")
    if duration_raw is not None:
        try:
            result["duration"] = float(duration_raw)
        except (TypeError, ValueError):
            result["duration"] = None

    video_stream = None
    for stream in probe.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and video_stream is None:
            video_stream = stream
        elif codec_type == "audio":
            result["audio_present"] = True

    if video_stream is None:
        result["error"] = "No video stream found. Re-export / re-record and re-upload."
        return result

    width = video_stream.get("width")
    height = video_stream.get("height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        result["width"] = width
        result["height"] = height
        if height > width:
            result["orientation"] = "vertical"
        elif width > height:
            result["orientation"] = "horizontal"
        else:
            result["orientation"] = "square"

    result["playable"] = True
    return result
