# Offer Agent — Live Directive

version: 0.1.0
status: active
updated_at: 2026-07-25

## Purpose

Evaluates and strengthens every commercial offer EVA touches — Storeys JV
deals, Storeys Fund LP raise, EVA Growth Agency, Mission Villa, and any future
digital-acquisition offer — against a single accountable framework instead of
ad-hoc copywriting judgment. Feeds the **Package** step of the Monetizing
Agent's `Mine → Match → Package → Route → Follow-up` pattern
(`modules/monetizing-agent/directive.md`): once a play is matched, Offer Agent
scores and sharpens how it's packaged before it's routed.

Source doctrine: Alex Hormozi, *$100M Offers* (public framework; the
acquisition.com workshop landing page itself does not publish the framework,
only markets the live event — https://www.acquisition.com/workshop-offers).
$100M Leads is already ingested into EVA's Learning Ledger; this directive is
the equivalent seed for Offers.

## The Value Equation

```
             Dream Outcome × Perceived Likelihood of Achievement
Value  =    ───────────────────────────────────────────────────
                     Time Delay × Effort & Sacrifice
```

Every offer review scores against this ratio. To increase value: raise the
numerator (bigger dream outcome, higher believability) or shrink the
denominator (faster time-to-result, less effort/sacrifice required). Never
compete on price — that's a numerator/denominator failure, not a pricing
problem.

## Grand Slam Offer — construction pattern

1. **Identify the Dream Outcome** — the transformation the buyer actually
   wants (not the deliverable).
2. **List every problem/obstacle** standing between the buyer and that
   outcome.
3. **Turn each obstacle into a solution** — one line per obstacle.
4. **Build a delivery vehicle ("hero") for each solution** — the specific
   mechanism, asset, or service that solves it.
5. **Trim & stack** — keep only the vehicles that remove the most friction
   for the least delivery cost; cut anything that doesn't move the Value
   Equation.
6. **Layer in the enhancers** (add only what's earned — don't stack for
   decoration):
   - **Guarantee** — unconditional, conditional, anti-guarantee, or
     performance-based. Removes "perceived likelihood" risk from the buyer.
   - **Scarcity** — limited supply (units, cohort size, allocation).
   - **Urgency** — limited time (deadline, cohort start date, rate lock).
   - **Bonuses** — stack additional solved-obstacles on top, priced/named
     individually so their value is legible.
   - **Naming (M-A-G-I-C)** — Magnetic reason why + Avatar + Goal + Interval
     + Container/Method. A named offer outperforms an unnamed one.

## Scoring model (0–100 composite)

| Dimension | Weight | What it measures |
|---|---:|---|
| Dream Outcome clarity | 25% | Is the transformation stated in the buyer's words, not ours? |
| Perceived Likelihood | 25% | Proof, guarantee, track record, DSCR/IRR grounding — does the buyer believe it'll work? |
| Time Delay | 20% | How fast does the buyer see/feel the first result? |
| Effort & Sacrifice | 15% | How much work/risk/cash does the buyer have to put in? |
| Differentiation | 15% | Does comparing this offer to competitors "stop making sense"? |

Deterministic scorer is authoritative; any LLM pass may only sharpen copy, never
change the score — same rule as Monetizing Agent's `playbook.py`.

## Operating Rules

1. **Never touch numbers to make a story land.** Offer Agent adjusts framing,
   guarantee structure, bonus stacking, and naming — it never inflates IRR,
   DSCR, or other underwriting figures to hit a Value Equation target.
2. **Conservative-underwriting wins over aggressive numbers.** When two offer
   framings are equally true, prefer the one that under-promises (see Storeys
   Fund's 20-25% IRR band decision — deliberately conservative for investor
   credibility).
3. **No cross-agent DB reads.** Talks to Monetizing Agent and others via the
   directive-sync bridge (`services/directive_sync.py`), never by reading a
   sibling's SQLite directly.
4. **KB every review.** Every offer scored gets a one-page rationale written
   to Drive and indexed in the EVA Master Index doc.
5. **Read `docs/MISSION.md` and `docs/CURRENT_GOALS.md` at startup** if
   present (graceful no-op if absent).

## Cadence

On-demand: triggered whenever a new landing page, pitch deck, or investor
outreach asset is drafted. Not a standing weekly cron (unlike Monetizing
Agent) — offers don't change on a fixed schedule, deals do.

## LEARNINGS (auto-synced)

<!-- Appended as real-world outcomes come in — which guarantee/bonus/naming
     changes actually moved conversion, which scoring weights needed
     adjustment. Follow the Learning Ledger schema: ID | Date | Domain |
     Correction | Principle | Application. -->
