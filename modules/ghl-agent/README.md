# EVA GHL Agent (`ghl-agent`) · port 8782

The single Eva-owned service that talks to **GoHighLevel**. No other module
reaches into GHL directly. It does two things:

1. **One-time campaign/funnel build** (Part 1) — idempotent, API-driven.
2. **Ongoing lead-capture automation loop** (Part 2) — capture, webhooks, and
   lead-lifecycle events written to the Eva State Ledger.

## Quick start

```bash
cd modules/ghl-agent
bash setup.sh                       # installs deps, inits ledger, starts on :8782
# or, manually:
python3 main.py --port 8782         # FastAPI service
```

Offline by default in the sandbox (network-free stub GHL + stub state client).
To talk to live GoHighLevel, set a **Location API Key** (recommended — see
[Auth](#auth-location-api-key-primary) below). OAuth is an optional alternative.

Set `EVA_GHL_OFFLINE=1` to force stubs even when credentials are present.

## Auth (Location API Key — primary)

The **recommended and primary** auth is a GHL **Location API Key**
(`pit-…`/`pi-…`). These keys are **long-lived** — there is no hourly access-token
expiry and **no refresh needed** — so nothing is ever rotated by hand:

```bash
export GHL_ACCESS_TOKEN="pit-…"     # GHL Location API Key (primary)
export GHL_LOCATION_ID="…"
python3 main.py
```

Because a Location API Key can't be refreshed, a `401` on this path is treated as
a hard failure (invalid/revoked key): the client **does not** attempt any OAuth
refresh and **does not** retry. It emits `ghl_api_failed` to the Eva State Ledger
and fails the call cleanly — no loop, no retry storm.

## OAuth setup (optional)

OAuth is **optional**. Configure it only if you specifically want short-lived,
self-refreshing access tokens instead of a Location API Key. When an
`ghl.oauth.refresh_token` (or `GHL_OAUTH_REFRESH_TOKEN`) is set, the agent uses a
self-refreshing OAuth 2.0 access token derived from that long-lived
`refresh_token`, and a `401` forces one refresh + retry (persistent `401` →
`ghl_oauth_failed`).

Config is **config-file-primary** (`~/.eva/channels_config.json`), mirroring the
channels/social-publish connectors, with env-var fallbacks:

```json
{
  "ghl": {
    "oauth": {
      "client_id": "…",
      "client_secret": "…",
      "refresh_token": "…",
      "location_id": "kyK4yAY6Hur3F4deCx2n"
    }
  }
}
```

Env fallbacks: `GHL_OAUTH_CLIENT_ID`, `GHL_OAUTH_CLIENT_SECRET`,
`GHL_OAUTH_REFRESH_TOKEN`, `GHL_LOCATION_ID`.

**Steps (do once):**

1. **Create a GHL OAuth app.** In GHL go to **Settings → Developer** (or the
   **Marketplace → My Apps**) and create an app. Note the **client_id** and
   **client_secret**. Add a redirect URI you control and grant the scopes the
   agent needs (contacts, opportunities, calendars, locations/customFields,
   workflows read).
2. **One-time handshake to get a `refresh_token`.** Send yourself through the
   authorization URL for your app + location, approve it, and exchange the
   returned `code` at `POST https://services.leadconnectorhq.com/oauth/token`
   (`grant_type=authorization_code`). The response contains a `refresh_token`.
3. **Store it.** Put `client_id`, `client_secret`, `refresh_token`, and
   `location_id` into `~/.eva/channels_config.json` under `ghl.oauth` (above).

From then on the agent calls
`POST https://services.leadconnectorhq.com/oauth/token`
(`grant_type=refresh_token`) automatically, caches the `access_token` + expiry
(in memory and SQLite), refreshes preemptively when <60s remain, and on any `401`
forces one refresh + retry. A persistent `401` emits `ghl_oauth_failed` to the
Eva State Ledger instead of crashing.

If `ghl.oauth` creds are absent the agent uses the primary
[Location API Key](#auth-location-api-key-primary) path instead.

## CLI (terminal-first)

```bash
python3 cli.py build-funnel                     # run the idempotent Part 1 build
python3 cli.py funnel-status                     # which build pieces exist
python3 cli.py capture-lead you@example.com --name "You"
python3 cli.py events --email you@example.com    # local lead-lifecycle ledger
python3 cli.py webhook '{"type":"email_opened","contact_id":"c1"}'
python3 cli.py campaign                          # print + voice-validate the 7 touches
```

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | health + last-run + lead-event count |
| GET  | `/directive` | the live directive (`directive.md`) |
| POST | `/funnel/build` | trigger the idempotent Part 1 build |
| GET  | `/funnel/status` | whether pipeline/calendar/fields/templates/workflow exist |
| POST | `/lead/capture` | `{email, name?, phone?, source?}` → upsert + tag + pipeline + campaign |
| POST | `/lead/webhook` | receive a GHL event → lead lifecycle → state ledger |

`/lead/capture` returns `{contact_id, status, tag, pipeline_stage}`. It requires
`email` or `phone` (GHL's contact rule).

## Part 1 — the one-time build

Idempotent (check-then-create). Creates:

1. Pipeline **Eva Acquisition** — stages Lead → Engaged → Demo Booked → Demo Held → Closed.
2. Calendar **Eva Demo Call** (book-a-call) — returns the booking link.
3. Custom field **source** = `eva-acquisition`.
4. The 7-touch email/SMS templates (21-day cadence).
5. A workflow that fires the sequence when a contact is tagged `eva-acquisition`.

Each piece is recorded in the append-only `funnel_artifacts` ledger, so the build
is idempotent across restarts and `/funnel/status` can answer without re-hitting
GHL.

### The 7-touch sequence

| # | Day | Channel | Angle |
|---|----:|---------|-------|
| 1 | 0  | email | Intro — the manual scanning ends here (→ eva-acquisition.mangotec.ai) |
| 2 | 2  | email | The $10K/month net lens — only the net matters |
| 3 | 4  | email | Never miss a hot deal — the buy box |
| 4 | 7  | SMS   | Short nudge — see a scored deal this week? |
| 5 | 10 | email | The Monetizing Agent / second-founder angle |
| 6 | 14 | email | Traction signal (illustrative) |
| 7 | 21 | SMS   | Final — book-a-call CTA with calendar link |

Copy lives in `campaign.py`, written to Eva's voice DNA and validated against the
`content-engine` banned-word list (`validate_touches()`). Touches 3–7 carry a
book-a-call / reply CTA. The booking-link placeholder is substituted from the
calendar the build creates.

## Part 2 — the capture loop

`POST /lead/capture` → upsert GHL contact → tag `eva-acquisition` → pipeline stage
**Lead** → enroll in the campaign workflow → write `lead_captured` to the local
ledger AND emit to the Eva State Ledger.

`POST /lead/webhook` maps inbound GHL events to lead lifecycle events:

| GHL event (examples) | Eva event |
|---|---|
| `email_opened`, `reply`, `sms_reply` | `lead_engaged` |
| `email_sent`, `sms_sent` | `touch_sent` |
| `appointment_booked`, `call_booked` | `demo_booked` |
| `appointment_showed`, `call_completed` | `demo_held` |
| `opportunity_won`, `won` | `closed` |

Events flow to the **Eva State Ledger** (`modules/eva-state`, port 8769) with
`source_surface="ghl-agent"` and `project="Eva Acquisition"`, so the Command
Center and Project Map see the acquisition timeline. If the ledger is down, the
capture still succeeds locally (the emit returns an honest `ok:false`).

## Architecture

Matches the governed sibling modules (`monetizing-agent`, `eva-state`):

- `main.py` — FastAPI app on :8782.
- `service.py` — orchestration (funnel build + capture loop + webhook).
- `ghl_client.py` — GoHighLevel behind a `GHLClient` **Protocol**. `HttpGHLClient`
  (live, `httpx` or stdlib `urllib`) and `StubGHLClient` (offline). Authorization
  uses the static **Location API Key** (`GHL_ACCESS_TOKEN`) as the primary path
  (a `401` there emits `ghl_api_failed` and fails clean — no refresh, no loop);
  the OAuth token provider is used only when an `ghl.oauth` refresh token is set.
- `oauth.py` — optional GHL OAuth 2.0 token provider (`GHLTokenProvider`).
  Config-file-primary creds (`ghl.oauth`), self-refreshing `access_token` cached in
  memory + SQLite, preemptive refresh (<60s), and the `401` → refresh → retry seam.
  Offline-safe.
- `campaign.py` — the 7-touch voice-DNA sequence + validation.
- `state_client.py` — the Eva State Ledger emitter behind a `StateLedgerClient`
  Protocol (`HttpStateLedgerClient` / `StubStateLedgerClient`).
- `memory.py` — own SQLite (`ghl_agent.db`) with two **append-only** ledgers
  (`lead_events`, `funnel_artifacts`): immutable identity columns, DELETE blocked,
  corrections-as-new-events.
- `cli.py` — terminal-first CLI.
- `tests/` — offline, stub-only.

### The append-only ledgers

`lead_events` and `funnel_artifacts` mirror the `eva-state` / `monetizing-agent`
pattern: identity/content columns are frozen by an immutability trigger, DELETE
is blocked outright, and corrections are written as **new** events carrying
`supersedes_event_id`.

## Tests

```bash
python3 -m pytest modules/ghl-agent/         # offline, zero network
```

Covers the voice DNA, ledger immutability, build idempotency (create-then-skip +
`manual_required` fallback), the capture loop, and webhook → state-ledger emission.

## GHL API base

GoHighLevel has two API generations. This module targets the current **v2 /
LeadConnector** base — `https://services.leadconnectorhq.com` — with Bearer
tokens (a Location API Key, or an OAuth access token) and the
`Version: 2021-07-28` header. The legacy **v1** base
(`https://rest.gohighlevel.com/v1`) is deprecated and not used. Since the primary
auth is a v2 Location API Key, v2 is the correct base.

## Known GHL API Limitations

The GoHighLevel public API does not expose everything its UI does. Where an
endpoint is missing or restricted, this module **degrades gracefully** — the
build records the piece as `manual_required` (with a reason) instead of failing —
so the rest of the build still completes.

| Piece | API status | Fallback |
|---|---|---|
| **Workflow creation** | **UI-only.** The v2 API is read-only for workflows (you can list them, not create them). | The build returns `manual_required` for the workflow. Create it once in the GHL UI: trigger = *Contact Tag added* `eva-acquisition`, then add the 7 timed email/SMS steps. After that, capture auto-enrolls contacts by tag. |
| **Email/SMS template creation** | **Often UI-only** (varies by plan; the public builder API is limited). | Copy is generated by `campaign.py` (voice-validated). Paste each touch into a GHL template/campaign step. `python3 cli.py campaign` prints all 7. |
| **Pipeline creation** | Not exposed on the public v2 API on most plans. | The stub creates it offline; the live client attempts `POST /opportunities/pipelines` and falls back to `manual_required` if the plan disallows it. Create the pipeline + 5 stages in the UI if needed. |
| **Calendar creation** | Supported on most plans via `POST /calendars/`. | Created via API; the booking link is returned. Falls back to `manual_required` on failure. |
| **Custom fields** | Supported via `POST /locations/{id}/customFields`. | Created via API. |
| **Contact upsert / tags / opportunities / workflow enrollment** | Supported (`/contacts/upsert`, `/contacts/{id}/tags`, `/opportunities/`, `/contacts/{id}/workflow/{wfId}`). | Used directly by the capture loop. |

### What still needs manual browser setup in GHL

On a typical plan, after running `POST /funnel/build`:

1. **The workflow** — create once in the UI (tag-triggered on `eva-acquisition`)
   and add the 7 timed steps using the copy from `cli.py campaign`.
2. **The templates** — if your plan's template API is UI-only, paste the 7 touch
   bodies into GHL template/campaign steps.
3. **The pipeline** — only if your plan disallows API pipeline creation.

`/funnel/build` reports exactly which of these came back `manual_required`, so the
list is never a guess.
