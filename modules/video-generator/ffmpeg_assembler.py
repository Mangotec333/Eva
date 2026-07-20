"""
EVA Video Generator — ffmpeg assembly (the single subprocess chokepoint).

Mirrors media-editor's ``_build_ffmpeg_args`` philosophy: all real ffmpeg
command construction lives here, in one validated place. Given a list of scenes
(each with a slide image + a voiceover WAV), this builds ONE ``filter_complex``
that:

  * scales/crops each slide to 1080x1920,
  * applies a Ken Burns slow zoom/pan (``zoompan``) for the scene's duration,
  * burns the branded lower-third (``drawbox`` + two ``drawtext`` captions,
    "Eva-acquisition" left / teal url right — same escape rules as media-editor),
  * crossfades (``xfade``) between consecutive scenes,
  * concatenates every scene's voiceover, crossfading audio (``acrossfade``),
  * loudnorm-normalizes the final mix (I=-16 TP=-1.5 LRA=11),

and writes a single H.264 + AAC MP4. ffmpeg is pre-installed locally and makes
no network calls, so this is offline-runnable and safe to test for real.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

from voice import wav_duration_seconds

FPS = 30
XFADE = 0.6            # seconds of crossfade between scenes
ACCENT_HEX = "0x2dd4a7"
CAPTION_LEFT = "Eva-acquisition"
CAPTION_RIGHT = "eva-acquisition.mangotec.ai"

_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
FONT_BOLD = os.environ.get("FONT_BOLD", os.path.join(_ASSETS, "DejaVuSans-Bold.ttf"))
FONT_REG = os.environ.get("FONT_REG", os.path.join(_ASSETS, "DejaVuSans.ttf"))
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")

W, H = 1080, 1920


def _escape_drawtext(text: str) -> str:
    """Escape a string for ffmpeg drawtext (media-editor rules)."""
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def _scene_video_chain(idx: int, dur: float, opts: dict) -> str:
    """Per-scene video filter: scale/crop -> Ken Burns -> branded lower-third."""
    frames = max(int(round(dur * FPS)), 1)
    left = _escape_drawtext(opts.get("caption_left", CAPTION_LEFT))
    right = _escape_drawtext(opts.get("caption_right", CAPTION_RIGHT))
    accent = opts.get("accent_hex", ACCENT_HEX)
    # Alternate pan direction per scene for variety; zoom always eases in.
    zoom = "min(zoom+0.0006,1.12)"
    if idx % 2 == 0:
        x, y = "iw/2-(iw/zoom/2)", "0"
    else:
        x, y = "iw/2-(iw/zoom/2)", "ih-(ih/zoom)"
    return (
        f"[{2 * idx}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"zoompan=z='{zoom}':d={frames}:x='{x}':y='{y}':s={W}x{H}:fps={FPS},"
        f"drawbox=x=0:y=ih-96:w=iw:h=96:color=black:t=fill,"
        f"drawtext=fontfile={FONT_BOLD}:text='{left}':x=40:y=h-66:"
        f"fontcolor=white:fontsize=40,"
        f"drawtext=fontfile={FONT_REG}:text='{right}':x=w-tw-40:y=h-62:"
        f"fontcolor={accent}:fontsize=34,"
        f"setsar=1,format=yuv420p[v{idx}]"
    )


def build_filter_complex(durations: list[float], opts: dict) -> str:
    """Build the whole filtergraph for N scenes (xfade video + acrossfade audio)."""
    n = len(durations)
    parts = [_scene_video_chain(i, durations[i], opts) for i in range(n)]

    if n == 1:
        parts.append("[v0]copy[vout]")
        parts.append("[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
        return ";".join(parts)

    # Video xfade chain. offset_k = sum(d0..d_{k-1}) - k*XFADE
    prev = "v0"
    cum = durations[0]
    for k in range(1, n):
        offset = cum - k * XFADE
        if offset < 0:
            offset = 0.0
        out = "vout" if k == n - 1 else f"vx{k}"
        parts.append(
            f"[{prev}][v{k}]xfade=transition=fade:duration={XFADE}:"
            f"offset={offset:.3f}[{out}]"
        )
        prev = out
        cum += durations[k]

    # Audio acrossfade chain over the raw wav inputs (audio input i = scene i).
    prev_a = f"{_audio_in(0)}"
    parts.append(f"[{_audio_in(0)}]anull[a0]")
    prev_a = "a0"
    for k in range(1, n):
        out = f"a{k}"
        parts.append(
            f"[{prev_a}][{_audio_in(k)}]acrossfade=d={XFADE}[{out}]"
        )
        prev_a = out
    parts.append(f"[{prev_a}]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    return ";".join(parts)


def _audio_in(scene_idx: int) -> str:
    """Input stream label for scene ``scene_idx``'s audio.

    Inputs are added image-then-wav per scene, so scene i's wav is input
    index ``2*i + 1``.
    """
    return f"{2 * scene_idx + 1}:a"


def build_ffmpeg_args(scenes: list[dict], output_path: str,
                      opts: Optional[dict] = None) -> list[str]:
    """Construct the full ffmpeg argv. ``scenes`` need ``image`` + ``audio``.

    Inputs are added interleaved (image, wav) per scene so scene i's image is
    input ``2*i`` and its wav is input ``2*i + 1`` (see ``_scene_video_chain``
    and ``_audio_in``).
    """
    opts = opts or {}
    durations = [wav_duration_seconds(s["audio"]) for s in scenes]
    args = [FFMPEG_PATH, "-y"]
    for i, s in enumerate(scenes):
        args += ["-loop", "1", "-t", f"{durations[i]:.3f}", "-i", s["image"]]
        args += ["-i", s["audio"]]
    args += [
        "-filter_complex", build_filter_complex(durations, opts),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        output_path,
    ]
    return args


def assemble(scenes: list[dict], output_path: str, opts: Optional[dict] = None,
             log_path: Optional[str] = None) -> dict:
    """Run the ffmpeg chokepoint. Returns {ok, output, returncode, error}."""
    if not scenes:
        return {"ok": False, "error": "no scenes to assemble"}
    for s in scenes:
        if not (s.get("image") and os.path.exists(s["image"])):
            return {"ok": False, "error": f"missing scene image: {s.get('image')}"}
        if not (s.get("audio") and os.path.exists(s["audio"])):
            return {"ok": False, "error": f"missing scene audio: {s.get('audio')}"}

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    args = build_ffmpeg_args(scenes, output_path, opts)
    logf = open(log_path, "wb") if log_path else subprocess.DEVNULL
    try:
        proc = subprocess.run(args, stdout=subprocess.DEVNULL,
                              stderr=logf if log_path else subprocess.PIPE)
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"ffmpeg not found: {exc}"}
    finally:
        if log_path and hasattr(logf, "close"):
            logf.close()

    if proc.returncode == 0 and os.path.exists(output_path):
        return {"ok": True, "output": output_path, "returncode": 0}
    err = ""
    if not log_path and getattr(proc, "stderr", None):
        err = proc.stderr.decode("utf-8", "replace")[-2000:]
    return {"ok": False, "returncode": proc.returncode,
            "error": err or f"ffmpeg exited {proc.returncode}"}


__all__ = ["build_ffmpeg_args", "build_filter_complex", "assemble"]
