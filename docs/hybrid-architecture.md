# EVA Hybrid Architecture — Design Specification

Status: Draft v1 (2026-05-02)
Audience: contributors implementing EVA modules.

## 1. Goals

EVA is a local-first voice assistant. The validated direction is a **hybrid**
architecture in which EVA itself is small and stable, and a remote brain
(Perplexity Computer) is invoked only when local capability is insufficient.

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
   +--> PERPLEXITY_COMPUTER (remote brain: reasoning, search, planning)
   +--> DYNAMIC_BUILD       (remote brain stitches a one-off workflow)
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
  user_explicit_approval)
- `policy` — operator-tunable knobs (allow_remote, allow_dynamic_build,
  credit_budget_remaining)

Decision precedence (top wins):

1. **CLARIFY** — empty / unparseable / contradictory utterance.
2. **APPROVAL_REQUIRED** — irreversible or external side effect AND not
   pre-approved.
3. **LOCAL_TOOL** — known cheap deterministic match (e.g. reminder).
4. **API_ADAPTER** — known stable adapter matches.
5. **PERPLEXITY_COMPUTER** — needs reasoning or fresh world knowledge AND
   `policy.allow_remote`.
6. **DYNAMIC_BUILD** — novel multi-step workflow AND
   `policy.allow_dynamic_build` AND credit budget allows.
7. Fallback: **CLARIFY**, never silently drop.

## 6. Tool tiers

| Tier | Latency budget | Cost | Examples |
|---|---|---|---|
| T0 LOCAL_TOOL | < 50 ms | free | reminders, timers, clipboard, calc |
| T1 API_ADAPTER | < 500 ms | free | local Ollama, file index, shell wrappers |
| T2 PERPLEXITY_COMPUTER | seconds | metered | reasoning, search, summarisation |
| T3 DYNAMIC_BUILD | seconds–minutes | metered + risk | one-off code stitching |

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
3. **`services/remote/perplexity.py`** — request/response framing for the
   remote brain, behind a feature flag.
4. **`services/brain/executor.py`** — explicit executor that consumes a
   `RoutingDecision` and dispatches to the right tier with audit logging.
5. **Promotion tooling** — script to inspect successful T3 traces and
   scaffold a T1 adapter from them.

## 11. Out of scope for this document

- Wake-word UX details (covered in `phase-1-macos-voice-qa.md`).
- Specific Perplexity wire format (lives with the remote client when added).
- GUI client design.
