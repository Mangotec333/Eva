# EVA Modules

Standalone modules that power EVA's sensing and operating layers.

## Architecture Directive — Every Eva module is an autonomous-agent microservice

**This is the fixed standard for all Eva coding.** No exceptions without explicit owner sign-off. New modules, edits to existing modules, and any agent that builds Eva code follow these rules.

1. **One module = one autonomous agent.** Each module is a self-contained microservice: own FastAPI app on its own port, own SQLite database, own CLI, own tests, own `requirements.txt`, own `setup.sh`, own `README.md`. A module owns its data and its transport; it never reaches into another module's internals.
2. **No shared runtime state.** Modules talk to each other through HTTP contracts or well-defined interfaces — never shared memory, never another module's database, never a shared mutable singleton. Coupling is via documented request/response shapes, not imports of sibling internals.
3. **Transport behind an interface.** Any external action (email, LinkedIn, Shopify, payments) goes behind a Protocol with a `Stub` implementation (offline, no network — used in tests) and a real implementation that shells out to a single subprocess chokepoint (`gmail_send.py`, `linkedin_post.py`, …). The chokepoint is the only place real network code lives. Stubs never fake success; an unwired transport returns `ok=False` with a clear error.
4. **Approval gates on irreversible actions.** Sends, posts, publishes, payments require a human approval step before release (status `draft → approved → posted`). This is Eva's collaborative-autonomy model: autonomy up to the line of irreversibility, human at the line. v1 never auto-executes an irreversible action.
5. **Append-only ledgers.** Every state change (create, approve, send, post, fail) is written to an append-only ledger table with a trigger enforcing immutability. The ledger is the audit trail and the recovery source.
6. **Idempotent by design.** `seed`, `tick`, and similar operations are safe to call repeatedly and from a cron. Running twice does not duplicate.
7. **Offline-runnable tests.** The sandbox has no network. Tests must pass with zero outbound calls — use Stub transports everywhere. No test depends on a live API, a real OAuth token, or a paid key.
8. **Budget-conscious stack.** stdlib `sqlite3` + `Pillow` only. No paid dependencies, no heavy frameworks, no new stack introduced to ship one module. Match the freshest sibling module's conventions.
9. **Two-phase release standard.** Every new module ships, then gets 2 weeks of 3×daily manual testing before it's allowed to run autonomously. Autonomous mode is earned, not assumed. This is the release protocol for all Eva modules.
10. **Module release checklist (a module is not done until all are true):**
    - [ ] FastAPI service on its own port + `/health`
    - [ ] CLI subcommands matching sibling module style (`eva <module> <cmd>`)
    - [ ] Stub + real transport behind a Protocol, chokepoint subprocess in place
    - [ ] Approval gate on every irreversible action
    - [ ] Append-only ledger with immutability trigger
    - [ ] Idempotent `seed` / `tick`
    - [ ] Offline test suite green (`python -m pytest`)
    - [ ] `README.md` with quick start + endpoints + CLI
    - [ ] Branch `feat/<module>`, PR opened, full suite green before merge

**For coding agents:** read this before touching `modules/`. Build to this contract. If a requirement forces a deviation, stop and surface it — do not silently break the standard.

---

## Agent Intelligence Layer — per-agent memory, mission alignment, time-varying goals

The microservice contract (section above) defines the service boundary. This section defines the **intelligence boundary**: how each agent remembers, how it stays aligned to the company, and how it coordinates without being commanded.

### 1. Every agent has its own memory

Each module maintains a **memory store** — persistent context the agent accumulates across runs: decisions made, what it learned, preferences discovered, state carried forward. This is distinct from the append-only event ledger (which records actions taken); memory records *what the agent knows*.

- Stored in the module's own SQLite as a `memory(key TEXT PRIMARY KEY, value TEXT, ts, source)` table (or the module's native key-value if it has one).
- Read at the start of every task; written after a decision or learning. Memory is the agent's long-term context — without it the agent is stateless and re-derives everything each run.
- Per-agent only. An agent never reads another agent's memory directly — if cross-agent context is needed, it flows through the coordination layer (below), not by reaching into a sibling store.

