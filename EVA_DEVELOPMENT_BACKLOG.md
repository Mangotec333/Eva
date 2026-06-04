# Eva Development Backlog
Last updated: June 03, 2026

> Single source of truth for all outstanding Eva tasks. Work serially top-to-bottom. If blocked on current item, move to next and return.

---

## 🔴 IMMEDIATE — Unblock Launch

| # | Task | Owner | Status |
|---|---|---|---|
| 1 | Wire Calendly link into morning brief cron notification | Eva | DONE |
| 2 | brief.mangotec.ai — DNS + Netlify live | Vineet | DONE ✅ |
| 3 | LinkedIn post live | Vineet | DONE ✅ |
| 4 | Monitor LinkedIn "BRIEF" comments → reply with Calendly link | Vineet | ONGOING |
| 5 | Delete old morning brief cron a71bbb3b | Vineet | PENDING — manual at https://www.perplexity.ai/computer/tasks/204e0620-6c55-4744-a77b-a623b7691b2c |

---

## 🟡 EVA PRODUCTION — What Needs Building to Handle First Paying Customer

| # | Task | Priority | Notes |
|---|---|---|---|
| 6 | GHL setup — CRM pipeline for strategy session bookings | HIGH | Create "Eva Brief Strategy Session" pipeline: Booked → Called → Onboarded. 2-email post-call sequence. Tag founding members. |
| 7 | Onboarding SOP — what happens after someone books | HIGH | Write step-by-step: pre-call Loom → call → connect their Gmail/GCal → set deal box → confirm first brief delivery |
| 8 | Pre-call Loom template | HIGH | 60-sec personalized video before each strategy session. Build template script. |
| 9 | Netlify deploy automation | MEDIUM | Wire Eva → Netlify API so future landing page updates deploy without manual drag-drop |
| 10 | LinkedIn Zapier alert | MEDIUM | Trigger: new comment on LinkedIn post → Slack DM to Vineet. Free tier. |

---

## 🟡 EVA MODULE — Signal Intelligence DB

| # | Task | Status | Notes |
|---|---|---|---|
| 11 | Integrate signal_embeddings.py into main repo | PENDING | File exists at /home/user/workspace/eva_signal_db/signal_embeddings.py — not yet in Eva GitHub repo |
| 12 | Commit all staged files to Eva GitHub repo | PENDING | Staged: modules/intelligence/eva_signal_db/, eva_deal_db/, morning_brief_task.txt, README.md |
| 13 | Weekly Saturday signal mining cron | PENDING | Approved, not yet scheduled. Mine inbox + web for signals every Saturday 8am PT |
| 14 | Wire Signal DB semantic layer to morning brief | PENDING | signal_embeddings.py enables semantic search — pipe into morning brief context |

---

## 🟡 EVA MODULE — Deal Scout (Phase 2, post batch.ai close)

| # | Task | Status | Notes |
|---|---|---|---|
| 15 | Deal Scout product layer | PENDING | Intake questionnaire + scoring engine + cross-marketplace aggregation. Validate with Morning Brief cohort first. |
| 16 | Deal Scout landing page | PENDING | $149/mo. Use same design system as brief.mangotec.ai |

---

## 🟢 DIGITAL PRODUCTS — Revenue Backlog (Evaluate for Fast Revenue)

| # | Asset | Status | Next Action |
|---|---|---|---|
| 17 | GLÖSSAI (Lovable, published) | Needs review | Vineet: share the published URL → Eva evaluates monetization path |
| 18 | Funnel Builder Pro (Lovable, unpublished) | Needs review | Vineet: share URL → Eva reviews code quality → productize or shelve |
| 19 | batch.ai acquisition | LOI sent June 2 | Broker call was June 3 with Zachary Slater. Await Shawn Hawkins reply. |

---

## 🔵 EVA POSITIONING — Approved, Needs Integration

| # | Task | Notes |
|---|---|---|
| 20 | Add "Built to outlast the AI cycle" block to landing page | Features section — Shopify analogy. Add after first 3 founding members validate hero. |
| 21 | VSL script — 2-minute self-produced video | Structure: personal story (30s) → screen recording of live brief (45s) → one real deal caught (30s) → soft close (15s). Record after 3 founding members onboarded. |
| 22 | 60-second explainer video on hero | Add after first 3 founding members. Below CTA, not above. Loom/QuickTime first. |

---

## 🔵 INFRASTRUCTURE — Parking Lot

