# EVA State Ledger (`eva-state`) · port 8769

The governed **append-only state/history ledger** — the single source of truth
for state and history *across* all Eva agents, sessions, and surfaces. Eva loses
information because no single service owns the timeline of decisions, outcomes,
and state changes. This module owns that timeline.

Kalpawriksha (the Project Map) and the Command Center become **views** of this
ledger, not independent stores that drift. It is complementary to the two
existing persistence layers, not a replacement:

| Layer | Owns | Mechanism |
|---|---|---|
| per-agent `memory.db` | local, domain-specific state | each module |
| `services/directive_sync.py` | learnings *into* agents | file bridge |
| **`eva-state`** | provenance + current state *across* agents/surfaces | this module |

## Quick start

```bash
cd modules/eva-state
bash setup.sh                     # installs deps, seeds, starts on :8769
# or, manually:
python seed.py                    # idempotent seed (Kalpawriksha import + lost state)
python main.py --port 8769        # FastAPI service
```

Offline by default in the sandbox; set `EVA_STATE_OFFLINE=1` to force stub
transports.

## The primitive: append-only events

Every meaningful thing that happens is one **event**. The `events` table has an
**immutability trigger**: identity/content columns are frozen on insert, DELETE
is blocked, and only the lifecycle `status` column may transition. Corrections
are **new events** (`correction_event` carrying `supersedes_event_id` /
`corrects_event_id`) — never edits or deletes. This mirrors the
`monetizing-agent` append-only-ledger pattern.

### Event schema

| Column | Meaning |
|---|---|
| `event_id`, `timestamp` | identity + when |
| `actor` | Vineet · Eva · subagent · system |
| `source_surface` | Perplexity · Command Center · cron · GitHub PR · Drive · Slack |
| `project`, `track` | grouping for the project map |
| `entity_type`, `entity_id` | the thing this event is about (see entity types) |
| `event_type` | what happened (see event types) |
| `summary`, `payload_json` | human line + structured detail |
| `evidence_urls` | provenance links |
| `supersedes_event_id`, `corrects_event_id` | correction chain |
| `confidence`, `status` | 0–1 confidence · current standing |

**Event types:** `decision_made`, `directive_created`, `task_created`,
`task_status_changed`, `agent_run_started`, `agent_run_completed`,
`artifact_created`, `approval_requested`, `approval_granted`, `blocker_added`,
`blocker_resolved`, `outcome_recorded`, `project_status_changed`,
`external_link_added`, `priority_changed`, `correction_event`,
`coined_term_created`, `coined_term_referenced`.

**Entity types:** `project`, `module`, `task`, `blocker`, `decision`,
`artifact`, `approval`, `agent`, `interface`, `deal`, **`coined_term`**.

### Derived views (never hand-maintained)

`project_state_view`, `task_state_view`, `daily_priority_view`,
`coined_terms_view` are SQLite views computed from the ledger. Kalpawriksha is
regenerated (`project_map.json`) from them.

## Coined terms — a first-class entity type

Coining terms is Vineet's USP (see the coined-terms directive). Each coined term
is a first-class `entity_type: coined_term` with its own `entity_id` (the
slugified term, e.g. `scissorhands`) and a full event history:

- `coined_term_created` — payload: `term, domain, definition,
  first_published_surface, first_published_url, first_published_date`.
- `coined_term_referenced` — payload: `term, surface, engagement_metrics`
  (with `engagement_metrics.total` rolled up), and an optional
  `productization_flag`.

`GET /state/coined-terms` returns each term with its **reference count**,
**last-referenced date**, and **total engagement**, so *"which coined terms have
traction"* is directly queryable. The `coined_terms_view` rolls this up per term
(term, domain, coined_date, reference_count, last_referenced, total_engagement,
productization_flags), and terms with rising traction surface in
`/state/today` as **monetization signals** — the bridge into the Monetizing
Agent's Content-to-offer / Productize plays.

