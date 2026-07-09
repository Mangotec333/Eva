# EVA Monetizing Agent

The weekly **revenue-leak detector**. Runs every Sunday, mines all connected
activity streams, finds under-monetized assets/signals, ranks them by cash
proximity, and converts the top opportunities into next-week actions — packaged
and gated behind a very brief pithy Sunday brief.

Governed successor to the **Yaksha** cron prototype
(`modules/angels/angel3_monetization/`, now DEPRECATED). Same intent, but a full
autonomous-agent microservice: FastAPI service + `/health`, own SQLite `memory.db`,
own CLI, Stub + real transports behind Protocols, an approval gate on every
irreversible action, an append-only ledger with an immutability trigger, offline
tests, and a swap-and-play reasoning brain (replaces Yaksha's direct OpenAI call).

**Stack:** FastAPI + stdlib `sqlite3` (offline-first). Port **8772**.

## The pattern

`Mine → Match → Package → Route → Follow-up`

- **Mine** signals from GHL, Drive/Docs, GitHub, Slack, gcal, finance, waitlist,
  and the agent's own memory (sources behind a `SignalSource` Protocol; a
  deterministic Stub is used offline).
- **Match** each signal to one of nine plays: Reactivate, Upsell, Outreach,
  Productize, Revive, Referral, Content-to-offer, Retainer, White-label.
- **Package** into a concrete artifact (drafted SMS/email, pipeline move, proposal
  doc, contact list, landing tweak, or human-only task).
- **Route** into the ledger + (after approval) the execution transport.
- **Follow-up**: next week checks whether plays converted and recalibrates.

## Scoring model (0–100 composite)

Cash Proximity 35 · Effort 20 · Strategic Fit 20 · Reusability 15 · Urgency 10.
The deterministic scorer (`playbook.py`) is authoritative and free; the brain only
sharpens packaging copy.

## Key files

- `main.py` — FastAPI REST API on :8772
- `service.py` — approval gate + execution transport (Stub + subprocess chokepoint)
- `scan.py` — the weekly scan orchestrator + Sunday-brief renderer
- `playbook.py` — the 9-play playbook + 5-dimension scoring model (deterministic)
- `mining.py` — signal sources (`StubSignalSource`, `RepoSignalSource`)
- `brain.py` — `MonetizationBrain` Protocol + Stub + LLM (swap-and-play)
- `memory.py` — SQLite schema, intelligence memory, append-only ledger + trigger
- `directive.md` — live directive (learnings auto-synced by `directive_sync.py`)
- `cli.py` — terminal-first scan/brief/approve/execute workflow
- `test_monetizing_agent.py` — offline test suite (Stub transports)

## Quick start

```bash
cd modules/monetizing-agent
bash setup.sh                       # installs deps, starts API on :8772
# or run the scan from the terminal:
EVA_MONETIZE_OFFLINE=1 python cli.py scan
python -m pytest                    # offline test suite
```

## API endpoints

- `GET  /health` — status + last-run summary + latest brief
- `GET  /directive` — the current live directive
- `POST /scan` — run the weekly revenue-leak scan; returns the pending-approval brief
- `GET  /brief/latest` — most recent Sunday brief (+ its plays)
- `GET  /brief/{id}` — a specific brief
- `POST /brief/{id}/approve` — **approval gate**: flip the brief's plays to approved
- `POST /brief/{id}/execute` — execute approved plays (refuses unapproved; Stub offline)

## CLI

```bash
python cli.py scan                        # run scan, print the Sunday brief
python cli.py brief                        # show latest brief
python cli.py plays --brief <id>           # list ledger plays
python cli.py approve <brief_id>           # approval gate
python cli.py execute <brief_id>           # execute approved plays
python cli.py outcome <play_id> <type> converted --lesson "SMS > email"
```

## Autonomy model

**v0 (now):** full-auto packaging, gated by the brief. Sunday: mine → score →
package → brief (`pending-approval`). Vineet approves → approved plays execute via
the transport. Human-only actions are routed as Slack tasks.

## Autostart

`launchd/com.eva.monetizing.plist` runs the scan every **Sunday 14:00 UTC**
(7:00 AM PT). Registered in `modules/autostart/eva-install-services.sh` and
`eva-start.sh`.
