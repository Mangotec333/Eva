# EVA Agent Builder — the meta-agent that builds agents

Directive: the goal is to switch to EVA as the primary operating console. Every one-off Eva/PC performs that is repeatable gets captured here as an agent + SOP — so EVA learns the process and can do it autonomously next time.

---

A coding-capable meta-agent that keeps Eva's agent roster growing and current.
It does three things:

1. **Inventory** — scans `modules/` on disk and reports every agent's
   entrypoint, port, launchd trigger, README, and status. Can refresh the
   auto-inventory table in `EVA_AGENT_CATALOG.md` so the roster never drifts.
2. **Scaffold** — stands up a brand-new agent/module following the canonical
   Eva pattern (`store.py` + `<module>.py` core + `gate.py` + `cli.py` +
   README + optional launchd plist), so a missing capability is filled in
   minutes.
3. **Capture** — turns a one-off workflow Eva/PC just did (explainer-video
   build, Apollo outreach, content cards, …) into a **repeatable SOP** + a
   Markdown runbook, persisted so EVA can rerun it autonomously.

```
agent_builder.py          core: catalog() / scaffold() / capture()
store.py                  sqlite persistence for scaffolds + captured SOPs
cli.py                    operator entrypoint
launchd/                  optional com.eva.agent-builder.plist (created on scaffold --launchd)
```

## Design constraints (match the repo)

- **Stdlib only.** `os`, `json`, `re`, `sqlite3`, `pathlib`, `urllib`. No pip.
- **Never hardcode secrets.** Slack notification is best-effort and reuses
  `modules/social-publish/slack_client.py` (token from `SLACK_BOT_TOKEN`);
  its absence is non-fatal.
- **Fail safe.** Missing optional deps or Slack token degrade, never raise.
- **Mirrors existing agents.** The scaffolded skeleton is a direct analogue of
  `modules/social-publish` (connector + store + gate + cli) and the Apollo
  pipeline in `modules/channels`.

## CLI

```bash
# inventory every agent (and refresh the catalog markdown)
python cli.py catalog --write

# scaffold a new agent
python cli.py scaffold --name "Invoice Agent" --purpose "Chase unpaid invoices" --port 8790 --launchd

# capture a one-off workflow as a repeatable SOP
python cli.py capture --name "Explainer video build" \
  --step "Draft script from deal thesis" \
  --step "Record VO" \
  --step "Auto-edit via media-editor /edit" \
  --step "Submit to social-publish gate for approval" \
  --trigger manual --input "deal id" --module media-editor

# audit what the builder has done
python cli.py scaffolds
python cli.py sops
```

## Launcher routes (`:8768`)

Delegated in `modules/launcher/eva_launcher.py`, imported lazily so a missing
dep never breaks the launcher's core service routes:

| Route | Purpose |
|-------|---------|
| `GET  /agent-builder/catalog` | inventory every agent (`?write=1` refreshes the catalog md) |
| `POST /agent-builder/scaffold` | scaffold a new agent/module |
| `POST /agent-builder/capture` | capture a one-off workflow as a repeatable SOP |

Request bodies:

```jsonc
// POST /agent-builder/scaffold
{ "name": "Invoice Agent", "purpose": "...", "port": 8790, "with_launchd": false, "notify": false }

// POST /agent-builder/capture
{ "name": "Explainer video build", "steps": ["...", "..."],
  "trigger": "manual", "summary": "...", "inputs": ["deal id"], "module": "media-editor", "notify": false }
```

## What a scaffold produces

Running `scaffold` creates `modules/<slug>/` with working, importable stubs:

- `store.py` — one `records` table, restart-safe, `*.db` gitignored.
- `<module>.py` — `creds_status()` (env-only) + `run()` (TODO body).
- `gate.py` — `submit_for_approval()` + `approve()`, Slack-aware.
- `cli.py` — `creds / run / submit / approve / list`.
- `README_<module>.md` — including the launcher-wiring table.
- optional `launchd/com.eva.<slug>.plist`.

The builder records every scaffold and SOP in `agent_builder.db` (gitignored)
so there's an audit trail of everything EVA has learned to do.