### 2. Mission & vision — shared, read-only north star

A single source of truth for the company mission and vision lives at `docs/MISSION.md` (rarely changes). Every agent reads it at startup to align its decisions. The mission is the constraint that keeps independent agents pointed the same direction without a central commander.

- Agents treat the mission as a **read-only alignment artifact**, not a config they edit.
- When an agent faces an ambiguous decision, the tie-breaker is: which choice serves the mission? The agent records that reasoning in its memory so the choice is auditable.

### 3. Time-varying goals — the evolving priority layer

Goals are time-varying: revenue targets shift, a fundraise becomes Tier 1, a module enters its 2-week test window, a goal gets retired. A single **current-goals artifact** (`docs/CURRENT_GOALS.md`, or a goals table the command center writes) holds the active goal stack with priorities and time horizons.

- Agents read the current goals before prioritizing work, so a module that was deprioritized knows to idle and a Tier-1 module knows to surge.
- Goals change over time; agents re-read on each run and pick up the latest — no redeploy needed to shift priorities.
- The goals artifact is the **coordination signal**: it's how the company steers many independent agents at once, by editing one document rather than commanding each agent.

### 4. Independence + coordination contract

- **Independence:** within its bounded domain, an agent decides and acts on its own. It does not wait to be commanded by another agent. An agent's autonomy extends up to the approval gate on irreversible actions (section above) and within the mission/goals alignment.
- **Coordination, not control:** agents coordinate through **shared context** (mission, current goals) and **status visibility** (each agent exposes `/health` + a status endpoint so the command center and sibling agents can see what it's doing). No agent directly commands another; coordination is by reading the same north star, not by one agent calling another's internal logic.
- **Conflict resolution:** if two agents' outputs conflict, the mission + current-goals artifact decides precedence. If still ambiguous, it escalates to a human (same gate as irreversible actions).

### 5. What each module must include for the intelligence layer

- [ ] `memory` table in the module's own SQLite (read on task start, written on decision/learning)
- [ ] Reads `docs/MISSION.md` at startup (graceful no-op if absent — never crash on missing mission)
- [ ] Reads `docs/CURRENT_GOALS.md` at startup (graceful no-op if absent)
- [ ] `/health` returns agent status + last-run summary so the command center can observe it
- [ ] No direct reads of another agent's memory or database — cross-agent context flows through shared docs + status endpoints only

---


## Cost Discipline — every agent minimizes credit/token spend

Budget is finite; revenue-first means every credit pushes toward revenue. Agents follow:

1. **No proactive work.** Agents act on explicit tasks, not by finding work to do. Idle is fine.
2. **Short outputs.** Final responses are terse — status + next step, no preamble, no restating done work.
3. **Minimal tool calls.** Batch where possible; one focused search instead of many parallel. No redundant re-reads.
4. **No advisor/second-model calls unless genuinely stuck.** Default to acting, not re-planning.
5. **Skip heavy QA (Playwright/screenshots) unless requested.**
6. **Background subagents are expensive** — only spawn when the task genuinely needs one, and cancel once the deliverable (e.g., PR pushed) lands.
7. **Prefer local edits over spawning a code agent** for small changes.

This is a standing directive, not a one-time instruction. Reviewing agents cost money; ship and stop.

---

---

Each module is independently deployable and validates as a micro-SaaS candidate.

## The module fleet

The full agent roster below is grouped by function. Ports are the observed
values from each module's code (see `EVA_AGENT_CATALOG.md` for the authoritative,
auto-inventoried catalog and flagged port conflicts). One line per module; see
each module's own `README.md` for the quick start, endpoints, and CLI.

> **38 module directories.** Some are FastAPI microservices on their own port,
> some are libraries/subrouters mounted by others, some are UI front-ends, and
> `autostart` is boot/install tooling (not an agent).

### Orchestration & console

