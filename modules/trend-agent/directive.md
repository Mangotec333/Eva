# Trend Agent — Live Directive

version: 1.1.0
status: active
updated_at: 2026-07-22

This module now runs two independent modes. Mode 1 (original) stress-tests
macro/strategic theses about durable industries. Mode 2 (new, 2026-07-22)
scans top apps/SaaS/marketplace listings across venture-aligned categories
for short-term revenue opportunities (clone / acquire / white-label). They
share the module's conventions (FastAPI service, sqlite memory, deterministic
engine + upstream-research-as-case-JSON, StateLedgerClient emission) but are
otherwise unrelated pipelines — read the mode-specific section you need.

## Mode 1: Sector Durability Thesis Stress-Test

### Purpose

Stress-test macro/strategic theses about which industries are durable over a
multi-year horizon, given exponential forces (AI, healthcare shifts,
crypto/digital assets, demographics, climate). Produces a ranked, sourced
durability scorecard and an explicit verdict (SUPPORTED /
PARTIALLY_SUPPORTED / REFUTED) — never a vibes-based conclusion.

Origin case: testing the thesis that society always converges to five
basic-needs industries — FOOD, WATER, SHELTER, EDUCATION, HEALTHCARE —
regardless of currency, inflation, or AI disruption, and that AI should be
treated as a tool serving those sectors rather than the investment target
itself. See `cases/basic_needs_2026.json` for the first run.

### When EVA should invoke this agent

- Before allocating capital, building a new product line, or evaluating an
  acquisition outside the current core (RCFE/senior-living real estate, AI
  agent tooling) — check sector durability first.
- Periodically (recommend: every 2 quarters, or immediately after a major
  macro shock — new AI model release with material capability jump, Fed
  policy shift, major crypto regulation, healthcare policy change) — re-run
  with updated sub-scores to see if the verdict has moved.
- When a new venture idea surfaces that claims to be "recession-proof" or
  "AI-proof" — run it through this agent's framework before believing it.

### No-Circularity Rule (permanent, non-negotiable)

The engine must NEVER assume a verdict (SUPPORTED/REFUTED) and back-solve
sub-scores to match it. The chain is strictly one-directional:

    research evidence (cited sources)
        -> historical_resilience_score, ai_disruption_exposure_score,
           structural_demand_score (0-10 each, per sector)
    weighted formula (trend_engine.durability_score)
        -> durability_score per sector
    aggregate + threshold rule (trend_engine.thesis_verdict)
        -> verdict + confidence (COMPUTED, never asserted going in)

If a case file shows scores that were reverse-engineered to produce a
pre-decided verdict, that case has this circularity bug and must be
re-sourced from evidence, not reused as a pattern.

### Data Inputs — provenance required

Every sector assessment must cite its sources (research reports, government
data, academic studies — see `sources` field on `SectorAssessment`). Do not
fabricate a score — if evidence is thin for a sub-score, say so in
`counter_thesis_notes` rather than inflating the number.

### Scoring Rule

`durability_score = historical_resilience*w1 + (10 - ai_disruption_exposure)*w2 + structural_demand*w3`

Default weights: `(0.35, 0.35, 0.30)` — historical resilience and AI
disruption resistance weighted equally and heaviest, structural demand
slightly lighter (structural drivers are the least certain over a 10-year
horizon). Weights are configurable per run via `ThesisRunInput.weights` but
must sum to 1.0 and any deviation from default must be justified in
`source_notes`.

Verdict thresholds (default `pass_threshold=6.5`):
- **SUPPORTED**: avg durability >= threshold AND no sector's score is more
  than 1.5 below the threshold (a thesis claiming multiple sectors are all
  durable fails if even one is not — weakest link matters).
- **PARTIALLY_SUPPORTED**: avg is at/near threshold but with meaningful
  dispersion between sectors, or avg is within 1.0 below threshold.
- **REFUTED**: avg more than 1.0 below threshold.

### Engine (trend_engine.py)

- `durability_score()` — pure weighted-average function, inverts AI exposure
  before weighting.
- `rank_sectors()` — scores + sorts a list of `SectorAssessment` into ranked
  `SectorScore`.
- `thesis_verdict()` — derives verdict + confidence label from avg/min score
  vs. threshold.
- `run_thesis_model()` — orchestrates the above into `ThesisRunResult`, and
  raises `flags` for anything a human should double check (sector AI
  exposure >= 6.5, structural demand <= 4.0, wide score dispersion across
  sectors).

### Operating Rules

1. Deterministic scoring only in v1 — no LLM call in the compute path. The
   qualitative research that produces sub-scores happens upstream (EVA
   research subagent / Perplexity), and is supplied as case JSON with
   sources. This keeps the composite math auditable and prevents the
   verdict from silently drifting with model mood.
