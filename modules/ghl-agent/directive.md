# GHL Agent — Live Directive

version: 0.1.0
status: active
updated_at: 2026-07-10

## Purpose

The single Eva-owned service that talks to GoHighLevel. It owns the entire
GoHighLevel integration end-to-end so no other module reaches into GHL directly.
It does two jobs:

1. **One-time campaign/funnel build (Part 1).** Idempotently create the
   "Eva Acquisition" pipeline, the "Eva Demo Call" calendar, the `source` custom
   field, the 7-touch email/SMS templates, and the tag-triggered workflow.
2. **Ongoing lead-capture automation loop (Part 2).** Capture leads into the
   funnel, receive GHL webhooks, and write every lead-lifecycle event to the Eva
   State Ledger so the whole system shares one timeline.

## The one-time build (idempotent — check-then-create)

- Pipeline **Eva Acquisition**: Lead → Engaged → Demo Booked → Demo Held → Closed.
- Calendar **Eva Demo Call** (book-a-call) → returns the booking link.
- Custom field **source** = `eva-acquisition`.
- 7-touch sequence over 21 days (see below), as email/SMS templates.
- Workflow that fires the sequence when a contact is tagged `eva-acquisition`.

Every piece is checked against GHL before creation and recorded in the
append-only `funnel_artifacts` ledger. Pieces GHL exposes only in its UI
(workflow creation; template creation on many plans) degrade to
`manual_required` and never fail the whole build.

## The 7-touch sequence (voice DNA)

| # | Day | Channel | Angle |
|---|----:|---------|-------|
| 1 | 0  | email | Intro — the manual scanning ends here |
| 2 | 2  | email | The $10K/month net lens — only the net matters |
| 3 | 4  | email | Never miss a hot deal — the buy box |
| 4 | 7  | SMS   | Short nudge — see a scored deal this week? |
| 5 | 10 | email | The Monetizing Agent / second-founder angle |
| 6 | 14 | email | Traction signal (illustrative) |
| 7 | 21 | SMS   | Final — book-a-call CTA with calendar link |

Copy is written to Eva's voice DNA (short sentences, one idea per line, quiet
confidence, never sell — demonstrate) and validated against the content-engine
banned-word list. Touches 3–7 carry a book-a-call / reply CTA.

## The capture loop

`POST /lead/capture` upserts the GHL contact (email or phone required), tags it
`eva-acquisition`, adds it to the pipeline at stage **Lead**, and enrolls it in
the campaign workflow. `POST /lead/webhook` maps inbound GHL events to lead
lifecycle events: `lead_captured`, `touch_sent`, `lead_engaged`, `demo_booked`,
`demo_held`, `closed`. Both surfaces write to the local append-only ledger and
emit to the Eva State Ledger (port 8769).

## Governance

- OAuth token from env `GHL_ACCESS_TOKEN` only — never hardcoded.
- GHL access sits behind the `GHLClient` Protocol; the sandbox and tests use a
  network-free stub. The state-ledger write sits behind `StateLedgerClient`.
- `lead_events` and `funnel_artifacts` are append-only (immutability trigger,
  DELETE blocked, corrections-as-new-events).
- Offline by default when no token is present; set `EVA_GHL_OFFLINE=1` to force
  stubs.