- **triage-brain** (`:8784`, Diracatron) — Eva's single top-level orchestration brain. `POST /triage/run` stack-ranks every open door (scored deals, ledger, signals) with first-principles rationale; `POST /triage/dispatch` uses an LLM to pick which lobes to invoke, triggers them via a data-driven agent registry, and logs every decision + outcome to eva-state.
- **launcher** (`:8768`, Module 7) — process manager for the fleet. Owns the `SERVICES` table, starts/stops/restarts services, lazily mounts sibling routes, and serves the landing tracker cache. The human/console entrypoint.
- **command-center** (Vite/React) — front-end console: AgentPipeline, DealTracker, ContentQueue, ActivityFeed dashboards. Talks to launcher + service APIs. "$10K/mo threshold = arrow flips."
- **morning-os** (`:5000`, Node/React + Express) — the "morning OS" dashboard (Lovable-built): Goals / Check-in / Activity / History across time horizons.
- **agent-builder** — the meta-agent that builds agents. Inventories `modules/` (refreshes the `EVA_AGENT_CATALOG.md` auto-inventory), scaffolds new agents to the canonical pattern, and captures a one-off workflow into a repeatable SOP + runbook so EVA can rerun it autonomously.
- **autostart** — not an agent: boot/install tooling. Registers every EVA service as a macOS launchd agent so they start on login and restart on crash.

### State, memory & knowledge

- **eva-state** (`:8769`) — the governed **append-only state/history ledger**; single source of truth for state and history across all agents, sessions, and surfaces (events, projects, blockers, coined terms).
- **knowledge** (`:8771`) — living knowledge base: culture, strategy, experiments, deals, playbooks, principles. Backed by Google Drive/Docs + local markdown.
- **kb_index** — shared "Master Index" writer for Google Docs. Protocol-behind-transport (offline Stub vs `GoogleDocsIndexTransport`). A library, not a server.
- **intelligence** — living knowledge layer (Signal Intelligence DB and related sub-modules) for the Founder OS.
- **logger** (`:8765`, Module 1) — EVA's sensing layer. Background daemon tracking active apps, focus blocks, context switches, and idle time; three-tier source hierarchy (Screenpipe → ActivityWatch → built-in) exposed via a unified context API.

### Deal engine

- **deal-scout** (`:8766`, Module 3) — deal-sourcing/scoring microservice for digital-business acquisition. Ingests candidates (Flippa, Empire Flippers), scores across five dimensions, and computes seller-finance / HELOC cash-flow projections.
- **deal-analyzer-agent** (`:8767`) — "first agentic-operating-model" service. Scores deals via a v7 engine behind HTTP with a cost gate, memory, and its own directive.

### Capture → nurture → outreach