2. Every run is persisted (`memory.py` -> `memory.db`, table `trend_runs`)
   for audit and trend-of-trend tracking (did the verdict get stronger or
   weaker across quarterly re-runs?).
3. Sub-scores must trace to `sources` URLs. A sector assessment with no
   sources is a draft, not a finding — flag it before acting on it.
4. Counter-thesis evidence (`counter_thesis_notes`, `counter_thesis_points`)
   is mandatory, not optional. A sector run with zero counter-evidence
   listed has not actually been stress-tested — treat that as a red flag on
   the research, not a clean bill of health.

### Run 1 result (2026-07-20) — see cases/basic_needs_2026.json and
cases/basic_needs_2026_result.json for full detail

Thesis: Food / Water / Shelter / Education / Healthcare are durable
basic-needs industries regardless of AI/crypto/currency disruption; AI is a
tool serving them, not the target.

**Verdict: PARTIALLY_SUPPORTED (confidence: MEDIUM)** — avg durability
6.81/10, min 3.45 (Education), max 7.77 (Water). The engine-computed verdict
matches the independent qualitative read in the source research report,
which is a good cross-check signal (deterministic scoring didn't diverge
from the narrative analysis).

Ranked durability scorecard:

| Rank | Sector | Historical Resilience | AI Exposure (lower=better) | Structural Demand | Durability |
|---|---|---|---|---|---|
| 1 | Water | 6.5 | 2.0 | 9.0 | 7.77 |
| 2 | Food | 8.5 | 3.5 | 8.0 | 7.65 |
| 3 | Healthcare | 9.0 | 5.0 | 9.0 | 7.60 |
| 4 | Shelter | 6.0 | 2.5 | 9.5 | 7.57 |
| 5 | Education | 4.5 | 8.5 | 4.5 | 3.45 |

Flags raised: Education AI-exposure 8.5/10 (re-underwrite sub-vertical mix);
wide dispersion between strongest (Water) and weakest (Education) sector —
thesis is sector-dependent, not uniformly true.

