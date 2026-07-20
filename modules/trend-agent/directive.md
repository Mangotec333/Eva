# Trend Agent — Live Directive

version: 1.0.0
status: active
updated_at: 2026-07-20

## Purpose

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

## When EVA should invoke this agent

- Before allocating capital, building a new product line, or evaluating an
  acquisition outside the current core (RCFE/senior-living real estate, AI
  agent tooling) — check sector durability first.
- Periodically (recommend: every 2 quarters, or immediately after a major
  macro shock — new AI model release with material capability jump, Fed
  policy shift, major crypto regulation, healthcare policy change) — re-run
  with updated sub-scores to see if the verdict has moved.
- When a new venture idea surfaces that claims to be "recession-proof" or
  "AI-proof" — run it through this agent's framework before believing it.

## No-Circularity Rule (permanent, non-negotiable)

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

## Data Inputs — provenance required

Every sector assessment must cite its sources (research reports, government
data, academic studies — see `sources` field on `SectorAssessment`). Do not
fabricate a score — if evidence is thin for a sub-score, say so in
`counter_thesis_notes` rather than inflating the number.

## Scoring Rule

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

## Engine (trend_engine.py)

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

## Operating Rules

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

## Run 1 result (2026-07-20) — see cases/basic_needs_2026.json and
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
