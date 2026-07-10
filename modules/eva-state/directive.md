# EVA State Ledger — Live Directive

version: 0.1.0
status: active
updated_at: 2026-07-10

## Purpose

The governed **append-only state/history ledger** — the single source of truth
across all Eva agents, sessions, and surfaces. Eva loses information because no
single service owns the timeline of decisions, outcomes, and state changes. This
module owns that timeline. Kalpawriksha (the Project Map) and the Command Center
become *views* of the ledger, not independent stores that drift.

It is complementary to, not competing with, the two existing persistence layers:

- **Per-agent `memory.db`** stays local and domain-specific.
- **`services/directive_sync.py`** stays the machine-readable feed that carries
  *learnings into* agents.
- **`eva-state`** carries *provenance and current state across* agents/surfaces.

## Operating Rules

1. **Append-only, always.** Every meaningful thing that happens is one event.
   The `events` table has an immutability trigger: identity/content columns are
   frozen on insert; DELETE is blocked. Only the lifecycle `status` column may
   transition.
2. **Corrections are new events.** Never edit or delete. A wrong or stale event
   is superseded by a `correction_event` carrying `supersedes_event_id` /
   `corrects_event_id`; the original is marked `superseded`. (Example: the stale
   `batch.ai` "Open — LOI sent" node is superseded by a drop correction dated to
   the 2026-06-05 walk-away.)
3. **Views are derived, never hand-maintained.** `project_state_view`,
   `task_state_view`, `daily_priority_view`, and `coined_terms_view` are computed
   from the ledger. Kalpawriksha is regenerated (`project_map.json`) from these.
4. **Coined terms are a first-class entity type.** Per Vineet's coined-terms
   directive, each coined term is an `entity_type: coined_term` with its own event
   history (`coined_term_created`, `coined_term_referenced`). "Which coined terms
   have traction" must stay queryable, and rising traction surfaces as a
   monetization signal in `/state/today`.
5. **Approval gate on irreversible actions.** Publishing a rebuilt Kalpawriksha
   `index.html` to a live surface routes through the execution transport
   chokepoint; the Stub never fakes a publish.
6. **No cross-agent DB reads.** Other agents write to this ledger via `POST
   /events`; nobody reads a sibling's SQLite directly. Learnings still flow via
   the directive-sync bridge.
7. **Read `docs/MISSION.md` and `docs/CURRENT_GOALS.md` at startup** if present
   (graceful no-op if absent).

## Event schema

`event_id, timestamp, actor, source_surface, project, track, entity_type,
entity_id, event_type, summary, payload_json, evidence_urls,
supersedes_event_id, corrects_event_id, confidence, status`.

## Command Center integration

The `/state/*` endpoints are the read surface for the Command Center
(eva.mangotec.ai). It is read-only today; the switch-over roadmap makes the
Command Center a first-class **state writer** (a `POST /events` on every
meaningful action) in a later phase.

## LEARNINGS (auto-synced)

<!-- Appended by services/directive_sync.py as cross-surface state lessons
     arrive. Each entry captures the source, decision, outcome, and lesson. -->
