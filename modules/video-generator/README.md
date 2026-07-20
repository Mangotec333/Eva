# EVA Video Generator

Turns a text **script/idea into a finished vertical (1080x1920) marketing
video** — with **no source footage**. Segments the script into scenes, renders a
branded Pillow slide per scene (postcards card aesthetic + media-editor teal
lower-third), gates on human **approval before render compute is spent**, then
synthesizes a voiceover per scene and composites everything into one MP4 with
ffmpeg (Ken Burns zoom/pan, burned captions, branded lower-third, crossfades,
loudnorm).

This fills the gap between the existing modules: `content-engine` produces text
drafts, `eva-video-dna` reviews/edits already-recorded founder videos, and
`media-editor` post-processes an existing video file. **Nothing else generates a
video from a script** — this does.

**Stack:** FastAPI + stdlib `sqlite3` + Pillow + ffmpeg (offline-first, no
external DB, no paid API).

**Port:** `8784` (override with `VIDEO_GEN_PORT`).

## Pipeline / status

```
draft ──▶ storyboard_ready ──▶ approved ──▶ rendering ──▶ rendered
                                   ▲                          │
                                   └── human compute gate     └─▶ failed
```

- **draft** — script captured (typed, or pulled from a content-engine draft).
- **storyboard_ready** — script segmented into scenes; a branded slide rendered per scene.
- **approved** — the cost-discipline **human gate**: only approved videos render.
- **rendering / rendered / failed** — async ffmpeg render, status persisted on every transition.

## Key files

- `service.py` — pipeline orchestration + script segmentation + state machine
- `renderer.py` — `SceneVisualRenderer` Protocol + `PillowSceneRenderer` (real) + `StubSceneRenderer` (tests)
- `voice.py` — `VoiceSynth` Protocol + `StubVoiceSynth` (stdlib `wave`, offline) + `MacOSSayVoiceSynth` (real, darwin-guarded)
- `ffmpeg_assembler.py` — the single ffmpeg subprocess chokepoint (Ken Burns + captions + lower-third + xfade + loudnorm)
- `draft_client.py` — content-engine draft-pull `DraftClient` Protocol + Stub + Http
- `state_client.py` — eva-state ledger emitter behind a Protocol (honest `ok=False` when down)
- `database.py` — SQLite schema, append-only `video_ledger` (immutability trigger), `memory` table, mission/goals read
- `main.py` — FastAPI REST API on `:8784`
- `cli.py` — terminal-first CLI

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | status + last-run summary |
| POST | `/videos` | create from `{title, script_text}` **or** `{content_engine_draft_id}` |
| GET | `/videos` | list videos (newest first; `?status=` filter) |
| GET | `/videos/{id}` | one video |
| POST | `/videos/{id}/storyboard` | segment script + render branded slides |
| POST | `/videos/{id}/approve` | compute gate (human) |
| POST | `/videos/{id}/render` | async render; returns `202` immediately |
| GET | `/videos/{id}/ledger` | append-only event trail for this video |

## CLI

| Command | Purpose |
| --- | --- |
| `video-generator seed` | idempotent demo seed |
| `video-generator list [--status S]` | list videos |
| `video-generator create "<title>" "<script>"` | create from a script |
| `video-generator storyboard <id>` | segment + render slides |
| `video-generator approve <id>` | approve for render (compute gate) |
| `video-generator render <id>` | render the MP4 |
| `video-generator status <id>` | show one video |
| `video-generator ledger [<id>]` | show event ledger |

## Quick start

```bash
cd modules/video-generator
bash setup.sh                       # pip install + launch on :8784
python cli.py seed                  # load a demo script
python cli.py storyboard <id>       # render branded slides
python cli.py approve <id>          # compute gate
python cli.py render <id>           # produce the MP4
python -m pytest -q                 # offline test suite (real ffmpeg render)
```

## Transport seams (Protocol + Stub + real)

Every external/compute action is behind a Protocol with an offline Stub (used in
tests, never fakes success) and a real implementation — matching the
`services/tts` Speaker pattern:

- **`SceneVisualRenderer`** — real = Pillow only (no paid API); Stub = deterministic blank PNG.
- **`VoiceSynth`** — Stub = deterministic silent/tone WAV via stdlib `wave` (offline, no ffmpeg/network); real = macOS `say -o file.aiff` → ffmpeg-to-WAV, darwin-guarded with an opt-in stub fallback. **A paid TTS / AI-video API can be wired behind this same Protocol later — no paid dependency is added now.**
- **`DraftClient`** — Stub serves in-memory drafts; real GETs `content-engine` `/drafts/{id}`.
- **`StateLedgerClient`** — Stub records in memory; real POSTs the eva-state ledger (`:8769`). Set `EVA_VIDEO_OFFLINE=1` to force stubs.

The ffmpeg assembly is a single subprocess chokepoint (`ffmpeg_assembler.py`),
mirroring media-editor's `_build_ffmpeg_args`. ffmpeg makes no network calls, so
the render is offline-runnable and tested for real locally.

## EVA Architecture Fit

```
                        docs/MISSION.md + docs/CURRENT_GOALS.md
                                     │ (read at startup)
                                     ▼
   content-engine ──GET /drafts/{id}──▶  ┌───────────────────────┐
   (text draft)                          │  video-generator :8784 │
                                         │  draft → storyboard →  │
   typed script ───────────────────────▶│  approve(gate) → render│──▶ rendered MP4
                                         └───────────┬───────────┘        │
                                                     │ events                │ (future)
                                                     ▼                       ▼
                                          eva-state ledger :8769     channels / postcards
                                                                       (publish)
```

- **Independence + coordination:** own port, own SQLite, own CLI; coordinates only through shared docs (mission/goals) + status endpoints, never by reaching into a sibling's internals.
- **Append-only ledger:** every transition is written to `video_ledger` (immutability trigger) and mirrored to the eva-state ledger.
- **Agent Intelligence Layer:** per-agent `memory` table; reads `docs/MISSION.md` + `docs/CURRENT_GOALS.md` at startup (graceful no-op if absent); `/health` exposes last-run summary.
