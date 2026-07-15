# EVA Diracatron — the top-level autonomous triage brain

> Diracatron sits on top of everything as the primary triage agent that knows everything that is happening. It reads eva-state + activity + signals, ranks priorities, dispatches to agents, and logs decisions back to eva-state so Eva learns. This fills the autonomy gap for the 2-month handoff to Eva as primary console.

---

## Role

Eva already has a **control plane** (`launcher` :8768) and a **memory ledger**
(`eva-state` :8769), but no reasoning brain that reads that state, decides what
matters most, and puts the right agent to work. Diracatron is that brain — the
new top-level orchestration layer that sits **above** every other Eva agent.

## The loop (one triage pass)

```
poll ──▶ normalise ──▶ rank ──▶ queue (idempotent) ──▶ dispatch ──▶ learn
```

1. **Poll** three read surfaces (behind Protocols — tests use stubs, no network):
   - eva-state append-only ledger (`:8769`) — recent `/events` + derived
     `/state/pending-approvals` and `/state/open-blockers`,
   - logger context/activity API (`:8765`),
   - an optional inbound signals feed (`EVA_SIGNALS_URL`).
2. **Normalise** every raw item into a candidate `{kind, entity_id, summary, source, payload}`.
3. **Rank** by priority = kind weight + payload bumps (urgent flag, high deal score).
4. **Queue** candidates idempotently into SQLite (a stable `signature` dedups
   repeat passes — cron-safe, like the social-publish store).
5. **Dispatch** a chosen item to the downstream agent that owns its kind.
6. **Learn** — every pass and every dispatch is logged back to eva-state via
   `state_client`, so the system's timeline records what Diracatron decided.

### Kinds → priority → downstream agent

| Kind | Priority | Downstream agent | Route |
|------|---------:|------------------|-------|
| `broker_reply` | 100 | pathfinder (`:8773`) | `/pathfinder/lead` |
| `new_lead` | 90 | ghl-agent (`:8782`) | `/lead/capture` |
| `deal_score_threshold` | 80 | deal-scout (`:8766`) | `/deals/score` |
| `revenue_leak` | 70 | monetizing-agent (`:8772`) | `/scan` |
| `content_draft_pending` | 60 | social-publish (via launcher `:8768`) | `/social/submit` |
| `stalled_task` | 50 | content-engine (`:8767`) or the stalled agent | `/tick` |

A `stalled_task` routes back to the agent named in its payload when known,
otherwise to its default.

## Routes (`:8784`)

| Route | Purpose |
|-------|---------|
| `GET  /health` | health + open-queue count + offline flag |
| `GET  /triage/queue` | current ranked, still-open queue |
| `POST /triage/run` | run one triage pass (poll → rank → queue) |
| `POST /triage/dispatch` | dispatch a specific queued item (`{"item_id": "..."}`) |

Also registered on the launcher (`:8768`) via lazy import as `/triage/queue`,
`/triage/run`, `/triage/dispatch` — exactly like social-publish and Apollo.

## CLI

```bash
python cli.py queue                  # show the current ranked queue
python cli.py run                    # run one triage pass
python cli.py dispatch <item_id>     # dispatch a specific queued item
python cli.py history --limit 20     # audit recent dispatch decisions
```

## Files

```
diracatron.py          brain: kinds, priority, routing, sources, dispatcher, ranking
service.py             DiracatronService: queue() / run_pass() / dispatch()
main.py                FastAPI service on :8784 (the three /triage/* routes)
store.py               sqlite: triage_queue (idempotent) + dispatch_history
state_client.py        eva-state ledger emitter (Protocol; stub for tests)
cli.py                 CLI mirror of the three routes
test_diracatron.py     offline test suite (stub sources + dispatcher + ledger)
```

## Relations

- **Reads** eva-state (`:8769`) + logger context API (`:8765`) + optional signals.
- **Dispatches** to ghl-agent, pathfinder, deal-scout, monetizing-agent,
  social-publish, content-engine.
- **Writes** every decision back to eva-state via `state_client` (self-learning moat).
- **Alerts** via `modules/social-publish/slack_client.py` (imported, not
  duplicated; token from `SLACK_BOT_TOKEN`, absence non-fatal).

## Design constraints (match the repo)

- **Stdlib only** for transport (`urllib`, `sqlite3`, `json`, `hashlib`) + FastAPI.
  No new heavy deps — mirrors social-publish / agent-builder.
- **Never hardcode secrets.** `SLACK_BOT_TOKEN` and URLs come from the
  environment, like sibling modules.
- **Offline/mock only for tests.** With `EVA_DIRACATRON_OFFLINE=1` all sources,
  dispatch, and ledger writes use stubs — nothing real (GHL/Slack/LinkedIn) is
  fired. That is the sandbox default.
- **Fail safe.** A dead ledger / down agent / missing Slack token degrades to an
  honest `ok=False`, never a raised exception or a faked success.

## Status

`active` (scaffold) — offline-safe brain + queue + dispatch history, wired into
the launcher and the agent catalog. Live source/agent endpoints are best-effort
and confirmed against the catalog port map; refine per downstream agent as the
handoff to Eva-as-console proceeds.
