# Retro-Agent — Live Directive

version: 0.1.0
status: active
updated_at: 2026-07-23

## Purpose

The weekly retrospective lobe — EVA's goal-drift early-warning system. Every
Monday 8:00 AM PT it reviews the prior 7 days and answers ONE question
deterministically: **did last week move the $10K/month critical path, or did it
just churn infrastructure?** It is the weekly counterpart to the daily
`activity-tracker-agent`: same no-circularity discipline, but goal-drift flavored
and reading a full week.

The founder's doctrine (Vineet): revenue first, infra second; anything Pending
more than 7 days is a stall to unstick or kill; building 30 modules while one
revenue pipeline is live is drift, not progress.

### Grounding example — the manual retro of 2026-07-23

The retro run for the week ending 2026-07-23 is the seed this agent was built to
automate. That week's manual review found:

- **Realized revenue ≈ $0** — only a symbolic $100 seed investment logged; no
  paying customer revenue.
- **batch.ai LOI stalled 7+ weeks** with no seller reply → a `STALLED_BLOCKER`.
- **Eva Morning Brief** the only pipeline row marked "LIVE — acquiring customers",
  yet its GHL pipeline, onboarding SOP, and Loom template were all Pending-HIGH.
- **30+ internal modules Active but only 1 revenue pipeline live** → infra
  outpacing revenue = `DRIFTING`.

This agent reproduces that verdict from eva-state events alone, every week,
without a human reading the timeline.

## The four lenses

Each week is bucketed into four lenses, every one **derived from eva-state
events / retro-log entries actually read** — never asserted first:

- **(a) What SHIPPED** — new/updated modules, catalog changes, GitHub commits,
  deploys, PRs. This is the infra/build signal (NOT revenue).
- **(b) Revenue-pipeline MOVEMENT** — did a Product/Revenue Pipeline row actually
  change stage (Pending→Live, a deal closed, a payment landed) vs. internal
  module churn? A `to_stage` containing live/closed/won/paid/funded/signed/
  converted — or a revenue event — is a genuine win.
- **(c) STALE blockers** — anything Pending / Needs-review / awaiting-reply for
  more than 7 days without movement, tracked across its whole open lifetime.
- **(d) Prior COURSE-CORRECTION priorities** — were last week's stated priorities
  actually worked on? Read the most recent dated entry from the **"Eva — Weekly
  Retrospective Log"** Google Doc (stub-only today, per EVA_AGENT_CATALOG.md — so
  it reads a local markdown mirror behind the same Protocol seam kb_index uses;
  swapping to live Docs later is additive, not a rewrite). A priority counts as
  "worked on" ONLY if this week's shipped/movement evidence tokens overlap it.

## Goal-drift status ladder

Precedence high → low (mirrors activity-tracker's DOUBLE_DOWN override idea):

  **REVENUE_WIN > STALLED_BLOCKER > DRIFTING > ON_TRACK**

- `REVENUE_WIN` — a pipeline row actually advanced. Headline; protect and double
  down on whatever produced it.
- `STALLED_BLOCKER` — something Pending > 7 days. Unstick or kill before new infra.
- `DRIFTING` — build/churn shipped but ZERO revenue-pipeline advanced (or no
  events at all — a verification gap, treated as drift, never a clean week).
- `ON_TRACK` — no drift, no stalls, prior priorities touched.

## No-circularity rule

Every flag, status, count, and "priority worked on?" verdict is derived from
events actually read that week — never asserted first and back-filled. A window
with **zero events read is reported as a verification gap, not a clean week.**
The deterministic engine (`engine.py`) is authoritative and FREE; the brain
(`brain.py`) only sharpens the narrative prose — it never changes a status, flag,
or count.

## Output — the Weekly Retro Digest

A structured digest (`RetroDigest`) with the status, the four lens buckets,
counts, a drift note, course-correction notes, and a human-readable narrative. It
is:

1. Written to this module's own **append-only SQLite ledger** (`memory.py`,
   immutability triggers — last week's retro is a historical fact, never
   rewritten).
2. Emitted back to **eva-state** (`retro_digest_ready` always, plus a
   status-specific `retro_revenue_win` / `retro_stalled_blocker` /
   `retro_drift_flagged`) so Diracatron and every other lobe see it on the shared
   timeline — no side channel.

## Endpoints

- `GET  /health` — module status
- `GET  /directive` — this file
- `POST /retro/run` — run the weekly retro now (optional `{"week_end": "YYYY-MM-DD"}`)
- `GET  /retro/latest` — most recent digest
- `GET  /retro/history?limit=` — past digests, newest first
- `GET  /retro/{run_id}` — one digest by id

## Cadence

Every Monday 8:00 AM PT (launchd `com.eva.retro-agent`, Monday 15:00 UTC) →
review prior 7 days → digest → persist + emit. Headless run:
`python3 main.py --run-once`.

## Operating Rules

1. **Deterministic core, optional brain.** No external LLM API is required; the
   digest is fully computed offline. The brain only sharpens prose.
2. **Offline-safe.** `EVA_RETRO_OFFLINE=1` stubs eva-state, the retro-log source,
   and the brain — no network (sandbox/test default).
3. **Append-only ledger.** Digests are immutable once written.
4. **No cross-agent DB reads.** Cross-lobe knowledge flows through eva-state, not
   by reading a sibling's SQLite.
