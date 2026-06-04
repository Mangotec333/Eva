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

---

## UI Feature Request — Task Done Button
**Logged: Jun 4, 2026**

- Add a "Done" button next to each task in EVA Command Center todo list
- User clicks Done → task marked complete without needing to respond in chat
- Saves credits — no round-trip to agent for status updates on historical tasks
- Priority: Medium — quality of life, reduces friction in daily use
- Component: Command Center task panel

---

## Feature Spec — EVA Activity Board (Command Center v2)
**Logged: Jun 4, 2026**
**Priority: HIGH — needed for ML data collection + daily ops visibility**

### Core Concept
Monday.com / Jira-style board inside EVA Command Center.
Every activity logged by timestamp. Nothing deleted. Used for ML pattern mining later.

### Board Views
1. **In Progress** — active tasks right now
2. **Completed** — done tasks with timestamp
3. **Planned** — items queued but not started
4. **Carry Over** — planned but not done today, rolled to next day
5. **Parking Lot** — validated ideas not on critical path yet

### Energy Level Collection
- Simple 1-5 input widget in EVA UI (morning, midday, evening)
- Logged to DB with timestamp, session_id, context tag
- Used for ML: correlate energy level with task completion rate, deal decisions, output quality

### Data Rules
- NEVER delete any record — soft delete only (archived flag)
- Every state change logged with timestamp (created, started, completed, carried_over, parked)
- All data tagged: project thread (EVA / Storeys / AI Growth Agency / Mangotec / Personal)
- ML-ready schema: user_id, task_id, state, timestamp, energy_level, project_tag, notes

### DB Schema (new tables needed)
- `activities` — id, title, description, project_tag, state, created_at, updated_at, completed_at
- `activity_events` — id, activity_id, from_state, to_state, timestamp, notes
- `energy_logs` — id, level (1-5), check_in_type (morning/midday/evening), timestamp, notes
- `parking_lot` — id, title, description, rationale, logged_at, revisit_date

### UI Components
- Kanban board with drag-and-drop columns (In Progress / Completed / Planned / Carry Over / Parking Lot)
- Done button on each task card (closes loop without chat round-trip)
- Energy check-in widget: 1-5 tap input, appears at morning/midday/evening cron trigger
- Timestamp on every card — hover to see full history
- Filter by project thread
- Export to CSV for ML training data

### Integration
- Crons write tasks to `activities` table on each run
- Morning Brief Angel reads `activities` to surface carry-overs and parking lot items
- Energy logs feed into pattern analysis (Module 5 — Pattern Engine)

### Build Sequence
1. DB schema + migration
2. FastAPI routes for activities + energy_logs
3. Command Center UI — kanban board component
4. Energy widget wired to cron triggers
5. Deploy to eva.mangotec.ai


---

## DRIVING PRINCIPLES (Updated June 4, 2026)

**PERMANENT — Apply to every build, design, and decision in EVA.**

1. **Automation velocity + customer outcomes** — Everything now. No waiting.
2. **Fail fast** — Outreach and experimentation saves opportunity cost.
3. **Ship fast, get feedback, fail fast and pivot** — No perfect. Drive for excellence through iteration, not perfection.
4. **Simple. Modern. Minimalistic. Intuitive.** — Every product decision runs through this filter. If it's complex, simplify it. If it's heavy, strip it.
5. **Modular + microservices** — Every component independently deployable.
6. **Blanket approval on routine work** — Speed over ceremony.

> "No perfect. We strive for simplicity, modern, minimalistic and intuitive product designs."
> — Vineet Ravi, June 4, 2026

---

## CREDIT DISCIPLINE & WATCHDOG (Locked June 4, 2026)

### Pre-Task Approval Gate
- **Any task estimated >5 min runtime → EVA states it upfront and waits for Vineet's go.**
- Applies to: browser automation, wide_research, multi-step PDF/data extraction, any retry loop.
- Low-cost routine tasks (<5 min estimated) → auto-execute per blanket approval rule.

### 5-Minute Watchdog Rule
- Any running browser/subagent task with no result at T+5 min = **KILL IT, surface as manual.**
- EVA should never run a browser task past 5 min on structured data extraction from known-problematic sources (Google Drive PDFs, auth-gated pages).
- Manual fallback: "Do this at your Mac in 2 min, share the output, I'll run the analysis."

### Agent Task Tracking (DB)
- `agent_tasks` table added to Activity Board DB.
- Every launched task logs: name, type, cost_tier, estimated_minutes, subagent_id, status.
- Watchdog endpoint: POST /api/agent-tasks/watchdog → flags any task running >5 min as `stalled`.
- Watchdog cron: every 5 min → hits /api/agent-tasks/watchdog → notification if stalled tasks found.

### Cost Tiers (proxy for credit spend)
| Tier | Type | Example |
|------|------|---------|
| Low | Single search, text generation | Web search, write copy |
| Medium | Short browser task <3 min | Form fill, page read |
| High | Long browser task, wide_research, PDF extraction | Drive PDFs, 10+ entity research |

**High tier = always ask before launching.**

---

## EVA DEPLOYMENT ARCHITECTURE (Locked June 4, 2026)

### Multi-Tenant Roadmap

**Phase 1 — Now → First 10 clients**
- Single-tenant per client
- One containerized Docker instance per customer
- Full data isolation, high trust
- You control the image, push updates manually
- Operationally simple — no control plane needed

**Phase 2 — 10–50 clients**
- Introduce a lightweight control plane
- Tenant registry: tracks all deployed instances
- Health monitoring across instances
- Push updates/config changes without changing per-tenant architecture
- No shared data layer yet

**Phase 3 — 50+ clients**
- Selective multi-tenancy
- Stateless services → shared multi-tenant layer: Content Engine, Deal Scout
- Stateful/behavioral layer → stays per-tenant: Logger, Pattern Engine, Memory
- This is the architecture that beats GHL on cost AND privacy

**Screenpipe signal layer: ALWAYS single-tenant**
- Too sensitive, too local
- Never shared infrastructure regardless of scale

### Admin / User Panel Model
- **Admin panel**: You only. PIN-gated (557799). Agents, crons, watchdog, costs, tenant registry (Phase 2+).
- **User panel**: Minimal, outcome-focused. Tasks + energy + notifications. Client need not know the ops layer.
- **Auth**: PIN now → Google OAuth at Phase 2 (multi-user)
- **White-label**: Each client gets branded EVA under their domain from Phase 1

> "The architecture that beats GHL on both cost and privacy." — June 4, 2026
