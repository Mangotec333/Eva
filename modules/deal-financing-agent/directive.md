# Deal Financing Agent — Live Directive

version: 1.0.0
status: active
updated_at: 2026-07-17

## Purpose

Run bottoms-up acquisition financing / underwriting math for real estate and
small-business deals (RCFE/senior-living focus first, generalizable to any
income-producing property or operating business acquisition). Complements
deal-analyzer-agent (which scores deal *attractiveness*) — this agent answers
"does the financing actually work?" with real numbers.

## No-Circularity Rule (permanent, non-negotiable)

The engine must NEVER assume a target return (IRR, cash-on-cash %, yield) and
back-solve into debt service, price, or cash flow. The chain is strictly
one-directional:

    revenue, opex (from actuals/projections)
        -> NOI
    loan amount, rate, amortization (from actual term sheet / lender quote)
        -> amortized debt service (standard mortgage formula)
    NOI - debt service
        -> cash flow to equity, DSCR
    cash flow stream + equity injection + (optional) exit value
        -> cash-on-cash, equity multiple, IRR (COMPUTED from the resulting
           stream, never assumed going in)

If a prior model shows an assumed yield % multiplied by equity to "derive"
cash flow (instead of deriving cash flow from NOI minus real debt service),
that model has this circularity bug and must not be reused as a pattern.

## Data Inputs — provenance required

Every run must cite where revenue, opex, and loan terms came from. Do not
fabricate a loan rate — if the actual lender term sheet rate is not yet
known, use `rate_source_note` to flag it as a market-rate assumption pending
confirmation (see cases/mission_villa.json for the current example).

## Engine (financing_engine.py)

- `monthly_payment()` / `remaining_balance()` — standard fixed-rate amortizing
  mortgage math.
- `build_yearly_cashflows()` — projects revenue/opex forward at their stated
  growth rates, computes NOI, subtracts total debt service (senior + seller
  note if any) per year.
- `irr()` — bisection solver on the full cash-flow stream (equity outlay at
  t=0, annual cash flow to equity, plus net sale proceeds at exit if an exit
  cap rate is supplied). No numpy-financial dependency.
- `run_financing_model()` — orchestrates the above into `DealFinancingResult`,
  and raises `flags` for anything a human underwriter should double check
  (DSCR below 1.25x, missing rate, non-convergent IRR, no exit modeled).

## Operating Rules

1. Deterministic only in v1 — no LLM call in the compute path. An LLM
   narrative/rationale layer may be added later strictly on top of, never
   inside, the engine.
2. Every run persists to `memory.db` (`financing_runs`) for audit.
3. Never approve or execute a purchase — model financing feasibility only.
4. If DSCR < 1.25x at any year, flag it — that is the typical SBA lender
   minimum covenant; a deal that fails it needs restructuring (lower price,
   more equity, seller note, longer amortization) before it is financeable.

## LEARNINGS

<!-- Appended as real outcomes (funded / declined / restructured) arrive. -->

### 2026-07-17
- **source**: session-2026-07-17 (Mission Villa build)
- **lesson**: Mission Villa's own historical P&L files ("Financial projections
  Mission Villa.xlsx") mix the SELLER's existing mortgage (~$128-129k/yr) into
  some side-panel net calcs. That is the seller's old debt, not the buyer's
  new SBA loan — never carry it into the buyer-side financing model. Always
  separate "seller's historical debt service" from "buyer's proposed new debt
  service" when building from acquisition-target financials.
- **decision**: Use unlevered NOI (revenue − opex, no interest/depreciation)
  as the sole engine input; apply the NEW proposed loan's amortized debt
  service downstream, never reuse a prior owner's mortgage figure.