The seed registers **ScissorHands** (coined 2026-07-10, *Football / defensive
technique* — "two defenders pressing a star striker from opposite sides like
scissor blades to isolate and neutralize the threat", first published on Twitter
manually 2026-07-10).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | health + last-run summary + event count |
| GET | `/directive` | current live directive |
| POST | `/events` | append an event (immutable once written) |
| GET | `/events` | filter by `project/track/entity_type/entity_id/event_type/actor/since/limit` |
| POST | `/events/{id}/correct` | write a `correction_event` superseding a prior event |
| GET | `/state/today` | priorities (blockers + deadlines + coined-term traction) |
| GET | `/state/projects` | current per-project status |
| GET | `/state/project-map` | Kalpawriksha tree derived from the ledger |
| GET | `/state/pending-approvals` | unanswered approval requests |
| GET | `/state/recent-decisions` | recent `decision_made` events |
| GET | `/state/open-blockers` | standing blockers |
| GET | `/state/agent-health` | latest run per agent (cross-agent liveness) |
| GET | `/state/coined-terms` | coined terms w/ reference count, traction, engagement |
| POST | `/admin/seed` | idempotent seed (Kalpawriksha import + lost state) |
| POST | `/admin/render-map` | regenerate `project_map.json` (+ optional `index.html`) |

## CLI

```bash
python cli.py add <event_type> --summary "…" --project "…" --entity-type task
python cli.py today             # today's priorities
python cli.py map               # Kalpawriksha tree (JSON)
python cli.py recent            # recent decisions
python cli.py open-blockers     # standing blockers
python cli.py coined-terms      # coined terms + traction
python cli.py render-map --html # regenerate project_map.json (+ index.html)
python cli.py seed              # idempotent seed
```

Wire under the shared launcher as `eva state <cmd>`.

## Kalpawriksha (Project Map) auto-generation

The static `eva-project-map/index.html` stops being hand-edited. Its data comes
from the ledger:

1. **Import** — `seed.import_project_map` parses the current static map (bundled
   under `seed/project_map_source.html`) into seed events. Each terminal node
   with a status badge becomes one event (badge map: Production-Live→`live`,
   In Progress→`in_progress`, Open→`open`, Planned→`planned`, Blocked→`blocked`).
2. **Correct stale nodes** — the map still shows `batch.ai` Open ("LOI sent,
   awaiting broker"), but Vineet walked away 2026-06-05. The seed writes a
   `correction_event` superseding it (status → `dropped`, evidence: the
   2026-06-05 walk-away).
3. **Generate** — `project_map.build_tree` derives the tree from the ledger's
   current (non-superseded) events; `render-map` writes `project_map.json` and,
   with `--html`, a static `index.html` reusing the original map's CSS/visual
   shell — populated from the JSON, not hand-maintained.

Publishing a rebuilt `index.html` to a live surface is an **irreversible action**
gated behind the execution-transport chokepoint (Stub offline; never fakes a
publish).

### Lost state (Jul 8–10) captured by the seed

Monetizing Agent (PR #20, :8772) · kb_index (shared Drive INDEX writer) · Book
Agent corpus (Rich Gomez + 33-question set) · Book Agent scaffold (:8773,
pending) · Sunday monetizing recurring task (pending retirement) · Storeys fund
formation (SEC Rule 506(c) gate) · eva-panel backend blocker (4 crons 404) ·
external Sunday cron `c31194a7` · **ScissorHands** coined term.

## Command Center integration

The `/state/*` endpoints are the **read surface** for the Command Center
(eva.mangotec.ai, currently frontend-only). It is **read-only today**.

**Switch-over roadmap (later phase):** the Command Center becomes a first-class
**state writer** — a `POST /events` on every meaningful action (priority change →
`priority_changed`; brief approval → `approval_granted`; kill a project →
`project_status_changed`; PR created → `artifact_created`; scheduled/subagent run
→ `agent_run_completed` + `artifact_created`).

## Governance

- **Append-only + immutability trigger** on `events`; corrections as new events.
- **Approval gate** on the irreversible publish action, behind a transport
  Protocol with an offline Stub.
- **No cross-agent DB reads** — siblings write via `POST /events`; learnings flow
  via `services/directive_sync.py`.
- **Idempotent seed/tick** — re-running `seed_all` never duplicates events.
- Reads `docs/MISSION.md` / `docs/CURRENT_GOALS.md` at startup if present.

## Tests

```bash
python -m pytest modules/eva-state/
```

Offline (Stub transports, zero network): append-only immutability, correction
events, coined_term entity + traction query, derived views, project-map
generation, stale-state detection (batch.ai drop), and idempotent seed.
