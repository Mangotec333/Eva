# Deal Analyzer Agent — Live Directive

version: 0.1.0
status: active
updated_at: 2026-07-07

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

## LEARNINGS

<!-- Appended by the directive-sync bridge as deal outcomes (passed / LOI /
     closed) arrive. Each entry should capture: the deal, the outcome, the lesson,
     and any proposed weight_delta. Empty at v0.1.0. -->
