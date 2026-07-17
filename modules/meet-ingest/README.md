# EVA Meet Ingest

Frugal, **zero-API-cost**, self-hosted meeting pipeline:

```
Google Meet auto-records a call to Drive
   → EVA polls Drive ("Meet Recordings" folder, past a watermark)
   → downloads the recording
   → extracts audio with ffmpeg (16kHz mono WAV)
   → transcribes locally with whisper.cpp (no network, no API spend)
   → stores the transcript + a short summary stub
   → files them into Drive under EVA/Meetings/<meeting-name>/
```

Built to the Eva **Architecture Directive** (`modules/README.md`): own FastAPI
app + port, own SQLite, own CLI/tests, every transport behind a Protocol with an
offline `Stub`, an append-only ledger with an immutability trigger, and an
idempotent, cron-safe `tick`.

**Stack:** FastAPI + stdlib `sqlite3` + ffmpeg + whisper.cpp (via
`services/stt/whisper_cpp.py`). Port **8785**.

## Prerequisites (user-provided, checked at runtime)

The pipeline runs offline with **stub transports** out of the box (tests, dry
runs). For **real** use you must supply, on your own machine:

1. **Google Meet auto-recording enabled** and set to save recordings to Google
   Drive (Google's default "Meet Recordings" folder).
2. **whisper.cpp built locally** + a ggml model downloaded:
   - binary (the `main` executable) — point EVA at it with `EVA_WHISPER_BIN`
     (default `~/.eva/whisper/main`)
   - model (e.g. `ggml-base.en.bin`) — `EVA_WHISPER_MODEL`
     (default `~/.eva/whisper/ggml-base.en.bin`)
   - build instructions: https://github.com/ggerganov/whisper.cpp
3. **Drive OAuth credentials** at `~/.eva/drive_credentials.json` (an OAuth
   client `client_secret.json` from Google Cloud). First real run opens a
   browser consent flow and caches a token at `~/.eva/drive_token.pickle`.
   Scope: `https://www.googleapis.com/auth/drive`.

ffmpeg is expected to already be installed on the Eva host.

Switch to real transports with env vars:
```bash
export EVA_MEET_DRIVE=real
export EVA_MEET_TRANSCRIBER=whisper
```

## Quick start

```bash
cd modules/meet-ingest
bash setup.sh                 # pip install + prerequisite check, then serve :8785

# offline dry-run (stub transports, no network / no whisper.cpp needed):
python cli.py tick            # poll + process all pending
python cli.py list
python -m pytest              # offline test suite (zero outbound calls)
```

## Endpoints (port 8785)

| Method | Path                    | Purpose                                   |
|--------|-------------------------|-------------------------------------------|
| GET    | `/health`               | status + drive/transcriber + last run     |
| POST   | `/poll`                 | discover new Drive recordings (idempotent)|
| POST   | `/process/{meeting_id}` | run the pipeline for one meeting          |
| POST   | `/tick`                 | poll + process all pending (cron-safe)    |
| GET    | `/meetings`             | list meetings (`?status=`)                |
| GET    | `/meetings/{id}`        | one meeting                               |
| GET    | `/ledger`               | append-only event ledger                  |

## CLI

```bash
python cli.py poll                 # discover new recordings
python cli.py list [--status ...]  # pending|downloading|transcribing|done|failed
python cli.py show <id>            # one meeting
python cli.py process <id>         # run the pipeline for one meeting
python cli.py tick                 # poll + process all pending (safe for cron)
python cli.py ledger               # append-only event trail
```

## Key files

- `service.py` — core logic: `poll` / `process` / `tick`, mission/goals + memory
- `drive_client.py` — Drive transport chokepoint (`StubDriveClient` / `RealDriveClient`)
- `transcriber.py` — ffmpeg extraction + `WhisperCppTranscriber` (`StubTranscriber` / `WhisperTranscriber`)
- `database.py` — SQLite: `meetings`, `memory`, append-only `ledger` (+ trigger)
- `main.py` — FastAPI on :8785
- `cli.py` — terminal-first CLI
- `test_meet_ingest.py` — offline test suite (stub transports only)

## Status — v1

This is a **v1**. Per the module release checklist in `modules/README.md`, it
must go through the **2-week, 3×daily manual-testing window** before it is
allowed to run autonomously on a cron. Until then, drive it manually via the CLI
/ API and review each transcript.
