# EVA Media Editor

Auto-edits videos in the background and **persists job state to survive a restart / sandbox loss**.

Each job:
1. Covers a clipped bottom-left caption with a **64px black lower-third bar**.
2. Burns a branded lower-third: **`Eva-acquisition`** (bold, left, white) + **`eva-acquisition.mangotec.ai`** (right, teal `#2dd4a7`).
3. Normalizes voice audio (`loudnorm I=-16:TP=-1.5:LRA=11`).
4. Optionally mixes ducked background music (experimental — see below).

Port: **8783** (`MEDIA_EDITOR_PORT`). Mirrors the `modules/ghl-agent` conventions (FastAPI, `/health`, launchd plist with env in `EnvironmentVariables`, eva-state ledger emitter).

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | `{status:"ok", offline:false, jobs_running:N, ...}` |
| POST | `/edit` | Start an edit; returns `{job_id, status}` **immediately** (ffmpeg runs async) |
| GET | `/jobs/{job_id}` | One job: `{job_id, status, input, output, started_at, finished_at, error?}` |
| GET | `/jobs` | All jobs, most recent first |

### POST /edit

Two ways to supply the source video:

```bash
# A) multipart upload (saved to OUTPUT_DIR/in) — requires python-multipart
curl -F "video=@/path/clip.mp4" -F "caption_left=Deal Scout" http://localhost:8783/edit

# B) JSON with a path already on the box
curl -X POST http://localhost:8783/edit -H 'Content-Type: application/json' \
  -d '{"video_path":"/Users/vineetkumar/Eva/media/in/clip.mp4"}'
```

Options (form fields or JSON keys, all optional):

| Key | Default | Notes |
|---|---|---|
| `caption_left` | `Eva-acquisition` | bold left caption |
| `caption_right` | `eva-acquisition.mangotec.ai` | teal right caption |
| `accent_hex` | `0x2dd4a7` | right-caption color (ffmpeg `0xRRGGBB`) |
| `music_path` | — | background music file (experimental) |
| `music_duck_db` | `-18` | how far to duck music under voice, in dB |

Returns `{"job_id": "...", "status": "queued"}`. Poll `GET /jobs/{job_id}`; the output lands at `OUTPUT_DIR/out/{job_id}.mp4`, stderr at `OUTPUT_DIR/logs/{job_id}.log`.

## The validated ffmpeg pipeline

Tested → clean `1080x1920 / 63s` h264/aac output. The lower-third bar covers the previously-clipped bottom-left caption.

```
ffmpeg -y -i INPUT.mp4 -filter_complex \
"[0:v]drawbox=x=0:y=ih-64:w=iw:h=64:color=black:t=fill,\
drawtext=fontfile=FONT_BOLD:text='Eva-acquisition':x=28:y=h-46:fontcolor=white:fontsize=30,\
drawtext=fontfile=FONT_REG:text='eva-acquisition.mangotec.ai':x=w-tw-28:y=h-44:fontcolor=0x2dd4a7:fontsize=26[v];\
[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]" \
-map "[v]" -map "[a]" -c:v libx264 -preset fast -crf 20 -c:a aac -b:a 128k -movflags +faststart OUTPUT.mp4
```

Fonts are bundled in `assets/` (`DejaVuSans-Bold.ttf`, `DejaVuSans.ttf`) so the module is self-contained — no system font lookup needed on the Mac.

## State persistence (the critical guarantee)

- Every status transition (`queued → running → done | failed`) **atomically rewrites** `state/jobs.json` (write `.tmp` + `fsync` + `os.replace`).
- On startup the service reloads `state/jobs.json`. Any job still marked `running` (i.e. the process died mid-edit) is set to **`interrupted`**. If its output file is missing, it is **re-queued** automatically so a KeepAlive restart doesn't strand work.
- Job lifecycle events are also best-effort appended to the eva-state ledger (`:8769`); if the ledger is down the edit still succeeds locally (honest `{"ok": false}`, never faked). Set `EVA_MEDIA_OFFLINE=1` to skip the ledger entirely.

`state/jobs.json` and `out/` are git-ignored (runtime artifacts).

## Config (env vars)

| Var | Default |
|---|---|
| `MEDIA_EDITOR_PORT` | `8783` |
| `OUTPUT_DIR` | `./modules/media-editor/out` |
| `FONT_BOLD` | bundled `assets/DejaVuSans-Bold.ttf` |
| `FONT_REG` | bundled `assets/DejaVuSans.ttf` |
| `FFMPEG_PATH` | `ffmpeg` |
| `EVA_STATE_URL` | `http://localhost:8769` |
| `EVA_MEDIA_OFFLINE` | unset (`1` = skip ledger) |

## Run it on the Mac

```bash
cd ~/Eva/modules/media-editor
brew install ffmpeg              # required
pip install -r requirements.txt  # fastapi, uvicorn, python-multipart, httpx
./setup.sh                       # or: python3 main.py
```

### launchd (auto-start, RunAtLoad + KeepAlive)

```bash
cp modules/media-editor/com.eva.media-editor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.eva.media-editor.plist
# health check:
curl -s http://localhost:8783/health
```

The plist mirrors `com.eva.ghl-agent.plist`: it calls `modules/autostart/run-service.sh media-editor main.py media-editor 8783`, which sources the shell env, waits for the launcher, and clears a stale listener on `:8783` before binding. Env vars live in `EnvironmentVariables` (launchd does **not** source `~/.zshrc`).

## Music mixing — experimental

If `music_path` is set the service adds a second input (`-stream_loop -1` to cover the full duration), attenuates it by `music_duck_db` (default -18 dB), and `amix`es it under the normalized voice with `-shortest`. This path is best-effort; results depend on the source audio. If mixing is fragile for a given clip, run the **no-music** path (solid and validated) and add music afterward.

**No-code fallback for music:** import the edited `out/{job_id}.mp4` into **CapCut**, drop a music track, and export. CapCut handles ducking and licensing UX better than a one-shot ffmpeg mix.
