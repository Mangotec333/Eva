# EVA Diracatron — Eva's top-level orchestrator & dispatcher

> Diracatron is Eva's single orchestration brain. It owns orchestration: all
> ingestion and actions are triggered through Eva, and **Eva decides which
> agents to invoke.** It reads open doors (eva-state + activity + signals +
> deal-scout's scored/gated deals + market signals), ruthlessly stack-ranks them
> from first principles, decides which lobes to fire, triggers them, collects
> results, and logs every decision + outcome back to eva-state so Eva learns.

The **Elon Musk-style advisor** and the **PM / orchestrator** function are
**folded into Diracatron** — there is exactly one triage brain, no competing
orchestrators.

---

## Three surfaces (the three verbs)

### 1. `POST /triage/run` — ruthless prioritization of open doors
Ingests every open door and stack-ranks it with a first-principles rationale:
- **deal-scout** scored + gated deals, read straight from its SQLite `DealStore`
  (`modules/deal-scout/eva-deal-scout.db`) — only `us_eligible`, available,
  above-threshold doors, carrying `overall_score` + buy-vs-build,
- **eva-state** ledger events + derived pending-approvals / open-blockers,
- logger **context/activity** API,
- **market signals / revenue paths** (`EVA_MARKET_SIGNALS[_FILE]`),
- an optional inbound signals feed.

Each ranked item is stamped with an Elon-style *why-this-why-now* rationale
(`first_principles_rationale`): a human waiting beats new work; cash-in beats
cost-out; a high-scoring door beats a marginal one; a stall is a leak to plug.

### 2. `POST /triage/dispatch` — Eva's dispatch brain
Takes a **goal/intent** and reasons from first principles (Elon-style prompt via
the repo's shared LLM client, `services/remote/claude`) to decide **which
agents/lobes to invoke, with what payloads** — then triggers them through the
registry, collects results, and logs the decision + every outcome to eva-state.

```jsonc
POST /triage/dispatch  {"goal": "get the highest-leverage acquisition moving"}
// or dispatch one already-queued item:
POST /triage/dispatch  {"item_id": "..."}
```

The LLM may only pick agents/actions that exist in the registry — hallucinated
agents are dropped. With no API key (sandbox default) it degrades to a
deterministic keyword→lobe **heuristic planner**, so a goal is *always* turned
into an executable plan.

### 3. `GET/POST /triage/queue` — read the prioritized queue
The current ranked, still-open queue (highest leverage first).

## The agent registry (data-driven — adding a lobe is a config edit)

`agent_registry.json` is the single source of truth for every lobe Diracatron
can orchestrate. Each entry declares identity, port, health, `role`,
plain-language `capabilities` (so the LLM knows *when* to use it), an `actions`
map (`action → {method, route}` — the HTTP invocation interface), and an
optional `cli` block (`{cwd, entry}` fallback). **Add an object to the JSON and
Diracatron discovers, reasons about, and invokes the new lobe — no code change.**

Registered lobes: `context-api` :8765, `deal-scout` :8766, `content-engine`
:8767, `launcher` :8768, `eva-state` :8769, `channels` :8770, `knowledge`
:8771, `voice` :8774, `ghl-agent` :8782, `treasurer` :8786, `social-scheduler`
:8787, `deployer` :8789, `local-exec` :8790, `ip-scout` :8791, `brand-builder`
:8792.

## Routes (`:8784`)

| Route | Purpose |
|-------|---------|
| `GET  /health` | health + open-queue count + offline flag |
| `GET  /triage/queue` | current ranked, still-open queue |
| `POST /triage/run` | ingest open doors → ruthless first-principles stack-rank |
| `POST /triage/dispatch` | dispatch brain: `{goal}` → decide → invoke → log, or `{item_id}` |
| `POST /triage/digest` | prioritized stack-rank of open doors (nightly job) |
| `GET  /triage/registry` | the data-driven agent registry (all lobes) |
| `GET  /triage/history` | recent dispatch decisions (audit trail) |

Also registered on the launcher (`:8768`) via lazy import.

## Triggers

- **On-demand:** the HTTP routes above (and the CLI).
- **Nightly digest:** `launchd/com.eva.diracatron-digest.plist` runs
  `cli.py digest --alert` on a `StartCalendarInterval` (22:00) — one triage pass
  then a posted, prioritized stack-rank of open doors / market potential.

## CLI

```bash
python cli.py run                         # ingest + first-principles stack-rank
python cli.py queue                       # show the current ranked queue
python cli.py dispatch --goal "..."       # dispatch brain: goal → decide → invoke
python cli.py dispatch <item_id>          # dispatch a specific queued item
python cli.py digest --top 10 [--alert]   # prioritized stack-rank of open doors
python cli.py registry                    # show the data-driven agent registry
python cli.py history --limit 20          # audit recent dispatch decisions
```

## Files

```
agent_registry.json    the data-driven registry of all lobes (edit to add one)
registry.py            AgentRegistry + Invoker (HTTP/CLI; stub for tests)
dispatch_brain.py      LLM (Elon first-principles) + heuristic planner
deal_source.py         deal-scout SQLite source + market-signal source
diracatron.py          brain: kinds, priority, routing, sources, first-principles rationale
service.py             DiracatronService: run_pass / dispatch / dispatch_goal / digest
main.py                FastAPI service on :8784
store.py               sqlite: triage_queue (idempotent) + dispatch_history
state_client.py        eva-state ledger emitter (Protocol; stub for tests)
cli.py                 CLI mirror of every route
launchd/               service plist + nightly digest plist
test_diracatron.py     offline test suite (stub sources/dispatcher/ledger/invoker/LLM)
```

## Design constraints (match the repo)

- **Stdlib only** for transport (`urllib`, `sqlite3`, `json`, `hashlib`) + FastAPI.
  The shared LLM client (`services/remote/claude`) is itself stdlib `urllib`.
- **Never hardcode secrets.** Tokens/URLs/DB paths come from the environment.
- **Offline/mock only for tests.** `EVA_DIRACATRON_OFFLINE=1` makes all sources,
  the planner, the invoker, dispatch, and ledger writes use stubs — nothing real
  is fired. Sandbox default.
- **Fail safe.** A dead ledger / down agent / missing DB / missing API key
  degrades to an honest `ok=False` or the deterministic fallback — never a raised
  exception or a faked success.

## Status

`active` — data-driven registry (15 lobes), first-principles dispatch brain,
open-door stack-rank (incl. deal-scout DealStore), nightly digest, and full
decision+outcome logging to eva-state. One orchestrator; the Elon advisor + PM
function are folded in.
