# Idea Generator Agent — Directive

**Port:** 8793 · **Role:** strategy · **Slug:** `idea-generator-agent`

## Purpose

Every new venture/product idea gets scored against two things at once, never
in isolation:

1. **The goal.** Storeys RE PE fund (senior-living / healthcare real estate)
   + Mangotec AI-agency revenue, per command-center's $10K/mo threshold.
2. **The existing portfolio.** Does it leverage what Eva already owns and
   operates (RCFE deal pipeline, Eva/Mangotec AI tooling, content-engine,
   GHL, Shopify, brand-builder, etc.) — or does it require building a new
   stack from zero?

The output is a computed **BUILD / PARTNER / WATCH / PASS** recommendation,
an **acquire-instead-of-build** flag when relevant, and a set of devil's-
advocate flags. Findings are written to the shared eva-state ledger so every
other lobe — Diracatron included — sees them on the same timeline. This is
the "Spain soccer team" sync surface: no separate framework, no side
channel.

A second capability runs **daily**: a system-wide alignment/red-flag digest
that reads recent eva-state activity and asks "is our actual time/effort
still converging on the goal, or has it drifted?" — independent of any
single idea.

## No-circularity rule (mirrors trend-agent / deal-financing-agent)

Sub-scores (goal_alignment, portfolio_synergy, market_demand, effort,
revenue_potential) are evidence-first inputs supplied by the caller (a
human, a research subagent, or another lobe). The engine only *computes*
the composite score, recommendation, and flags from them — it never
back-solves a verdict it already believed going in. If demand or synergy is
asserted without sources/counter-notes, the engine flags it as unverified
rather than trusting it.

## Scoring formula

```
composite = goal_alignment*0.25 + portfolio_synergy*0.25 + market_demand*0.20
            + (10 - effort)*0.15 + revenue_potential*0.15
```

Alignment and portfolio fit are weighted heaviest on purpose — an idea that
scores well on demand/revenue but drifts from the thesis or from what we
already own is exactly the shiny-object trap this agent exists to catch.

| Composite | Portfolio synergy | Recommendation |
|---|---|---|
| >= 7.5 | >= 6.0 | **BUILD** — leverages what we own, in-house |
| >= 7.5 | < 6.0 | **PARTNER** — good idea, needs an outside operator |
| 5.5 – 7.5 | any | **WATCH** — monitor, revisit, not urgent |
| < 5.5 | any | **PASS** |

**Acquire-instead-of-build nod** (mirrors deal-scout's buy-vs-build logic):
`effort_score >= 8` AND `market_demand_score >= 7` sets `acquire_candidate =
true` — check deal-scout for an existing operator to acquire in that
category instead of building from scratch.

## Devil's-advocate flags (computed, not asserted)

- **Unverified demand** — `market_demand_score >= 6` with no `demand_sources`.
- **No counter-thesis** — no `counter_notes` supplied; nothing has actually
  stress-tested the idea yet.
- **Shiny-object risk** — `portfolio_synergy_score >= 7` and
  `goal_alignment_score <= 4`: leverages our tools but drifts from the
  mission. This is the exact pattern to raise a RED flag on immediately.
- **Alignment/synergy gap** — any |gap| >= 3.0 between synergy and alignment.
- **Capacity risk** — BUILD/PARTNER call with `effort_score >= 8`: confirm
  capacity exists; this competes directly with Storeys deal flow and Eva
  build time.

## Daily alignment / red-flag digest

Reads eva-state events over a trailing 7-day window (configurable), buckets
by `track`, and computes the fraction of activity in the goal tracks
(`real_estate`, `ai_agency`).

| Goal-track share | Status |
|---|---|
| >= 50% | OK |
| 35% – 50% | WATCH |
| < 35% | **RED_FLAG** |

Also RED_FLAGs if 3+ BUILD/PARTNER idea calls in the window scored
`portfolio_synergy_score < 6` — a pattern of chasing ideas that don't
leverage what we already operate.

On RED_FLAG: emits `alignment_red_flag` to eva-state AND sends a best-effort
Slack alert (reuses `modules/social-publish/slack_client.py` — never
duplicated). Runs automatically once per 24h via `AlignmentLoop`
(`EVA_IDEA_NO_LOOP=1` to disable, `EVA_IDEA_OFFLINE=1` for the sandbox
default).

## Plugging into Diracatron (existing orchestrator, not a new framework)

Per explicit "plug into existing (reuse)" decision — this agent does not run
its own separate triage; it writes events, and Diracatron's `diracatron.py`
picks them up:

- `idea_scored` -> `KIND_IDEA_SCORED` (priority 55, bumped by composite score)
- `alignment_red_flag` -> `KIND_ALIGNMENT_FLAG` (priority 95 — nearly as
  urgent as a human waiting, because misallocated effort compounds daily)
- Both route to `idea-generator-agent:8793 /idea/review` — an L1-autonomy
  acknowledgment endpoint. Dispatch never auto-builds or auto-acquires
  anything; a human/EVA decision still gates any BUILD/PARTNER/ACQUIRE call.
- Routine `idea_flag_raised` and non-red `alignment_digest` events are
  intentionally NOT mapped in Diracatron — only an actual scored idea or a
  real RED_FLAG interrupts the triage queue.
- Registered as a lobe in `modules/triage-brain/agent_registry.json` and in
  `modules/launcher/eva_launcher.py`'s `SERVICES` table.

## Endpoints

| Method | Route | Purpose |
|---|---|---|
| GET | `/idea/health` | module status |
| POST | `/idea/score` | score one idea, persist + emit to eva-state |
| GET | `/idea/runs` | scored-idea history (`?idea_id=`) |
| POST | `/idea/alignment/run` | trigger the alignment digest now |
| GET | `/idea/alignment/history` | past digest runs |
| POST | `/idea/review` | Diracatron dispatch ack (no autonomous action) |

## Framework-first scope (explicit user decision)

This pass builds and tests the scoring engine + registry wiring only. The 5
real ideas (traveling-fitness-coach marketplace, group-fitness marketplace,
5%-body-fat video analytics, goal/nutrition workout video analytics, retail
foot-traffic video analytics) are scored in a **separate follow-up pass**
once this framework is confirmed working — not in this commit.

## Open item raised, not yet decided

`trend-agent` (port 8788, macro thesis stress-testing) currently runs
standalone and is not yet registered as a Diracatron lobe. Given the "plug
into existing" philosophy applied here, the same wiring (KIND/ROUTES/
EVENT_KIND + registry entry) would make sense for it too — flagged for the
user to confirm, not assumed.
