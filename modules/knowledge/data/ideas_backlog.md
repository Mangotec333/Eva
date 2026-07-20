# Ideas Backlog
_Last updated: 2026-07-20 | Version: 0.1 | Module: EVA Knowledge OS_

Append-only capture of venture ideas raised in conversation, ahead of formal
scoring through idea-generator-agent. Exists so no idea drops out of the
chain before it reaches a logical conclusion (score -> decision -> build or
kill) or contributes to a goal and gets saved to eva-state.

Status legend: RAW (captured, not yet scored) | SCORED (has idea-generator-agent
output) | ACTIVE (building) | KILLED (scored, rejected) | PARKED (deferred)

---

## 1. Uber for traveling fitness coach (on-demand or subscription)
Status: RAW

## 2. Uber for fitness group lessons (anyone can join, outdoor)
Status: RAW

## 3. Video analytics for personal 5% body-fat journey (workout / post-workout / body scanning)
Status: RAW

## 4. Video analytics for goal-based workouts including nutrition
Status: RAW

## 5. Video analytics for retail stores — foot traffic
Status: RAW

## 6. Local intent-based activity/events discovery ("what's happening near this zip that fits my kid's interests")
Status: RAW — added 2026-07-20

Raw intent (verbatim, condensed): as a father, wants his son to spend time
with people who uplift him and match his interests, instead of e-bike +
phone all day. Problem: activity/event info near a zip is fragmented, not
unified by interest/intent for parents.

Sub-variants raised in the same message (score separately, likely different
GTM/ICP each, same core intent-search engine):
- 6a. Parent/kid interest-matched local activities & community discovery (core ask)
- 6b. Couples date-night activity discovery (same engine, different ICP)
- 6c. Generic local marketplace for investors looking to invest (possible
  reuse of the same intent-match engine for deal/investor matching — needs
  scoping, may be its own idea rather than a variant)

Competitor space to check (kids/family): Meetup, Eventbrite, Nextdoor Events,
ActivityHero, Sawyer, Macaroni Kid, Mommy Poppins, Winnie, Peanut, ClassTag,
Outschool. Competitor space to check (investor marketplace): AngelList,
CrowdStreet, Fundrise, Republic.

User ask: market study + competitor analysis, sieve for what's buildable
quick/frugal/high-confidence, then bake as an EVA agent that EVA can invoke
autonomously at her discretion (not just on command) when she judges it
relevant to the mothership WHY.

---

## Sai/DirectShift-adjacent ideas (see modules/knowledge/data/action_items.md for full detail)
Status: RAW
1. Micro-loan financial product for DirectShift healthcare workers
2. Storeys Fund I investor pipeline via DirectShift network
3. DirectShift buyout

---

## Utility apps — gallery-derived, quick-build (scored 2026-07-20)
Status: SCORED via idea-generator-agent engine.score_idea() (offline, no LLM in compute path)

| # | Idea | Composite | Rec | Effort | Time-to-Results | Mothership | Notes |
|---|------|-----------|-----|--------|------------------|------------|-------|
| U1 | Healthcare RE Macro Terminal (Storeys investor dashboard, FRED/BLS/CMS) | 7.15 | WATCH | 3 | 8 | 5 | No prospect signal yet on format |
| U2 | Senior-Living Invest-vs-Buy Calculator (RCFE lead magnet) | 6.45 | WATCH | 3 | 8 | 4 | Overlaps existing Fund I xlsx -- check incremental value |
| U3 | DirectShift Wellness Wedge App (health dashboard, audience wedge) | 6.35 | WATCH | 4 | 6 | 7 | Only one with a real demand source (Sai). Best mothership fit. Depends on Sai distribution + SEC sign-off on the fintech half |
| U4 | Mangotec AI-Agency Capability Showcase (data-viz portfolio piece) | 6.25 | WATCH | 2 | 9 | 3 | No named prospect lined up -- build-then-hope-to-sell |
| U5 | Sports-Prediction Tool (opticodds, personal) | 3.35 | PASS | 3 | 7 | 6 | Zero business alignment, Lifestyle-bucket only |
| U6 | M&A Intelligence Dashboard (Storeys RE deal sourcing + Mangotec bolt-on/DirectShift buyout eval) | 7.35 | WATCH | 3 | 8 | 5 | Highest portfolio_synergy (9) of all 6 -- pure reuse of deal-scout/deal-analyzer logic. #2 overall |

All 6 landed WATCH or PASS -- none cleared BUILD_THRESHOLD (7.5) yet, all
sit just under it. None flagged as distraction (effort scores too low to
trip the >=6.0 floor -- that's the point of "quick/frugal" builds).
Ranking: U6 (7.35) > U1 (7.15) > U2 (6.45) > U3 (6.35) > U4 (6.25) > U5
(3.35, PASS).
U6 is the top score and cheapest-synergy pick (reuses deal-scout almost
entirely -- lowest incremental build risk). U3 remains the best mothership
fit (7) and the only one with a real named-person demand source (Sai), but
depends on his cooperation to convert to results.

---

_Next step: score all RAW ideas above through idea-generator-agent (engine
now includes mothership_alignment_score + distraction_flag, PR #35). Track
status transitions here as each moves RAW -> SCORED -> ACTIVE/KILLED/PARKED
so no idea silently drops out of the chain._
