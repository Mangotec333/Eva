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

## modules/logger — EVA Activity Logger

EVA's sensing layer. Tracks app usage, screen activity, and audio transcripts.
Three-tier source hierarchy: Screenpipe → ActivityWatch → built-in daemon.

**Key files:**
- `eva_logger.py` — background daemon, JSONL activity log
- `eva_activitywatch_bridge.py` — ActivityWatch REST client + normalizer
- `eva_screenpipe_bridge.py` — Screenpipe REST client (OCR + audio)
- `eva_context_api.py` — unified REST API on :8765 for EVA agents
- `eva_summarize.py` — daily summary + focus score generator

**Quick start:**
```bash
cd modules/logger
bash setup.sh
python eva_logger.py &
python eva_context_api.py
```

**API endpoints:**
- `GET localhost:8765/context/unified` — all sources merged
- `GET localhost:8765/screenpipe/search?q=<query>` — search screen memory
- `GET localhost:8765/screenpipe/transcript?start=...&end=...` — meeting transcript

## modules/morning-os — EVA Morning OS

EVA's daily operating system. Opens in browser each morning.
Goal check-in across time horizons, priority surfacing, activity dashboard.

**Stack:** Express + Vite + React + Tailwind + shadcn/ui + Drizzle/SQLite

**Quick start:**
```bash
cd modules/morning-os
npm install
npm run dev
```

**Live deployment:** https://www.perplexity.ai/computer/a/eva-morning-os-3Tmx6H6.SsOgfEUZegsOJw

## modules/outreach — EVA Outreach & Investor Verification

Compliance-safe, approval-gated investor outreach. Approval queue (nothing is
auto-sent), accredited-investor verification workflow (SEC Rule 506(c), 365-day
expiry), global suppression/opt-out list, and an append-only compliance ledger
exportable for the Form D / blue-sky paper trail. Email transport is behind a
`sender` interface (stub/log in v1; Gmail adapter hook for later).

**Stack:** FastAPI + stdlib `sqlite3` (offline-first, no external DB)

**Key files:**
- `service.py` — all enforced compliance rules (send/sale gating, ledger)
- `database.py` — SQLite schema, indexes, append-only/immutable triggers
- `sender.py` — `Sender` interface + `StubSender` + `GmailSender` hook
- `main.py` — REST API on :8768
- `cli.py` — terminal-first approve/deny/send/optout/verify/ledger

**Quick start:**
```bash
cd modules/outreach
bash setup.sh                # REST API on :8768
python cli.py pending        # terminal workflow
python test_outreach.py      # offline test suite
```

## modules/postcards — EVA Postcards

Quote-card content + LinkedIn auto-publish. Stores Vineet's authored quotes,
renders each into a LinkedIn-style image card (Adam Grant style — soft-pink
background, rounded corners, profile header, two-paragraph reframe), queues them
on a publish schedule, and auto-posts to LinkedIn through a wired transport.
Approval-gated (only `approved` cards are released); the LinkedIn transport sits
behind a single network chokepoint (`linkedin_post.py`); an append-only publish
ledger records every render/approve/post/failure.

**Stack:** FastAPI + stdlib `sqlite3` + Pillow (offline-first, no external DB)

**Key files:**
- `service.py` — seed, render, approval gate, scheduler `tick`
- `renderer.py` — 1200x1200 Adam Grant-style PNG (ported from `render_cards.py`)
- `publisher.py` — `Publisher` interface + `StubPublisher` + `LinkedInPublisher`
- `linkedin_post.py` — the single network chokepoint (`_post_via_linkedin_api`)
- `database.py` — SQLite schema, indexes, append-only ledger triggers
- `main.py` — REST API on :8778
- `cli.py` — terminal-first seed/list/approve/render/schedule/tick/ledger

**Quick start:**
```bash
cd modules/postcards
bash setup.sh                # REST API on :8778
python cli.py seed           # load the 8 authored quote-cards
python cli.py tick           # post next due approved card (safe for cron)
python test_postcards.py     # offline test suite
```

## modules/projects — EVA Projects

