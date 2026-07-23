# EVA Retro-Agent

**Port: 8795** · weekly $10K/month course-correction lobe

Every Monday 8:00 AM PT, the retro-agent reviews the prior 7 days over eva-state
and answers, deterministically, whether the week moved the revenue critical path
or just churned infrastructure. It is the weekly counterpart to
`activity-tracker-agent` (daily), with the same no-circularity discipline.

## What it does

It buckets the week into four lenses — all derived from events actually read,
never asserted:

- **(a) Shipped** — modules/catalog/commits/deploys/PRs (infra signal, not revenue).
- **(b) Revenue-pipeline movement** — did a pipeline row actually advance a stage
  (Pending→Live, deal closed, payment landed) vs. internal churn.
- **(c) Stale blockers** — Pending / needs-review / awaiting-reply > 7 days without
  movement, tracked across the full open lifetime.
- **(d) Prior priorities** — were last week's stated course-correction priorities
  worked on? Read from the "Eva — Weekly Retrospective Log" (local markdown mirror
  today; live Google Docs is an additive swap later).

…and rolls them into a goal-drift status ladder:

> **REVENUE_WIN > STALLED_BLOCKER > DRIFTING > ON_TRACK**

The digest is written to an append-only SQLite ledger AND emitted back to
eva-state so Diracatron and every other lobe see it.

## Architecture (swap-and-play)

| File | Role |
|---|---|
| `models.py` | Pydantic models + event/status vocabularies |
| `engine.py` | Pure, deterministic `build_retro()` — no I/O, no network |
| `state_client.py` | eva-state emit/read behind `StateLedgerClient` Protocol (Stub + Http) |
| `retro_log.py` | Weekly Retrospective Log source behind `RetroLogSource` Protocol (Stub + LocalFile + GoogleDocs-not-wired) |
| `memory.py` | Append-only SQLite ledger (immutability triggers) |
| `brain.py` | Optional LLM narrative sharpener behind `RetroBrain` Protocol — never changes a flag/count |
| `service.py` | `RetroService.run_retro()` — read → build → sharpen → persist → emit |
| `main.py` | FastAPI service (also `--run-once` for launchd) |

The deterministic engine is authoritative and FREE. The brain only sharpens the
narrative prose — it never changes a status, flag, or count.

## Run it

```bash
# API service
pip install -r requirements.txt
python3 main.py                 # serves on :8795

# one headless weekly retro (what launchd runs)
python3 main.py --run-once
```

## Endpoints

- `GET  /health`
- `GET  /directive`
- `POST /retro/run` — optional body `{"week_end": "YYYY-MM-DD"}`
- `GET  /retro/latest`
- `GET  /retro/history?limit=30`
- `GET  /retro/{run_id}`

## Offline / tests

Fully offline-safe: `EVA_RETRO_OFFLINE=1` stubs eva-state, the retro-log source,
and the brain — no network. Run the offline suite (no pytest dependency):

```bash
EVA_RETRO_OFFLINE=1 python3 test_retro_agent.py
```

## Environment

| Var | Purpose |
|---|---|
| `EVA_RETRO_OFFLINE=1` | force Stub transports (no network) |
| `EVA_STATE_URL` | eva-state base URL (default `http://localhost:8769`) |
| `EVA_RETRO_DB_PATH` | override the ledger path |
| `EVA_RETRO_LOG_PATH` | override the retro-log markdown mirror path |

## Schedule

`launchd/com.eva.retro-agent.plist` — Monday 15:00 UTC (8:00 AM PT),
`KeepAlive=false`, `RunAtLoad=false` (one-shot weekly cron).
