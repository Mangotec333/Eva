# EVA Hybrid Architecture — Design Specification

Status: **Final v1** (2026-07-17) — architecture confirmed, browser automation finalized under T2.
Audience: contributors implementing EVA modules.

## 1. Goals

EVA is a local-first voice assistant. The validated direction is a **hybrid**
architecture in which EVA itself is small and stable, and a remote brain
(Perplexity Computer) is invoked whenever local capability is insufficient.

**Perplexity Computer is EVA's primary remote horsepower layer.** It already
performs the heavy lifting EVA needs — orchestration, model and tool
selection across an evolving roster of frontier models, code synthesis and
stitching, research/search, memory and context handoff, and long-running
task execution. EVA does not try to reproduce that surface. When the local
tier (LOCAL_TOOL / API_ADAPTER) cannot serve a request, EVA hands it off to
Perplexity Computer with the necessary context.

- Keep EVA cheap to run, private by default, and responsive on commodity
  hardware.
- Treat the remote brain as **infrastructure**, not as the default capability
  surface.
- Make capability accretion observable: any successful dynamic workflow can be
  promoted to a stable local adapter, paying the credit/latency cost only once.
- Preserve the safety contract: every request is completed, clarified,
  transformed, deferred, or explicitly refused — never silently dropped.

## 2. Non-goals

- We do **not** build a Perplexity-native skill ecosystem. Skills there are
  scaffolding for orchestration, not the canonical home of EVA capabilities.
- We do not build a multi-tenant, internet-exposed service. The bridge stays
  loopback-only without an explicit auth layer.
- We do not invest in cross-platform GUI in this phase; voice + CLI + bridge
  are sufficient.
- No always-on cloud listening. STT and wake-word stay local.

## 3. High-level flow

```text
mic / push-to-talk
   |
   v
[ EVA shell ]  -- listener, VAD, STT, state, TTS, audit log
   |
   v
[ Brain Orchestrator ] -- policy + routing decision
   |
   +--> LOCAL_TOOL          (deterministic, free, instant)
   +--> API_ADAPTER         (stable local service, e.g. reminders)
   +--> PERPLEXITY_COMPUTER (primary remote brain: reasoning, search, planning,
   |                        code stitching, long-running orchestration)
   +--> DYNAMIC_BUILD       (remote brain stitches a one-off workflow)
   +--> EXTERNAL_AGENT      (optional; named third-party agent — e.g. MANUS —
   |                        only when explicitly preferred and policy-allowed)
   +--> CLARIFY             (ambiguous; ask a single targeted question)
   +--> APPROVAL_REQUIRED   (high-impact / irreversible / external side effect)
   |
   v
[ Executor ]   -- runs the chosen route, streams progress
   |
   v
[ TTS + task log ]
```

## 4. Component responsibilities

| Component | Owns | Does NOT own |
|---|---|---|
| Voice shell (`services/voice`) | mic, VAD, push-to-talk, TTS, turn loop | reasoning, planning |
| STT (`services/stt`) | local transcription adapters | LLM calls |
| Brain orchestrator (`services/brain`) | route decision, policy, response shape | side effects |
| Routing (`services/brain/routing.py`, **new**) | classify each task into a `RouteKind` | model inference |
| Local tools (`services/reminders`, future `services/tools/*`) | cheap, deterministic, private actions | reasoning |
| API adapters (future `services/adapters/*`) | wrap a stable local service behind a typed contract | UI |
| Bridge (`services/bridge`) | loopback HTTP API for clients | auth, rate limits |
| Perplexity client (future `services/remote/perplexity.py`) | request/response framing for remote brain | execution |

## 5. Routing policy

The router consumes a small, structured `RoutingInput` and returns a
`RoutingDecision`. The router never calls a model; it is a pure function of
its inputs. Inputs include:

- `utterance` — raw user text
- `signals` — derived booleans (looks_like_reminder, looks_high_impact,
  matches_known_adapter, requires_fresh_world_knowledge, novel_workflow,
  user_explicit_approval, prefers_external_agent)
- `policy` — operator-tunable knobs (allow_remote, allow_dynamic_build,
  allow_external_agent, credit_budget_remaining)

Decision precedence (top wins):

1. **CLARIFY** — empty / unparseable / contradictory utterance.
2. **APPROVAL_REQUIRED** — irreversible or external side effect AND not
   pre-approved.
3. **LOCAL_TOOL** — known cheap deterministic match (e.g. reminder).
4. **API_ADAPTER** — known stable adapter matches.
5. **EXTERNAL_AGENT** — caller has explicitly signalled a named third-party
   agent (e.g. MANUS) AND `policy.allow_external_agent` is set AND the
   agent is configured. Only fires when the operator has declared the
   external agent fills a known gap vs. Perplexity Computer; otherwise the
   request falls through to PERPLEXITY_COMPUTER.
6. **PERPLEXITY_COMPUTER** — needs reasoning or fresh world knowledge AND
   `policy.allow_remote`. This is the default remote tier.
7. **DYNAMIC_BUILD** — novel multi-step workflow AND
   `policy.allow_dynamic_build` AND credit budget allows. In practice
   DYNAMIC_BUILD is executed *through* Perplexity Computer; the separate
   route kind exists so the executor can apply a tighter approval and
   credit policy to one-off code stitching.
8. Fallback: **CLARIFY**, never silently drop.

## 6. Tool tiers

| Tier | Latency budget | Cost | Examples |
|---|---|---|---|
| T0 LOCAL_TOOL | < 50 ms | free | reminders, timers, clipboard, calc |
| T1 API_ADAPTER | < 500 ms | free | local Ollama, file index, shell wrappers |
| T2 PERPLEXITY_COMPUTER | seconds | metered | reasoning, search, summarisation, model/tool selection, long-running orchestration |
| T3 DYNAMIC_BUILD | seconds–minutes | metered + risk | one-off code stitching |
| T2x EXTERNAL_AGENT | seconds–minutes | metered + policy | optional MANUS-like or future third-party agents |

T2 is the default remote tier and absorbs most non-local work. T2x is an
**opt-in** sibling: it is never a default dependency, only fires when an
operator has explicitly enabled and named an external agent, and is
intended for cases where that agent fills a real gap vs. Perplexity
Computer (a niche capability, a contractual requirement, a benchmark the
operator has independently validated). Adding a new external agent must
not require touching EVA core; it is a configuration + thin adapter.

Promotion path: a T3 workflow that succeeds repeatedly is rewritten as a T1
adapter and routing prefers the adapter on subsequent calls.

## 7. Approval and safety rules

- Verbs in `HIGH_IMPACT_TERMS` (`send`, `delete`, `purchase`, `transfer`, …)
  route to APPROVAL_REQUIRED unless the user explicitly pre-approved this
  exact action in the same turn.
- Approval is per-action and per-turn. There is no global "yes to everything".
- Remote routes (T2/T3) never bypass approval; if a remote-suggested plan
  contains a high-impact verb, the executor halts and re-prompts.
- Every decision is recorded in `data/voice_tasks.jsonl` with route kind and
  reason — required for after-the-fact review.

## 8. Persistence and memory

- Per-turn audit log: append-only JSONL, local file.
- Reminders: in-process min-heap for the lifetime of `eva text` / `eva voice`
  (already implemented).
- Long-term memory: deferred. When introduced it will be a local sqlite store
  with explicit consent per write, not an opaque vector blob.
- The remote brain is **stateless from EVA's perspective**: any context it
  needs is sent on the request. No silent server-side accumulation.

## 9. Economical credit policy

- A `credit_budget_remaining` value (operator-set, default conservative)
  flows into routing input.