Roadmap tracker that renders the whole roadmap as a collapsible mind-map / tree
in the browser (dark theme, colour-coded tier dots, status badges,
click-to-expand/collapse). Projects are stored as a tree of nodes in SQLite with
an append-only change ledger; the mind-map view is populated live from the DB.

**Stack:** FastAPI + stdlib `sqlite3` (offline-runnable), inline-CSS/JS HTML view (port 8779)

**Key files:**
- `service.py` — CRUD, cascade delete, cycle-safe move, import/export, seed
- `database.py` — `sqlite3` store, schema, append-only ledger triggers
- `main.py` — FastAPI REST API + mind-map view on :8779
- `cli.py` — terminal-first CLI (`seed/add/list/update/move/delete/import/export/ledger`)
- `templates/map.html` — ported mind-map page (tree JSON injected by the API)

**Quick start:**
```bash
cd modules/projects
bash setup.sh                # pip install, seed, launch on :8779
# mind map: http://localhost:8779/   ·   docs: /docs   ·   health: /health
```

## modules/linkedin-analytics — EVA LinkedIn Analytics

Reads LinkedIn post analytics (impressions, clicks, reactions, comments, shares,
engagement rate) and stores normalized snapshots + raw payloads in SQLite.
Idempotent, cron-safe sync behind a single network chokepoint
(`linkedin_analytics.py`); append-only analytics ledger. FastAPI on `:8780`.

**Quick start:**
```bash
cd modules/linkedin-analytics
bash setup.sh
```

## modules/channels — EVA Channels (multi-platform publish)

Approval-gated, idempotent multi-platform publishing behind a common `Publisher` Protocol (v1: Reddit + Substack). FastAPI `:8781`, own SQLite, CLI, append-only ledger, iconized dashboard. See `modules/channels/README.md`.

## eva-video-dna — Video DNA & Review/Edit (capability spec + scaffold)

Ingest→review→approve→edit→distribute pipeline for founder videos, with a stealth-default distribution posture for raise content. Docs + light scaffold (root-level `eva-video-dna/`); transcription/editing are future work. See [`eva-video-dna/README.md`](../eva-video-dna/README.md).

## modules/ghl-agent — EVA GHL Agent (GoHighLevel integration)

The single Eva-owned service that talks to GoHighLevel. Owns both the one-time, idempotent campaign/funnel build (the "Eva Acquisition" pipeline, "Eva Demo Call" calendar, `source` custom field, the voice-DNA 7-touch 21-day sequence, and the tag-triggered workflow) AND the ongoing lead-capture automation loop (upsert → tag → pipeline → campaign enroll, plus GHL webhooks mapped to lead-lifecycle events emitted to the State Ledger on `:8769`). GHL access sits behind a `GHLClient` Protocol (OAuth token from env `GHL_ACCESS_TOKEN`; offline stub for tests). FastAPI `:8782`, own SQLite with two append-only ledgers, CLI. UI-only GHL endpoints (workflow creation, some template APIs) degrade to `manual_required` rather than failing the build. See `modules/ghl-agent/README.md`.

## modules/remote-bridge — EVA Remote-Bridge (authenticated remote instruction channel)

The ONE authenticated front door: it lets the founder send Eva a natural-language instruction from anywhere (phone, Slack, Perplexity Computer) over a cloudflared tunnel. `POST /remote/instruct {"goal"}` persists the instruction, returns an instant `{instruction_id}` receipt, then forwards the goal in the background to Diracatron's registry-scoped `/triage/dispatch` (`:8784`) and tracks the outcome (received → dispatched → complete | failed). The deliberate opposite of `local-exec`: it IS meant to be tunnel-exposed, so **bearer auth is mandatory on every `/remote/*` route** (env `REMOTE_BRIDGE_API_KEY`) and **fails closed** — if the key is unset every route returns `503`, never allow-all. Fixed-window rate limiting (30 req/min → `429`), `DispatchClient`/`StateLedgerClient` Protocols with offline stubs, own SQLite with an append-only `instruction_ledger`, CLI. FastAPI `:8795`. It only ever forwards a goal to Diracatron's registry-scoped dispatch — never raw shell, never local-exec. See `modules/remote-bridge/README.md`.
