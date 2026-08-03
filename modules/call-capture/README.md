# Eva Call Capture (`call-capture`) · port 8795

Software-only call/meeting recorder → transcript → AI summary → GHL contact
note. No dedicated hardware (no puck, no separate charging device) — this is
the phone/software equivalent of a HeyPocket-style capture flow, wired
directly into Eva's CRM instead of a standalone app.

## Consent (read first)

California is a **two-party consent** state (Penal Code 632). This module
does **not** do passive/ambient background listening — it is deliberately a
tap-to-record flow, same as the transcription/summary tools it's modeled on.
Callers must disclose recording to all parties before uploading audio. Pass
`consent_disclosed=true` on the upload; if you don't, the GHL note is still
written but is flagged `⚠ Consent NOT confirmed` so nobody mistakes an
undisclosed recording for a compliant one.

## What it does

1. `POST /calls/upload` — accepts an audio file (call or meeting recording)
   plus contact info (email/phone/name).
2. Transcribes the audio (`transcriber.py` — real client hits OpenAI Whisper,
   `WHISPER_API_KEY`/`OPENAI_API_KEY`; stub client is offline/deterministic
   for tests and local dev).
3. Summarizes the transcript into a summary, action items, key topics, and
   sentiment (`summarizer.py` — real client hits an OpenAI-compatible chat
   endpoint; stub client does keyword-based extraction, no network).
4. Syncs to GoHighLevel via the existing `ghl-agent/ghl_client.py`:
   upserts the contact, tags it `eva-call-captured`, and writes a note with
   the full summary + transcript (`pipeline.py`).

## New GHL client method

Added `add_contact_note(contact_id, body)` to `ghl-agent/ghl_client.py`
(Protocol + `StubGHLClient` + `HttpGHLClient`, `POST /contacts/{id}/notes`
on the real client). This was the one gap in the existing client — everything
else (upsert, tag, pipeline, workflow) already existed and is reused as-is.

## Client selection

Both `transcriber.build_transcriber_client()` and
`summarizer.build_summarizer_client()` default to the offline stub unless a
real API key is present in the environment — same pattern as `ghl_client.build_client()`.

## Tests

`tests/test_pipeline.py` (10 tests, all offline/stub-based):
transcript generation, summary extraction, sentiment detection, GHL
contact+note sync, consent flag on the note, skip-sync mode, repeat-caller
contact reuse, and note formatting edge cases.

`ghl-agent/tests/test_add_contact_note.py` (3 tests) covers the new client
method directly: success, unknown contact, multiple notes appended.

Run: `/usr/bin/python3 -m pytest tests/ -q` (this sandbox's default `python3`
lacks pytest/fastapi — use `/usr/bin/python3`, which has pytest+httpx+pydantic
already installed).

## Not yet wired

- `main.py`'s FastAPI app needs `fastapi`/`uvicorn` installed to actually run
  (not available in this sandbox — pipeline/client logic is fully tested via
  stubs regardless, since `main.py` isn't imported by the test suite).
- No real Whisper/LLM API key configured anywhere — both clients degrade to
  their stub form until `WHISPER_API_KEY`/`OPENAI_API_KEY`/`LLM_API_KEY` are
  set.
