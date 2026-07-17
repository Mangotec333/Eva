# EVA Health Monitor

Cross-module **watchdog**. Most EVA modules expose a `/health` endpoint but
nothing watched them. This module polls them on a `tick`, records up/down +
latency to its own SQLite, and **raises an alert when a module stays down for N
consecutive ticks**.

Built to the Eva **Architecture Directive** (`modules/README.md`): own FastAPI
app + port, own SQLite with a `memory` table and an append-only `ledger`
(immutability trigger), own CLI/tests, and every network call behind a
`HealthClient` Protocol with an offline `Stub` — so the whole module is testable
with zero outbound calls.

**Stack:** FastAPI + stdlib `sqlite3` + stdlib `urllib` (no HTTP dependency).
Port **8788**.

## What it does

On each `tick()`:
1. probes every monitored module's `/health` URL (short timeout, via the
   `HealthClient` chokepoint),
2. writes a `health_checks` row (status `up`/`down`, latency, http_code, error)
   and a `checked` ledger event,
3. if a module has `>= failure_threshold` (default **3**) consecutive `down`
   checks and has no open alert, opens an alert (`alerts` row + `alert_opened`
   ledger event + `_deliver_alert`),
4. when a down module recovers, its open alert is resolved (`alert_resolved`).

### Alerting is a one-line swap

`_deliver_alert` in `service.py` only **logs** in v1. To wire Slack / GHL / email
later, pass an `alert_sink` callable to `HealthMonitorService(...)` (or set
`service.alert_sink`); it is invoked with the alert dict. No other code changes.

## Quick start

```bash
cd modules/health-monitor
bash setup.sh                       # pip install, serve :8788

# offline dry-run (stub probe, no sockets):
EVA_HEALTH_CLIENT=stub python cli.py tick
python cli.py status
python -m pytest                    # offline test suite (zero outbound calls)
```

Live use just runs `python cli.py tick` (or `POST /tick`) on a cron; the default
`urllib` client probes the real localhost `/health` endpoints.

## Endpoints (port 8788)

| Method | Path        | Purpose                                        |
|--------|-------------|------------------------------------------------|
| GET    | `/health`   | this monitor's own health + last-run summary   |
| POST   | `/tick`     | probe all modules, record, raise/resolve alerts|
| GET    | `/status`   | latest status per monitored module             |
| GET    | `/modules`  | the monitored-module config list               |
| GET    | `/checks`   | recent raw check rows (`?module=&limit=`)       |
| GET    | `/alerts`   | alerts (`?status=open\|resolved`)               |
| GET    | `/ledger`   | append-only event ledger                        |

## Configuration

- **Monitored modules** — default list lives in `config.py`, derived from the
  authoritative service registry in `modules/launcher/eva_launcher.py` plus the
  standalone modules that expose `/health`. Override without code changes by
  setting `EVA_HEALTH_MONITOR_CONFIG` to a JSON file:
  ```json
  [{"name": "postcards", "url": "http://localhost:8778/health"}]
  ```
- **Alert threshold** — `EVA_HEALTH_FAILURE_THRESHOLD` (default `3`).
- **Probe timeout** — `EVA_HEALTH_TIMEOUT` seconds (default `3`).
- **Probe client** — `EVA_HEALTH_CLIENT=stub|real` (default `real`; tests force `stub`).

## Default monitored modules

context-api (8765), deal-scout (8766), content-engine (8767), outreach (8768),
eva-state (8769), channels (8770), knowledge (8771), monetizing-agent (8772),
pathfinder (8773), voice (8774), postcards (8778), projects (8779),
linkedin-analytics (8780), ghl-agent (8782), media-editor (8783),
triage-brain (8784), finance-tracker (8786), social-scheduler (8787),
deployer (8789), local-exec (8790), ip-scout (8791), brand-builder (8792).

## Key files

- `service.py` — core logic: `tick`, alert raise/resolve, memory, mission/goals
- `http_client.py` — probe chokepoint (`StubHealthClient` / `RealHealthClient`)
- `config.py` — monitored-module registry + thresholds
- `database.py` — SQLite: `health_checks`, `alerts`, `memory`, append-only `ledger`
- `main.py` — FastAPI on :8788
- `cli.py` — terminal-first CLI
- `test_health_monitor.py` — offline test suite (stub probe only)

## Status — v1

v1. Per the module release checklist in `modules/README.md`, run it manually
(CLI / cron) through the standard testing window before granting it autonomy, and
wire `_deliver_alert` to a real channel when ready.

See also `docs/BACKUP_DR.md` for the companion backup/DR proposal for EVA's
SQLite-per-module data.
