# EVA Hybrid Architecture — Design Specification

Status: Draft v2 (2026-05-03)
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