- Hard rule: T2/T3 routes are skipped when budget is at or below zero —
  router falls back to LOCAL_TOOL/API_ADAPTER if available, else CLARIFY.
- DYNAMIC_BUILD costs more credits than PERPLEXITY_COMPUTER; routing
  prefers T2 over T3 when both could plausibly serve the request.
- Successful T3 workflows are promoted to T1, removing future T3 spend.

## 10. Module-by-module roadmap

1. **`services/brain/routing.py`** (this PR) — pure routing decision
   abstraction with `RouteKind`, `RoutingInput`, `RoutingDecision`,
   `decide_route()`. Covered by unit tests. Existing `policy.py` keeps its
   coarse approval/clarify/answer/reminder split; routing is the richer
   layer that calls into it.
2. **`services/adapters/`** — first stable local adapter (file index or
   shell-wrapped tool) behind a typed contract.
3. **`services/remote/perplexity.py`** *(scaffolded)* — typed
   `PerplexityRequest`/`PerplexityResponse` framing plus a
   `PerplexityClient` Protocol. Ships with a `MockPerplexityClient` for
   tests and a `NoopPerplexityClient` that fails safely when no
   transport is configured. The real HTTP transport against Perplexity
   Computer is a future integration; nothing in the default test or
   runtime path performs network calls.
4. **`services/brain/executor.py`** *(scaffolded)* — `RouteExecutor`
   consumes a `RoutingDecision` and dispatches `PERPLEXITY_COMPUTER` to
   the remote client. Returns an `ExecutionResult` carrying the audit
   fields (`task_id`, `route`, `utterance`, `status`, `summary`,
   `needs_approval`, `error`). `LOCAL_TOOL` and clarify/approval flows
   continue to be handled by the orchestrator and are unchanged. Other
   remote routes (`DYNAMIC_BUILD`, `EXTERNAL_AGENT`) currently produce a
   `not_implemented` audit entry pending their own modules.
5. **Promotion tooling** — script to inspect successful T3 traces and
   scaffold a T1 adapter from them.
6. **Optional external-agent adapters** (`services/remote/external/*`) —
   thin, per-agent clients (e.g. MANUS) gated behind
   `policy.allow_external_agent` and a named-agent config entry. Not a
   default dependency; only built when an operator has identified a
   concrete gap vs. Perplexity Computer.

## 11. Market watch / new releases

The agent/tool landscape moves quickly. EVA should periodically re-evaluate
whether a newly-released agent, model, or platform changes the calculus
above — most notably whether it should become a configured EXTERNAL_AGENT,
or whether Perplexity Computer's coverage has grown enough that a planned
adapter is now redundant.

This re-evaluation is **not** hardcoded into EVA. There is no built-in
scraper, no scheduled network fetch, and no implicit dependency on any
third-party release feed. Instead:

- Operators who want recurring market watch configure it as a normal
  scheduled task (cron, Claude Code routine, calendar reminder) that opens
  an issue or writes a note.
- Findings update this document and, where appropriate, the roadmap in
  section 10. Adding a new EXTERNAL_AGENT entry requires a config change,
  a thin adapter, and an explicit operator policy flag — never a silent
  default.

## 12. Out of scope for this document

- Wake-word UX details (covered in `phase-1-macos-voice-qa.md`).
- Specific Perplexity wire format (lives with the remote client when added).
- GUI client design.

## 13a. Recorded decision (2026-07-17) — Browser automation finalized

- **Browser automation is served TODAY via T2 (Perplexity Computer), not a
  dedicated local adapter.** PC has native cloud-browser automation plus
  the ability to drive the operator's own logged-in Comet browser session
  (cookies/auth preserved). Validated live 2026-07-17: PC logged into GHL
  and worked pipeline/opportunity setup end-to-end with no EVA-side code.
