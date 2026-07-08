# EVA Modules

Standalone modules that power EVA's sensing and operating layers.
Each module is independently deployable and validates as a micro-SaaS candidate.

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
# EVA Modules

Standalone modules that power EVA's sensing and operating layers.
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