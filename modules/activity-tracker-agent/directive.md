# Activity Tracker Agent — Directive

**Port:** 8794 · **Role:** ops · **Slug:** `activity-tracker-agent`

## Purpose

One-army discipline: time and resources are the scarcest input, so every
day gets logged, monitored, and course-corrected — not just worked through
on instinct. This lobe reads the shared eva-state ledger every other lobe
already writes to, buckets the day's activity by project, and answers three
things every EOD:

1. **Where did effort actually go today** (event-count per project — see
   Effort proxy below), bucketed by track.
2. **What patterns are recurring** — stuck/blocked projects (repeat
   `task_stalled` / `revenue_leak_found` / `deploy_failed`-shaped events),
   and high-activity projects producing zero revenue signal.
3. **Is there revenue traction to double down on** — a real revenue-shaped
   event (`deal_closed`, `payment_received`, `invoice_paid`,
   `subscription_started`, `lead_converted`, `revenue_milestone`,
   `deal_funded`, or a payload with a positive `revenue_amount`/`amount`/
   `deal_amount`/`mrr_delta`/`payment_amount`). If found: the digest's
   explicit recommendation is to leave lower-leverage work, reallocate time
   there first, and arrange a team around it based on what it needs — this
   is the standing "if we see traction that can be monetized, double down"
   directive, made mechanical instead of relying on memory.

Findings are written back to eva-state (`activity_digest_ready` always,
`revenue_traction_detected` on double-down, `activity_red_flag` when the
day drifted off-thesis or logging went dark) so Diracatron and every other
lobe see this on the same shared timeline — no side channel.

## Effort proxy (stated honestly, not hidden)

This module has **no real time-tracking input** yet — no calendar, no
screen-activity feed. "Effort" here is a proxy: **event_count per project**
in the eva-state ledger for that day. This is explicit in every digest and
in the code (never labeled "hours" or "minutes" anywhere). A future upgrade
path is wiring context-api's raw activity feed in as a second, real signal
— this module's `engine.py` already isolates bucket-building so that swap
is additive, not a rewrite.

## No-circularity rule (mirrors trend-agent / idea-generator-agent)

Every bucket, pattern flag, and revenue signal is derived from events the
service actually read from eva-state that day — never asserted first and
back-filled. A day with zero eva-state events is reported as a logging gap
("cannot verify where time went"), not silently treated as a clean/OK day.
Goal-track share below 35% (mirrors idea-generator-agent's alignment
threshold) is a RED_FLAG on its own, independent of any pattern found.

## Status ladder

- **DOUBLE_DOWN** — a revenue-side event fired today. Highest priority;
  overrides RED_FLAG/WATCH even if other things also look off, because the
  standing directive is "leave everything else" when this happens.
- **RED_FLAG** — zero activity logged today, or goal-track share < 35%.
- **WATCH** — no revenue signal, but a project logged high activity
  (≥5 events) with zero revenue movement — busy without progress.
- **OK** — normal day, nothing above triggered.

## Diracatron wiring

- `KIND_REVENUE_TRACTION` (`revenue_traction`) — priority 90, just under
  `KIND_THESIS_REFUTED` (92). Reflects "leave everything else and double
  down" urgency without outranking a refuted macro thesis.
- `KIND_ACTIVITY_DIGEST` (`activity_digest_ready`) — priority 45,
  informational EOD summary.
- Both route to `idea-generator-agent:8793 /idea/review` — reusing the
  existing human/EVA review queue surface rather than building a second one.

## Offline / test posture

`EVA_ACTIVITY_OFFLINE=1` stubs the eva-state client and skips Slack — no
network. `EVA_ACTIVITY_NO_LOOP=1` disables the daily background thread
(`loop.py`) so tests never wait on real time. `EVA_ACTIVITY_DB_PATH`
overrides the sqlite digest-history path for isolated test runs.

## Endpoints

- `GET /health` — module status
- `GET /directive` — this file
- `POST /activity/run` — run today's (or `{"date": "..."}`'s) digest now
- `GET /activity/today` — today's digest (runs it if not already run)
- `GET /activity/history?limit=` — past digests, newest first
- `GET /activity/{date}` — one day's digest
- `POST /activity/review` — Diracatron dispatch target; ack-only, never
  auto-reallocates or auto-spends anything on its own