| # | Task | Notes |
|---|---|---|
| 23 | Personal Gmail forwarding (vineetkumar014@gmail.com → work) | Instructions delivered. Set up Gmail filter → forward newsletters/deal alerts to work inbox |
| 24 | mangotecusa.com sunset | Stale site on GoDaddy + Cloudflare + Omnia CMS (AWS). Contains "Opia Labs" reference. Redirect to mangotec.ai |
| 25 | Eva voice interface | Designed only. Not building until Morning Brief has 15 paying members. |
| 26 | Immersed VR / spatial computing | Parking lot 2027+. Track as emerging platform signal in morning brief. |
| 27 | Eva GitHub — commit all staged files | Run: cd /home/user/workspace/eva_repo && git add -A && git commit -m "feat: add intelligence modules, signal DB, deal DB, morning brief task" && git push |

---

## 📋 DECISION LOG (Key Decisions Eva Must Know)

| Date | Decision |
|---|---|
| Jun 2 | Morning Brief first at $49/mo — 15 founding members, call CTA only |
| Jun 2 | brief.mangotec.ai subdomain — separate from Eva OS |
| Jun 2 | LinkedIn organic only (Phase 1) — validate before paid |
| Jun 2 | GHL for CRM — not custom build until 100+ contacts |
| Jun 2 | Deal Scout: validate with Morning Brief cohort first |
| Jun 2 | VC/PE: not our market |
| Jun 3 | Teach-first content sequence — 8-10 posts before hard CTA push |
| Jun 3 | "Built to outlast the AI cycle" angle — features section, not hero |
| Jun 3 | Video: after first 3 founding members, not before |
| Jun 3 | Calendly free tier — one event type: Eva Brief Strategy Session |

---

## 🔗 Key Links

- Landing page: https://brief.mangotec.ai
- Calendly: https://calendly.com/vineetkumar-mangotecusa/eva-brief-strategy-session
- Eva Command Center: https://eva.mangotec.ai
- Eva Launch Playbook (Google Doc): https://docs.google.com/document/d/1_A6d1TZyautJdbnkZjp0d_XQeMwXD8y9N-reVlHKgL4/edit
- Eva Master Index (Google Doc): https://docs.google.com/document/d/16T3kyMmvCuxpeGFVmVo48VHm_6O6FCM2CgIquKRR4X0/edit
- Eva GitHub: https://github.com/Mangotec333/Eva
- Signal DB: /home/user/workspace/eva_signal_db/ (30 active signals)
- Netlify site: eva-brief.netlify.app

---

## Architecture Correction — Angels vs AI Employees
**Logged: Jun 4, 2026**

- EVA uses ANGELS (outcome-based) NOT AI Employees (role-based)
- Angels have missions, not job titles. Spin up for a result, dissolve when done.
- AI Employees = overhead mindset. Angels = leverage mindset.
- One-line: "EVA deploys Angels — autonomous agents with a mission, not a job description."
- Remove all AI Employee language from EVA product copy, pitch, landing pages
- Infographic built Jun 4 (AI Employee Blueprint) = competitive research only, not EVA framing
- Jun 4 | Angels are outcome-based agents, not role replacements — core architecture principle

---

## Competitive Intel — Tatiana Budney / The AI Workroom
**Logged: Jun 4, 2026**

- 19 members, launched ~1 week ago, $47/mo, Kajabi community
- Format: monthly Zoom mixer + skills/prompt library + 4-week accelerator (Jun 24)
- Philosophy: "Not watching. Not collecting prompts. Building."
- Human-first AI — practical, useful, still human
- Audience: coaches, content creators, ops people, beginners
- One member (Marc Gurtman) building "autonomous agent systems + digital workforce framework" — closest to EVA territory
- No product. No Angels. No outcome-based architecture. Pure education + community.
- Gap vs EVA: they teach, we deploy. They build skill, we deliver outcome.
- Inspiration: monthly "mixer" format — small Zoom breakout rooms, peer-to-peer wins sharing. Could be EVA founding member meetup format.
- Inspiration: "Wins and Builds" channel — EVA could have a founder log or build-in-public feed inside Command Center
- Inspiration: Skills & Prompt Library — EVA Angel library (pre-built Angel missions by use case) is the product equivalent
- NOT to copy: community model, self-serve, prompt collection, passive content
- Jun 4 | Tatiana = education layer. EVA = execution layer. Complementary, not competing.
