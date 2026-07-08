# Deal Analyzer Agent — Live Directive

version: 0.2.0
status: active
updated_at: 2026-07-08

## Purpose

Autonomously evaluate digital-business acquisition candidates and produce a
transparent, reweightable 0–10 score with per-dimension rationales. This is the
**first instance of Eva's agentic operating model**: a single Eva task, promoted
to a standalone autonomous LLM-loop microservice that learns over time.

## Standing Agentic Operating-Model Instruction (permanent)

- Every Eva task becomes a microservice agent.
- Agents are **autonomous LLM loops**: observe → reason → act → learn. They are
  not merely deterministic scripts — the deterministic core is the *substrate*,
  the LLM loop is the *operator*.
- Agents **learn over time**; this directive is a *live* document whose
  `LEARNINGS` section is appended to as outcomes arrive.
- Conversations/decisions from the parent (Perplexity Computer) feed into this
  directive via a **directive-sync bridge** (built in a later phase).
- The deterministic scoring core (`scoring_v7.py`) MUST remain fully functional
  and testable without any LLM call. The LLM adds qualitative judgement and
  enrichment synthesis *on top of* the numeric core; it never replaces it.

## v7 Scoring Methodology (summary)

Composite = weighted average of 13 axes, normalised to 0–10:

| Axis | Weight |
|------|-------:|
| cashflow | 13% |
| profit_potential (12-lever composite) | 13% |
| exit_potential | 12% |
| moat | 10% |
| tam | 9% |
| competitor_analysis (tiered L0/L1) | 8% |
| ai_proof | 8% |
| company_life | 7% |
| buy_vs_build | 6% |
| mitigation | 5% |
| owner_neglect (inverted) | 4% |
| platform_dependency_risk (inverted) | 3% |
| risk (inverted) | 2% |

Key v7 changes:
- **Taxonomy split**: legacy "Digital Products" → "Software/Digital" (higher
  multiples, higher AI-proof) vs "Physical Ecommerce" (lower multiples, platform
  risk). `category_v2` is derived by `migrate_category()`.
- **exit_potential_score**: category revenue-multiple ceiling (60%) + headroom
  from current entry multiple (40%). Moat is deliberately excluded (defensibility
  ≠ exit multiple).
- **profit_potential_score**: replaces the vague `value_add_score`. Composite of
  ~12 growth levers; each lever = 45% upside + 30% utilisation gap + 15%
  feasibility + 10% evidence confidence. Moat is a small modifier, never a lever.
- **tam_score**: 40% size band + 25% growth + 25% penetration headroom + 10%
  source confidence. Returns 0 gracefully when TAM data is absent.
- **platform_dependency_risk_score**: generalised from v6's Adobe-specific score.
- Rationales are **generic** — no hardcoded case studies (see `cases/`).

## Operating Rules

1. Always score the deterministic core first; treat LLM output as advisory.
2. When enrichment is missing, score what you can and **flag the gap** (do not
   fabricate TAM, competitors, or lever evidence).
3. Persist every run to `memory.db` (`agent_runs`) for auditability.
4. Never approve or execute an acquisition — score, rationalise, shortlist only.

## ENRICHMENT CONTRACT (v0.2.0)

Market enrichment is gathered **outside Eva** (Perplexity-side) because the data
connectors are not in Eva's local runtime. Eva-side, `enrichment.py` defines the
CONTRACT and applies/caches enrichment — it never calls external APIs.

Field → connector mapping the external gatherer MUST satisfy:

| EnrichmentData field(s) | Connector | Meaning |
|-------------------------|-----------|---------|
| `tam_usd`, `sam_usd`, `market_growth_rate_pct`, `tam_source_url`, `tam_confidence_score` | **Statista** | market size / TAM / SAM / CAGR |
| `named_competitors`, `estimated_market_share`, `niche_growth_score` | **CB Insights** | competitor set, funding, subject market share |
| `market_fragmentation_score`, `niche_growth_score` | **Similarweb** | traffic distribution / demographics / demand spread |
| `source_urls`, `research_level`, `confidence_overall`, `niche`, `enriched_at` | cross-cutting | provenance + tier (`L1` once named competitors + share present, else `L0`) + blended confidence |

- `apply_enrichment(deal, EnrichmentData)` → validated flat kwargs dict for
  `analyze_deal_v7(deal, enrichment=...)`. Zero/empty fields are dropped so
  absent enrichment degrades gracefully (no TAM ⇒ `tam_score` stays 0; no named
  competitors ⇒ stays `L0`).
- `NicheCache` (sqlite, `enrichment_cache.db`) keys `EnrichmentData` by
  **normalized niche** with a **14-day TTL** — deals in the same niche share one
  (paid) research pass; stale entries miss and force a re-research.
