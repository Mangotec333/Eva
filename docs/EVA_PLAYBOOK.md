# Eva Acquisition — Playbook v1

> Source of truth for the acquisition data + monetization strategy. Finalized 2026-07-14. Owner: Vineet. Lives in Eva repo `docs/` + Google Drive.

## Database stack
- **Primary:** PostgreSQL (`infra/init/postgres/01_schema.sql`) — `TIMESTAMPTZ` on every row, `JSONB` for flexible fields, `pgvector` extension for embeddings.
- **Vector layer:** Qdrant — embeddings synced (Layer 2 semantic search).
- **Local/dev:** SQLite via `infra/migrate_sqlite.py`.

## Data directives (locked this session)
1. **Collect ALL deal scans.** Every listing Eva scans is persisted to `deals` (timestamped `created_at`) — not just the final top 3. The top 3 are the surfaced output for the user; the full long tail is the dataset.
2. **Harvest closed deals online.** Actively scan for already-closed/sold listings on each source to seed historical outcome data (original asking, multiple, time-to-close). This builds the outcome dataset retroactively, not just prospectively.
3. **Outcomes via listing-status polling.** Re-check each tracked listing periodically; record the transition to closed/unavailable. Outcome = closed-vs-not + time-to-close + original asking/multiple. Works across every marketplace (they all flip listings to "sold").
4. **Persist scores.** Scout's scores + params go to a `deal_scores` table, not just a run output.

## Schema additions (migration — apply on Mac)
- `deals`: add `listing_status` (available/under_contract/closed/unavailable/removed), `closed_at`, `last_checked_at`, `close_observation_source`.
- New `deal_scores` (deal_id FK, score, params JSONB, scored_at).
- New `deal_status_history` (deal_id FK, listing_status, observed_at) — the outcome audit trail.

## Deal sources
Keep e-comm (Empire Flippers/Flippa/VestedBB) + add M&A (BizBuySell, broker listings, RCFE/senior-living).

## Monetization ladder (free → trust → paid)
1. **Free attract:** whitepaper ✓, weekly 3-deals digest, buy-box scorecard.
2. **Free engage (trust wedge):** Free Deal Audit — submit 1 listing → Eva scores → 1-page report, one time free. Saves the deal to the dataset + enrolls the lead in 7-touch.
3. **Paid (LATER):** engine subscription (monthly recurring) first → custom deploy (one-time) as upsell once hooked.
4. **Continuity (LATER):** paid M&A Trends Report.

Principle: free until the magnet has done its job and the customer trusts us; monetize after.

## 4-week plan (now)
- Run all free lead magnets for 4 weeks.
- Keep talking to people; validate interest.
- Collect emails + deal scans + outcomes throughout.

## Backlog gating
- **M&A Trends Report = BACKLOG.** Build only AFTER (a) **100 emails collected** AND (b) interest/monetization validated via conversations.
- Reassess at the 4-week mark. Do not build paid tiers before then.

## Status
- Whitepaper 01 + landing gate: built, committed (pending Mac Vercel deploy + ghl-agent token swap).
- ghl-agent: 401-ing (token not swapped) — fix on Mac ASAP (live captures being lost).
- Free magnets to build next: weekly 3-deals digest, buy-box scorecard, free deal audit.
- Data directives: spec locked; implementation (migration + poller + closed-deal harvester) next.
