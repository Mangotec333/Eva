# EVA — Current Goals

**The time-varying priority layer.** `docs/MISSION.md` is the north star that
rarely changes; this file is the *current* goal stack and it changes often.
Every EVA agent reads this at startup (graceful no-op if absent) to decide
whether to surge or idle — a deprioritized module knows to stay quiet, a Tier-1
module knows to push. This is the **coordination signal**: the company steers
many independent agents by editing this one document, not by commanding each
agent. Agents re-read on every run, so shifting a priority here needs no
redeploy.

**Owner:** Vineetkumar Ravi · Mangotec LLC
**Last updated:** 2026-07-17

---

## The one number that matters

> **$10K net / month** is the threshold where the flywheel self-sustains and the
> arrow flips to net-positive cash flow.

Until it's crossed, ranks 1–3 (EVA, Acquisition, Agency) get first allocation of
time and credits. Everything else runs protected or in the background.

**The flywheel:** *Acquisition or Agency cash → funds EVA build time → EVA
accelerates everything.*

---

## Priority stack (live)

The ranking mirrors the Command Center's Priority Tracks. Ranks 1–3 are the
revenue engine; 4 is non-negotiable; 5–7 are queued or background.

| Rank | Track | Status | Horizon | Current focus |
|------|-------|--------|---------|---------------|
| 1 | **EVA — Autonomous AI OS** | ACTIVE · BUILDING | Continuous | The flagship. Its own build is top priority because it accelerates every other track. Command Center live; module fleet growing; services startup in progress. |
| 2 | **Digital Business Acquisition** | FLYWHEEL | 30-day sprint | Acquire a cash-flowing, AI-resilient digital business (Health/Wellness SaaS profile). Target ~$10K net/mo after debt service. HELOC $200K staged. Deal Scout scores + gates candidates. |
| 3 | **AI Growth Agency** | 90-day target | 90 days | Productized AI services for SMBs — the near-term revenue engine toward the $10K/mo threshold. First-paying-customer path: deal-scorer wedge → landing page → capture → 7-touch nurture → convert. |
| 4 | **Wife & Family** | PROTECTED | Always | Non-negotiable protected time. Quality over quantity. Never traded against throughput. |
| 5 | **Public Speaking (Leadr.co)** | QUEUED | Staged | "Logic, Intuition & The LLM Within You" keynote. Stage prep active. Both a channel and EVA's product origin story. |
| 6 | **Storeys / RCFE (storeys.io)** | BACKGROUND | Background track | RCFE / senior-living acquisitions in California. A facility is under contract, not yet cash-flowing. |
| 7 | **Pureplate** | BACKGROUND | Maintenance | Dropshipping e-commerce. Maintenance mode, no new investment. |

---

## What "first allocation" means in practice

- **Ranks 1–3** — surge. Spend build-hours and credits here first. This is where
  proactive-but-explicit work is welcome.
- **Rank 4** — protected. Never scheduled over.
- **Ranks 5–7** — idle by default. Act only on explicit tasks; do not go looking
  for work (see Cost Discipline in `modules/README.md`).

---

## Active near-term objectives

These are the concrete milestones the ranks above are currently chasing.

1. **Cross the $10K net/mo threshold** — the whole priority stack collapses to
   "whatever gets us here fastest" until it's crossed.
2. **Close the first digital acquisition** (Rank 2, 30-day sprint) — Deal Scout →
   Deal Analyzer → gated candidate → HELOC-funded close.
3. **Land the Agency's first paying customer** (Rank 3) — deal-scorer wedge:
   direct outreach → landing page → inline capture → GHL contact + 7-touch
   nurture → convert 1–3 to paid.
4. **Keep the EVA build compounding** (Rank 1) — every one-off task that proves
   repeatable becomes a captured agent + SOP.

---

## Module status notes (things that change fast)

- **New modules earn autonomy.** Per the two-phase release standard
  (`modules/README.md`), a freshly-shipped module runs a 2-week window of
  3×daily manual testing before it's allowed to run autonomously. Modules in
  that window should stay manual/approval-gated regardless of their track rank.
- Modules coordinate through this file + `docs/MISSION.md` and their status
  endpoints — never by commanding a sibling.

---

*Companion documents: `docs/MISSION.md` (the north star) and
`docs/BRAND_VOICE.md` (voice guardrails for content-facing modules).*