- `fetch_enrichment_stub(niche)` documents the exact external interface and
  returns an empty `L0` record in-runtime (no network). The real gatherer is
  wired externally and hands back `EnrichmentData` JSON matching the schema.

## LEARNING (v0.2.0)

The agent learns from deal OUTCOMES via `learn.py`, non-destructively:

1. `record_outcome(deal_id, stage, outcome, notes)` — appends to `learnings`.
   `stage` ∈ VALID_STAGES; `outcome` ∈ {`passed`, `LOI`, `closed`, `withdrew`,
   `passed_on`} (positive = `LOI`/`closed`).
2. `recalibrate()` — for each of the 13 scoring axes, computes
   `separation = mean(dimension | positive outcomes) − mean(dimension | negative
   outcomes)` (inverted-risk axes are flipped so higher = better everywhere), and
   proposes `weight_delta = clamp(separation/100 × 0.03, ±0.03)`. It **PROPOSES
   ONLY** — base `V7_WEIGHTS` are never mutated; the proposal is logged to
   `directive_versions` as a `proposed-*` version for human/agent review.
3. `apply_learning(deltas)` — once reviewed, adds deltas onto an absolute
   `learned_weights.json` override and logs an `applied-*` version. Scoring
   consumes it via `analyze_deal_v7(weights_override=...)`, which merges onto the
   base weights and **renormalises to 1.0** (see `resolve_weights`) so the 0–10
   scale is preserved. Passing no override keeps the pure v7 base weights.
4. `get_learnings_summary()` — digest: outcome counts, mean positive vs negative
   overall score, and the high-score → conversion precision (does a high score
   actually predict `LOI`/`closed`?), plus the top recent lessons.

## LEARNINGS

<!-- Appended by the directive-sync bridge as deal outcomes (passed / LOI /
     closed) arrive. Each entry should capture: the deal, the outcome, the lesson,
     and any proposed weight_delta. Empty at v0.1.0.

     v0.2.0: recalibrate() now auto-logs weight-recalibration PROPOSALS to the
     directive_versions table (proposed-* versions). Distil reviewed proposals
     into human-readable entries here as outcomes accumulate. -->

## LEARNINGS (auto-synced)

### 2026-07-08T20:06:55.841518+00:00
- **source**: session-2026-07-08
- **lesson**: A Google Drive knowledge base is the long-term human-readable learning store; the directive-sync bridge is the machine-readable agent feed. Persist key decisions to BOTH every session.
- **decision**: Knowledge base directive: save key decisions BOTH ways every session
- **extra**: `{"kb_index_url": "https://docs.google.com/document/d/1_pLi2IB1Dp7RVGb1QMXKdl2-o3563Iv5klhx5jjZvjw/edit", "topic": "knowledge-base"}`

### 2026-07-08T20:06:55.839245+00:00
- **source**: session-2026-07-08
- **lesson**: Agents depend on Protocols (BrainClient, ResearchClient), NEVER on concrete providers. EVA_BRAIN_PROVIDER selects the provider at runtime. No hardcoded model dependencies anywhere.
- **decision**: Swap-and-play standing rule
- **extra**: `{"topic": "protocols"}`

### 2026-07-08T20:06:55.837336+00:00
- **source**: session-2026-07-08
- **lesson**: When starting testing, open all gates. Scout CLOSED deals (Acquire.com/Flippa/EF/BizBuySell) for market-trend ground truth. Closed deals carry known_outcome (sale_price, final_multiple, time_to_close) that feeds learn.recalibrate. 92 closed-deal records already collected (closed_deals_dataset.json).
- **decision**: Testing-mode principle: open all gates to collect labeled training data
- **extra**: `{"topic": "testing-mode"}`

### 2026-07-08T20:06:55.834781+00:00
- **source**: session-2026-07-08
- **lesson**: Gate 1 radar = 4 free checks (data completeness, category/niche fit, price-range band, red-flag screen) and FAILS OPEN. Free per-niche cached enrichment feeds v7. route_deal -> SHORTLIST (score >= 7.5) vs LOG_ONLY. Testing mode (EVA_TEST_MODE=1) opens all gates to collect training_observation records.
- **decision**: Cost-gate cascade (simplified)
- **extra**: `{"commit": "83a4239", "topic": "cost-gates"}`

### 2026-07-08T20:06:55.830265+00:00
- **source**: session-2026-07-08
- **lesson**: Claude is an OPTIONAL second-opinion call on the FINAL shortlist only (top 3 / score >= 7.5), NOT a per-deal hot-loop brain. Ollama deferred. Cost gates are configurable routing/logging only. Keep the BrainClient Protocol seam so providers are swap-and-play.
- **decision**: Architecture pivot: deterministic v7 score is the authoritative FREE engine
- **extra**: `{"commit": "83a4239", "topic": "architecture"}`