- The section-13 "third" API-adapter slot for local browser automation
  stays on the roadmap only as a **future cost/latency optimization**
  (build a T1 adapter if a specific browser workflow becomes
  high-frequency enough to justify it) — it is not required to get
  browser capability now. Until promoted, all browser tasks route
  PERPLEXITY_COMPUTER (T2) by default.
- No change to the tier model: PC remains the default T2 horsepower layer;
  this decision just closes the open question of "how does EVA get
  browser automation" — answer: through PC, already working.

## 13. Recorded decisions (2026-05-03)

These are operator-confirmed defaults for the next implementation phase.
They are recorded here so future PRs do not have to re-litigate the same
calls.

- **Wake phrase / assistant name:** `AVA`. EVA/EVE remain accepted aliases
  for backward compatibility with existing config and docs, but new
  surfaces should treat AVA as the canonical name.
- **Default Ollama model:** `llama3.2`. The model stays configurable
  (`config/eva.example.yaml` → `model.ollama_model`); only the default
  changes. Operators are expected to override this for stronger or
  smaller models depending on their hardware.
- **Manual stop:** the manual-stop control surface is exposed through
  the existing voice loop and bridge; we deliberately keep it small and
  do not rewrite the UI in this phase.
- **Durable memory:** durable memory is the next priority. Persistent
  reminders explicitly **wait** until the durable memory layer exists —
  there is no point persisting reminders before the storage substrate
  is settled.
- **First stable API adapters (in order):** local files first, shell
  command wrapper second, browser automation third. The organizer
  (`services/brain/organizer.py`) emits route hints aligned with this
  order so subsequent adapter PRs have a predictable surface to plug
  into.
- **Request organizer first:** before any further routing or adapter
  work, a deterministic local *organizer* is built that takes any
  request and produces a structured `OrganizedRequest`. The organizer
  asks focused clarifying questions when the request is empty, vague,
  or missing required slots; it does not call models or the network.
  See `services/brain/organizer.py`.
- **Perplexity Computer remains the primary remote brain.** None of the
  decisions above change the tier model in section 6 — Perplexity
  Computer is still the default T2 horsepower/orchestrator. Optional
  third-party agents (EXTERNAL_AGENT) stay gated behind explicit
  operator config; they are not promoted to defaults by this phase.

## 14. Autonomous agent loop model (2026-07-08)

Operator-confirmed today. This section EXTENDS the tier model (section 6); it
does not replace it. It documents the piece the original doc lacked: the
**loop-runner** — how an autonomous agent maintains context and calls the right
brain for each kind of work.

### 14.1 Brain / Hands / Nervous-system split

| Role | Who | Tier | Notes |
|---|---|---|---|
| **Brain — reasoning** | Claude / Anthropic API | T2 (metered) | Judgement, edge-case rationale, lever assessment, confidence flags. Called per reasoning-step, **stateless**. `services/remote/claude.py`. |
| **Brain — research / orchestration** | Perplexity Computer | T2 (metered) | Market enrichment connectors (Statista, CB Insights, Similarweb) and long-running orchestration live here. Reached via `services/remote/perplexity.py`. |
| **Hands** | Agent microservices | T0–T2 | Each runs its own `observe → reason → act → learn` loop with a **deterministic core** (e.g. `scoring_v7.py`) + connectors. First instance: `modules/deal-analyzer-agent`. |
| **Nervous system** | routing + executor + directive-sync | T0 | `routing.py` decides, `executor.py` dispatches, `services/directive_sync.py` feeds learnings back. |

Two brains, deliberately: **reasoning** (Claude — judgement over given facts) is
distinct from **research** (Perplexity — going out and gathering facts + heavy
orchestration). An agent calls Claude to *think* and Perplexity to *find out*.

### 14.2 The loop-runner and where context lives

