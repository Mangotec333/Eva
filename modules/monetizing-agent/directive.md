# Monetizing Agent — Live Directive

version: 0.1.0
status: active
updated_at: 2026-07-09

## Purpose

The weekly revenue-leak detector. Every Sunday it mines all connected activity
streams, finds under-monetized assets and signals, ranks them by cash proximity,
and converts the top opportunities into concrete next-week actions — packaged and
gated behind a very brief pithy Sunday brief. It is the governed successor to the
Yaksha cron prototype (`modules/angels/angel3_monetization/`, now DEPRECATED):
same intent, but a full autonomous-agent microservice with an approval gate, an
append-only ledger, a swap-and-play brain, and a learning loop.

## The Pattern: Mine → Match → Package → Route → Follow-up

1. **Mine** every connected source (GHL, Drive/Docs, GitHub, Slack, gcal,
   finance, waitlist, own memory). Sources sit behind a `SignalSource` Protocol;
   the sandbox uses a deterministic Stub.
2. **Match** each mined signal to exactly one of nine plays.
3. **Package** it into a concrete artifact (drafted SMS/email, pipeline move,
   proposal doc, contact list, landing tweak, or a human-only task) — never a
   vague suggestion.
4. **Route** it to where it belongs (GHL pipeline, Drive KB, Slack task) via the
   ledger + execution transport.
5. **Follow-up**: next Sunday, check whether last week's plays moved cash and
   feed the signal back to recalibrate scoring.

## The 9-play playbook

Reactivate · Upsell · Outreach · Productize · Revive · Referral ·
Content-to-offer · Retainer · White-label/resale.

## Scoring model (0–100 composite)

| Dimension | Weight |
|---|---:|
| Cash Proximity | 35% |
| Effort | 20% |
| Strategic Fit | 20% |
| Reusability | 15% |
| Urgency | 10% |

The deterministic scorer (`playbook.py`) is authoritative and FREE. The brain
(`brain.py`) only sharpens packaging copy on top — it never changes scores.

## Operating Rules

1. **Approval-gated now, learning-based autonomy later.** A fresh brief is
   `pending-approval`; nothing irreversible executes until the brief is approved.
2. **Every irreversible action goes through the approval gate** and then a single
   execution transport chokepoint. Stubs never fake success.
3. **Append-only ledger.** Every packaged play is written to `monetization_plays`
   with an immutability trigger; only lifecycle columns (status/executed_at/
   outcome) may transition.
4. **No cross-agent DB reads.** Cross-agent knowledge flows via the directive-sync
   bridge (`services/directive_sync.py`), never by reading a sibling's SQLite.
5. **KB every scan.** Write a markdown revenue brief and index it into the Eva
   Master Index doc.
6. **Read `docs/MISSION.md` and `docs/CURRENT_GOALS.md` at startup** if present
   (graceful no-op if absent).

## The Sunday brief (format)

One line per play, a last-week feedback block, ending with
`Reply "go" to execute all, or edit the list.`

## Cadence

Every Sunday 7:00 AM PT → mine + score + package + brief. Vineet approves →
execute by EOD Sunday / Monday.

## LEARNINGS (auto-synced)

<!-- Appended by services/directive_sync.py as play outcomes arrive. Each entry
     captures the source, play, outcome, lesson, and any proposed weight_delta. -->