See the accompanying research report
(shared with the user 2026-07-20 as "Basic-Needs Thesis Stress Test
(10-Year Outlook)") for the full sourced sector-by-sector analysis, macro
outlook, and counter-thesis stress test that fed this run's `sources` and
sub-scores.

---

## Mode 2: App Category Scan

### Purpose

Scan the top apps / SaaS products / acquirable marketplace listings within
categories aligned to the current venture portfolio, study what need each
serves and what gap or weakness it leaves open, and flag which ones are
"worth a second look" — meaning a clone, white-label, or straight acquisition
could plausibly generate revenue on a short (weeks-to-months) horizon. This
is explicitly NOT a broad app-store trends survey: every category must map
to an active venture, and the output optimizes for near-term cash flow, not
long-run market sizing.

### Tracked categories (vertical-aligned, not a general survey)

| Category | Vertical alignment |
|---|---|
| AI Agent / Autonomous Assistant Platforms | EVA (white-label AI agent platform) |
| Senior Living / RCFE Operations & Care Management Software | Storeys (RCFE / senior-living real estate operations) |
| Real Estate Investment Analysis, Underwriting & Deal/DSCR Modeling Tools | Storeys (Fund I underwriting) |
| Healthcare Commercial Real Estate Technology Platforms | Storeys (Healthcare Commercial Real Estate) |
| Local Service Business Marketing & All-in-One CRM Platforms (GoHighLevel Competitors) | AI Growth Agency |
| Acquirable SaaS / Apps for Sale ($10K-$300K range) | Digital Acquisition Business |

Each category tracks exactly 10 apps (`AppEntry.rank` 1-10), spanning mobile
apps, SaaS/web products, and acquirable marketplace listings
(`platform_type`: `mobile_app` / `saas_web` / `marketplace_listing`) per the
user's explicit "all of the above" scope decision. Categories may be added
or swapped as the venture portfolio changes, but the count must stay
aligned to active ventures, not expand into a generic trends feed.

### Cadence

Monthly, scheduled (see `launchd/com.eva.trend-agent-appscan.plist`,
1st of month). Unlike Mode 1's quarterly-or-macro-shock cadence, Mode 2 runs
monthly because app/SaaS/marketplace listings turn over fast enough that a
quarter is too long a gap for a short-term-revenue mandate.

### "Worth a second look" — definition

An app is flagged `worth_second_look=true` only when the research evidence
supports at least one of:

1. **Buildable gap** — a named, specific missing feature or channel
   (e.g. "no Stripe rebilling", "missing SMS/voice", "single asset-class
   only") that a small team could plausibly ship in weeks, not quarters.
2. **Underpriced/underexploited acquisition** — a marketplace listing
   trading at a low multiple (sub-1x-3x revenue) relative to disclosed
   revenue/profit, or with a large, quantifiable unmonetized asset (email
   list, registered-user base) that a buyer could activate quickly.
3. **Validated-but-thin niche** — real, sourced evidence of unmet demand
   (e.g. a marketplace with real listings but no transaction/booking layer)
   where the core product is simple enough to be a fast follow.

Apps are explicitly marked NOT worth a second look when they sit behind a
deep, hard-to-replicate moat (owned infrastructure, 20+ year data moats,
deep app-store/ecosystem lock-in, capital-intensive hardware/regulatory
drag) — being a good product is not sufficient; the bar is "can this
realistically be cloned, acquired, or fast-followed for near-term revenue."
A category and its `research_synthesis` must state the reasoning for every
NO, not just every YES — silent omissions are a research-quality flag.

### Data provenance rules (same philosophy as Mode 1)

- Every `AppEntry` must carry `sources` — real fetched URLs, never filled
  from memory. An app entry with an empty `sources` list is a draft, not a
  finding.
- The engine (`app_scan_engine.py`) is purely deterministic aggregation of
  already-sourced case JSON — it does not decide `worth_second_look` itself;
  that judgment call is made upstream during research and must be
  justified per-app in `second_look_reason`.
- No-circularity applies here too: `priority_rank` must follow from the
  strength of the `second_look_reason` evidence, never be assigned first and
  then rationalized.

### Engine (app_scan_engine.py)

- `_opportunity_tier(ratio)` — maps a category's second-look ratio to
  HIGH (>=0.5) / MEDIUM (>=0.2) / LOW (<0.2), so the module can flag which
  categories deserve the most short-term-revenue attention this cycle.
- `score_category()` — counts second-look apps in a `CategoryAppScan`,
  computes the ratio and tier, and returns the filtered second-look list.
- `run_app_scan()` — orchestrates all categories into an
  `AppScanRunResult`: total apps scanned, total second-look apps, a
  cross-category `top_priority_picks` list (sorted by `priority_rank`,
  apps without a priority_rank excluded), and `flags` for HIGH-tier
  categories (prioritize) and zero-second-look categories (deprioritize).

### Operating Rules

1. Deterministic aggregation only — same as Mode 1, the qualitative
   app-by-app research happens upstream (Perplexity wide-search / EVA
   research subagent) and is supplied as case JSON
   (`cases/app_scan_YYYY-MM.json`). `run_app_scan.sh` looks for the current
   month's case file by naming convention and fails loudly (with a clear
   message) if the upstream research hasn't been produced yet, rather than
   silently reusing stale data.
2. Every run is persisted (`memory.py` -> `memory.db`, table
   `app_scan_runs`) for month-over-month tracking of which categories stay
   HIGH-opportunity vs. which cool off as competitors fill the gaps.
3. `top_priority_picks` is the action list — the cross-category ranked
   picks a human should evaluate first for near-term clone/acquire/
   white-label decisions, not just a restatement of every second-look app.
4. Because this mode surfaces acquisition targets, flag (don't silently
   drop) any listing where asking price, revenue, or multiple could not be
   confirmed from a fetched source — use `"n.a."` rather than guessing.

### Run 1 result (2026-07) — see cases/app_scan_2026-07.json and
cases/app_scan_2026-07_result.json for full detail

Researched via three parallel Perplexity wide-search passes (2026-07-22)
covering all six categories, 10 apps each (60 total).

**28/60 apps flagged worth a second look.** Two categories hit HIGH
opportunity tier: AI Agent / Autonomous Assistant Platforms (6/10) and
Acquirable SaaS / Apps for Sale (8/10). The other four categories are
MEDIUM tier (0.3-0.4 ratio) — real gaps exist but are thinner per category.

Top cross-category priority picks (ranked by evidence strength):

| Rank | Pick | Category | Why |
|---|---|---|---|
| 1 | AI Agent Builder SaaS (Acquire.com listing) | AI Agent Platforms | Profitable, 229% growth, 1,000 paying subs, selling at ~0.46x revenue — buy-not-build |
| 2 | Synkwise / iOS PDF utility app | RCFE Software / Acquirable SaaS | Underserved Title-22 RCFE niche; sub-1x-multiple simple mobile codebase |
| 3 | Stammer.ai / HubSpot themes business | AI Agent Platforms / Acquirable SaaS | 1,300+ agencies validate demand but miss IG DM/voice; #1-ranked niche listing |
| 4 | Botpress / AI resume-builder SaaS | AI Agent Platforms / Acquirable SaaS | Missing Stripe rebilling layer; 30K registered users converting at only ~1.1% |
| 5 | Health Space Finder | Healthcare CRE | Medical-specific marketplace, early-stage with unproven liquidity — first-mover window |

Flags raised: AI Agent Platforms and Acquirable SaaS both flagged HIGH
opportunity tier — prioritize these two categories for immediate
clone/acquire action this cycle.

See the accompanying report (compiled from the underlying wide-search
research and shared with the user as "App Category Scan — July 2026") for
the full 60-app, 6-category breakdown with every source URL.
