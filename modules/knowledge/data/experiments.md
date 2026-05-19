# Experiments
_Last updated: 2026-05-19 | Version: 0.1 | Module: EVA Knowledge OS_

_This is a living log. Append new experiments as they run. Never delete old entries — failed experiments are data._

---

## [2026-05-19] LinkedIn Audience Validation Test

**Hypothesis:** Acquisition entrepreneurs and RCFE operators will respond to pain-point posts with keyword CTAs.

**Test A:** Deal Scout post — keyword: SCOUT
- Hook: pain point of solo acquirers drowning in deal flow noise
- CTA: "Comment SCOUT for early access"
- Tag: Alex Hormozi (audacious move — mentor outreach attempt)

**Test B:** RCFE Compliance post — keyword: OPERATOR
- Hook: pain point of RCFE operators managing state compliance manually
- CTA: "Comment OPERATOR for early access"

**Method:** Organic LinkedIn post. No paid amplification. First 48 hours are signal-only.

**Measure:** Number of keyword comments within 48 hours.

**Kill signal:** 0 keywords in 48 hours → pivot copy or pivot audience.

**Fuel signal:** 3+ keywords → $200 LinkedIn ad spend on winning variant.

**Status:** RUNNING

**Learnings so far:**
- Public CTA > private DM ask — the algorithm amplifies comment activity, making the post reach larger audiences organically.
- Posting to a cold audience generates a smaller sample but simultaneously warms the algorithm for future posts. Cold audience seeding is a long-term investment even when short-term signal is weak.
- Tagging a high-profile mentor (Hormozi) is a calculated asymmetric bet: near-zero cost, non-zero upside of mentor visibility and audience credibility signal.
- The keyword mechanic creates a two-sided data point: volume (how many) and intent (they typed the word, they're not passive).

---

## [2026-05-19] Channels Hub Architecture Experiment

**Hypothesis:** A unified Channels Hub module can aggregate all EVA communication channels (LinkedIn DMs, Reddit mentions, email alerts, Slack notifications) into a single command interface, reducing context-switching tax to near zero.

**Test:** Build MVP Channels Hub with 3 integrations (LinkedIn, email, Slack) and run for 5 working days. Measure time saved vs. baseline (checking 3 separate apps manually).

**Approach:**
- Lovable bridge for UI scaffolding
- FastAPI aggregation layer
- EVA Launcher API as orchestration backbone

**Measure:** Time-to-first-response on inbound messages (baseline vs. Channels Hub). Subjective "cognitive load" rating (1–10) end of each day.

**Kill signal:** Build takes >3 days, OR no measurable time saving after 5 days of use.

**Fuel signal:** Average time-to-response drops by 50%+ OR cognitive load rating drops by 3+ points.

**Status:** IN BUILD (2026-05-19)

**Learnings so far:**
- The Lovable bridge pattern (Lovable scaffold → EVA API wiring → production hardening) is faster than building from scratch. Scaffold takes hours. Hardening takes days. This is the right sequence.
- Aggregating channels is a commodity feature. The moat is not the aggregator — it's the EVA context layer that understands which message requires Vineet's direct response vs. EVA auto-reply.
- Priority filter logic: inbound DMs from SCOUT/OPERATOR keyword senders get highest routing priority. Everything else is background.

---

## [2026-05-19] Microservices Monetisation Model Test

**Hypothesis:** Each EVA module can be sold as a standalone micro-SaaS product ($49–$299/month) AND remain integrated into the full EVA OS, creating a dual revenue model: standalone users who may upgrade to full OS, and OS users who validate individual module value.

**Test:** List Deal Scout v2 as a standalone product on ProductHunt (or equivalent) with a $49/month price point. Run for 30 days alongside the integrated EVA deployment. Measure: standalone signups vs. full OS upgrade requests.

**Pricing ladder for test:**
- Free: 5 deals/week (Deal Scout standalone)
- $49/month: unlimited deals + email alerts
- $99/month: + AI scoring + daily brief
- $299/month: full EVA OS (all modules)

**Measure:** Conversion rate at each price tier. Upgrade rate from standalone → full OS. Support overhead per tier.

**Kill signal:** 0 standalone conversions in 30 days at $49 tier, OR upgrade rate from standalone → OS is <5%.

**Fuel signal:** 10+ standalone conversions at $49 in 30 days, OR 3+ standalone users request full OS access.

**Status:** QUEUED (dependency: stable Deal Scout v2 + landing page)

**Learnings so far:**
- The micro-SaaS model creates a natural customer acquisition funnel for the full OS. Standalone users are pre-qualified — they've already paid, already have context, already trust the product.
- Standalone pricing validates willingness to pay for individual modules before bundling them. This is the sell-first principle applied to product architecture.
- Risk: standalone users may never upgrade if the standalone product solves their full need. Counter: deliberately scope standalone to leave 30% of the value in the integrated OS. Design the gap intentionally.

---

## [2026-05-19] RCFE Pipeline Validation Test

**Hypothesis:** Having 1 RCFE under contract creates enough credibility signal to move 2 pipeline facilities from warm to signed within 60 days.

**Test:** Reference RCFE #1 (under contract) explicitly in all RCFE operator outreach. Measure: conversion rate from warm intro → signed LOI for facilities #2 and #3.

**Measure:** Days from first contact to LOI for pipeline facilities. Compare to RCFE #1 baseline.

**Kill signal:** Both pipeline facilities fail to advance to LOI within 60 days despite warm outreach.

**Fuel signal:** Either pipeline facility reaches LOI within 30 days. Or additional unsolicited RCFE inquiries arrive (word-of-mouth signal).

**Status:** BACKGROUND (RCFE track is running in parallel, not primary sprint focus)

**Learnings so far:**
- "Under contract" is a credibility anchor that changes the conversation from "who is this person" to "what are the terms." The first deal is always the hardest because there's no proof of execution.
- EVA deployment in RCFE #1 creates a replicable case study: "We deployed AI-assisted care quality monitoring and reduced compliance overhead by X%." That becomes the pitch for facilities #2 and #3.
- Background track discipline: we check this once per week, not daily. The sprint focus is acquisition and EVA build. RCFE advances when the pipeline moves it.