Each agent is an autonomous loop. **EVA holds the loop context locally** — the
deal, the deterministic scores, the observed enrichment, the run history in
`memory.db`. The brains are called **stateless per step**: everything a brain
needs is packed into that single request (consistent with §8 — "the remote
brain is stateless from EVA's perspective"). There is no server-side session to
resync; if the process restarts, context is rehydrated from `memory.db`.

Cost/latency per step of the loop:

| Step | Runs on | Tier | Cost |
|---|---|---|---|
| `observe()` | local + cached enrichment (NicheCache) | T0 | free (cache hit) |
| `reason()` — deterministic core (`analyze_deal_v7`) | **local** | T0 | **free, authoritative** |
| `reason()` — judgement layer (Claude) | remote | T2 | metered (tokens logged to `agent_runs`) |
| enrichment gather (Perplexity connectors) | remote | T2 | metered (cached 14d by niche) |
| `act()` / `learn()` | local sqlite | T0 | free |

The deterministic core is **never** gated behind a brain: with a
`NoopClaudeClient` (no key) and a `NoopPerplexityClient` (no transport) the loop
still completes and produces full scores — the advisory layer is simply empty
and `tokens=0`. Brains are additive, never load-bearing for correctness.

### 14.3 Loop flow

```text
                        ┌──────────────────────────────────────────┐
                        │  LOOP-RUNNER  (agent process, holds ctx)   │
                        │        run_loop() polls a deal source      │
                        └───────────────────┬────────────────────────┘
                                            │  new deal(s)
                                            v
   ┌─ observe() ──────────────────────────────────────────────────────────┐
   │   gather deal + cached enrichment (NicheCache)                         │
   │   cache miss ─────────► Perplexity Computer (T2)  ── Statista /        │
   │                          research/enrichment       CB Insights /       │
   │                                                     Similarweb          │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    v
   ┌─ reason() ────────────────────────────────────────────────────────────┐
   │   1) analyze_deal_v7()  [LOCAL, T0, deterministic, authoritative]       │
   │   2) Claude (T2) judgement ON TOP  ── scores passed in as context ─────►│
   │      returns qualitative_notes / lever_assessments / confidence_flags   │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    v
   ┌─ act() ─────────────────────────────────────────────────────────────── ┐
   │   persist deal + scores + agent_run (with token usage) → memory.db      │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    v
   ┌─ learn() ─────────────────────────────────────────────────────────────┐
   │   record outcome; learn.recalibrate() PROPOSES weight deltas            │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    v
         ┌──────────────────  DIRECTIVE-SYNC BRIDGE  ─────────────────────┐
         │  services/directive_sync.py                                     │
         │  conversations/decisions → data/directive_inbox.jsonl           │
         │  sync_loop() drains inbox → appends to directive.md             │
         │  "## LEARNINGS (auto-synced)" + versions memory.db              │
         └─────────────────────────────────────────────────────────────────┘
                     (feeds the next observe()'s directive context)
```

### 14.4 Directive-sync bridge

Routing/executor push work OUT to agents; the directive-sync bridge pushes
distilled knowledge IN, closing the loop. It is file-based (no new service): a
producer — a conversation turn or the learning loop — appends one JSON line to
`data/directive_inbox.jsonl`; `sync_loop()` drains it, appending timestamped
entries to the target agent's `directive.md` under `## LEARNINGS (auto-synced)`
and recording a `directive_version` row in that agent's `memory.db`. A cursor
file makes application exactly-once across restarts. The agent reads its live
directive at the top of every `observe()`, so synced learnings shape the next
reasoning pass.

### 14.5 What is still stubbed

- The **deal source** for `run_loop()` is a seam — plug in deal-scout / external
  connectors. The loop machinery itself is real (it iterates, scores, sleeps).
- Real **Claude** calls need `ANTHROPIC_API_KEY` in the environment; without it
  the loop runs deterministic-only.
- Real **enrichment** needs a concrete `PerplexityClient` transport wired to
  Perplexity Computer; the Noop/Mock clients keep everything offline-safe.

### 14.6 Cost-gate cascade (simplified, 2026-07-08)

We PIVOTED away from a tiered multi-provider brain (Claude + Ollama + a 3-tier
router) — that was over-engineering before we had measured any LLM lift over the
deterministic **v7** score. The leaner model keeps the swap-and-play seam but
drops the machinery. Guiding rule: **the deterministic v7 score is the
authoritative, free engine and is NEVER gated behind a brain.**

The per-deal hot loop is entirely free and deterministic:

```
                         deal in
                            |
                   ┌────────▼────────┐
                   │  GATE 1: radar  │  free, no cost. 4 checks:
                   │  (radar.py)     │  data-completeness, category/niche fit,
                   └────────┬────────┘  price band, red-flag screen.
                     drop ◄─┤ fail       Unknown fields fail OPEN. Never raises.
                    (log)   │ pass
                   ┌────────▼────────┐
                   │ FREE enrichment │  Statista + Bing, per-niche 14-day cache.
                   │ (gather_enrich) │  Runs EARLY to FEED v7.
                   └────────┬────────┘
                   ┌────────▼────────┐
                   │  v7 SCORE       │  scoring_v7.analyze_deal_v7 — AUTHORITATIVE,
                   │  (deterministic)│  free, local. The single source of truth.
                   └────────┬────────┘
                   ┌────────▼────────┐
                   │  route_deal()   │  TWO buckets (not three):
                   └───┬─────────┬───┘  score >= 7.5 => SHORTLIST, else LOG_ONLY
             LOG_ONLY  │         │  SHORTLIST
          ┌───────────▼──┐   ┌──▼─────────────────────────────┐
          │ persist only │   │ DEEP DIVE (opt-in, not default)│
          │ tokens = 0   │   │  • PAID enrichment (CB Insights │
          │ NO brain     │   │    + Similarweb) -> re-score v7 │
          └──────────────┘   │  • Claude SECOND-OPINION iff    │
                             │    second_opinion.enabled + key │
                             └────────────────────────────────┘
```

Key points:

- **Gate 1 radar** (`radar.py`) is the cheapest filter: pure-Python heuristics
  that drop unfit deals before any spend. Thresholds + the allowed-category set
  come from `config/cost_gates.yaml` — no magic numbers in code.
- **Free enrichment** (Statista + Bing) is per-niche cached (14 days) and runs
  early so its market signal feeds the authoritative v7 score. **Paid
  enrichment** (CB Insights + Similarweb) is a SEPARATE explicit call
  (`gather_paid_enrichment`) used ONLY on the shortlist — never per-deal.
- **Routing** (`cost_gate.py`) sorts survivors into `SHORTLIST` (deep-dive) or
  `LOG_ONLY` (scored + persisted, no paid work, no brain). This is configurable
  logging/routing, NOT a multi-brain router.
- **Claude is an OPTIONAL second-opinion, NOT a hot-loop brain.** It runs only on
  a SHORTLIST deal AND when `second_opinion.enabled` is true AND a key is present
  (or on every survivor in testing mode). LOG_ONLY deals log `tokens=0`. The
  generic `BrainClient` Protocol seam is kept so Claude can be re-plugged as a
  hot-loop brain later if data justifies it.
- **Testing mode** (`EVA_TEST_MODE=1` or `testing.open_all_gates: true`) bypasses
  the cascade: every Gate-1 survivor gets full treatment (paid enrichment +
  second-opinion) regardless of v7 score, and a `training_observation` row
  (features, enrichment, v7 score, brain output, tier, gate trace) is persisted
  to collect labeled data BEFORE we trust the gate. Default OFF in production.
- **Ollama mid-tier is DEFERRED** — no second model provider is built now.
- **Closed-deal scouting** is a separate follow-up. The cascade + learning
  records already accept an optional `known_outcome` (sale_price, final_multiple,
  time_to_close_days) so closed deals can feed `learn.recalibrate` with a real
  result once that sourcing microservice exists.