- **ghl-agent** (`:8782`, Nora) — the single Eva→GoHighLevel service. Idempotent campaign/funnel build + ongoing lead-capture automation loop + webhook handler (the landing page's `/lead/capture` target). GHL access behind a `GHLClient` Protocol.
- **channels** (`:8770`) — multi-platform publishing behind a common `Publisher` Protocol (v1: Reddit + Substack), each with its own subprocess network chokepoint; also hosts the Apollo→GHL cold-outreach pipeline.
- **social-publish** (Sam) — the approve-then-publish gate for social. Nothing publishes without an explicit Slack ✅ or launcher approval. Delegated behind launcher `/social/*` (no own port).
- **social-scheduler** (`:8787`) — the autonomous daily publisher for the eva-acquisition pipeline: 5 posts/day on a fixed America/New_York schedule, each gated through the social-publish Slack flow, then likes + CTA-comments and syncs engagement analytics into local SQLite.
- **outreach** (`:8768`, Module 6) — compliance-safe, approval-gated investor outreach: approval queue, accredited-investor (Rule 506(c)) verification, global suppression list, and an append-only compliance ledger.
- **pathfinder** (`:8773`) — monetization funnel agent. Scores waitlist submissions hot/warm/cold, routes them to DM sequences, and surfaces follow-up priorities for the Command Center.
- **email_agent** — morning triage: scans Gmail → deals.db, extracts broker contacts/URLs, and builds the morning-brief JSON.
- **waitlist** — the static landing page for "Eva — AI Agent Platform for Operators & Agencies."

### Content & media

- **content-engine** (`:8767`, Cole) — nightly LinkedIn draft generation from the EVA activity stream. Converts deals/patterns/builds into ready-to-approve posts using the three voice modes (thought_leader / builder_log / human_story); approval-gated queue.
- **postcards** (`:8778`) — quote-card content → 1200×1200 Adam-Grant-style PNG render → scheduled publish queue → LinkedIn, behind a single `linkedin_post.py` chokepoint with an append-only publish ledger.
- **media-editor** (`:8783`) — background auto video-editor (branded 64px lower-third + loudnorm + music duck + caption cover) with durable job state that survives a restart. Requires ffmpeg.
- **linkedin** (`:8773`) — LinkedIn OAuth handler + CLI post/analytics; permanent token in `~/.eva/channels_config.json`.
- **linkedin-analytics** (`:8780`) — post-analytics sync (impressions/clicks/reactions/comments/shares/engagement). Idempotent, cron-safe snapshots behind a single network chokepoint; append-only analytics ledger.
- **brand-builder** (`:8792`) — brand strategy/orchestration layer above content-engine + social-scheduler. Writes content **briefs** (never posts; approval stays L1) from a pipeline + blueprint + personas; weekly blueprint-staleness refresh loop.

### Revenue / monetization

- **monetizing-agent** (`:8772`, Mira) — governed weekly revenue-leak detector. Sunday Mine→Match→Package→Route→Follow-up plays that rank under-monetized assets by cash proximity, behind an approval gate + immutable ledger.
- **angels** — the watchdog/monetization "angels": `angel0_sentinel` monitors service health (ports 8765–8771) and auto-restarts dead services with consecutive-failure tracking; `angel3_monetization` (Yaksha) is the ungoverned revenue-leak-scan predecessor to monetizing-agent.

### Finance / infra / hands

- **finance-tracker** (`:8786`, Treasurer) — tracks all Eva operational spend (API/LLM credits, subscriptions, fees, ad/deal costs, hosting) against per-category budget caps; classifies ok/warn/over, alerts on newly-crossed thresholds, and projects monthly run-rate.
- **deployer** (`:8789`) — event-driven CI/CD self-update agent. Polls a configurable list of deploy targets and safely ships when a remote is ahead: fast-forward-only pull for the Eva backend (restarts only changed services, gated on no in-flight work) and `vercel --prod` for eva-landing.
- **local-exec** (`:8790`) — the localhost-only "Mac hands" layer. Runs shell commands on demand: auto-runs a small allowlist of safe ops, gates everything else behind one-tap Slack approval; every run is secret-masked and audited.
- **ip-scout** (`:8791`) — L1-autonomy invention-triage lobe. Runs a daily incremental novelty / prior-art triage over invention-idea seeds and surfaces attorney-review candidates. Never files, submits, or asserts patentability — scores are heuristic signals only.

### Roadmap & integrations

- **projects** (`:8779`) — roadmap tracker: a tree of nodes in SQLite rendered as a collapsible mind-map / tree in the browser, with an append-only change ledger.
- **voice** (`:8774`) — always-on Mac voice service: wake word ("Hey EVA") + Whisper transcription + ElevenLabs TTS + command routing.
- **shopify** (`:8772`) — Shopify OAuth handler / Admin API token exchange (`/shopify/install` → `/shopify/callback`).
- **lovable-bridge** (`:8769`) — wraps the Lovable "build-with-URL" API, injects EVA context, and clones Lovable GitHub repos into `~/Eva/modules/`.
- **drive_organizer** — auto-categorizes uploaded Google Drive files (Architecture, Deal Intelligence, Personal Brand, …).

### Capability specs / scaffolds (root-level, not under `modules/`)

- **eva-video-dna** — ingest → review → approve → edit → distribute pipeline for founder videos, with a stealth-default distribution posture for raise content. Docs + light scaffold; transcription/editing are future work. See [`eva-video-dna/README.md`](../eva-video-dna/README.md).
