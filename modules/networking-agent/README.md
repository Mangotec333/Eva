# EVA Networking-Agent — Relationship Capital + Community Scout

FastAPI service on **port 8793** (sibling lobe to Brand Builder `:8792`). It
converts authority into relationship capital at both the individual and the
community level, over **one store** and **one approval loop**.

Two integrated layers, two entity types:

- **Layer A — Relationship Capital (contacts).** Manage individual relationships
  through a stage model (`unknown → engaged → active → partner`) with a
  next-best-action at each stage and a tactic playbook.
- **Layer B — Community Scout (groups).** Discover groups/communities where a
  venture's audience congregates, score them, and feed them into the same
  engagement loop as contacts (`candidate → qualified → engaged → active →
  partner`).

A weekly **KAIZEN** loop re-weights a 10-signal outcome taxonomy from what is
actually converting.

Covers three ventures — **eva_growth_agency** (online-biz acquisition ICP),
**storeys** (RCFE/senior-living real estate), **shopify** (e-commerce/dropshipping)
— with per-venture ICP/offer/brand-voice pulled from `directives.py`.

Runs **fully offline**: stdlib `sqlite3` for storage, a stub eva-state emitter,
and no live network/scraping calls anywhere. Live platform providers are stubs
until per-platform integrations are explicitly wired later.

## Architecture

| File | Responsibility |
|------|----------------|
| `directives.py` | Per-venture ICP / offer / brand voice. Reads a venture blueprint md when present (like Brand Builder), else a built-in default. |
| `discovery.py` | `Provider` Protocol per platform. Working offline `ManualSeedProvider` (JSON/CSV/markdown); `LinkedInGroupsProvider`, `RedditProvider`, `DiscordProvider`, `FacebookGroupsProvider`, `ForumProvider` are stubs (`NotImplementedError`) until live wiring. |
| `scoring.py` | Deterministic, confidence-banded 0–1 group score from member_count, activity, topical fit, and access difficulty. Documented weights. |
| `store.py` | Stdlib `sqlite3` persistence: `groups`, `contacts`, `drafts`, append-only `outcomes` ledger (immutable via triggers), and `kaizen_weights`. Idempotent migration. |
| `autonomy.py` | The `AUTO_ALLOWED` whitelist `{join_public_group, monitor_keyword_mention}` + `assert_auto_allowed` guard. |
| `playbook.py` | Stage models + next-best-action + tactic library (shared by both layers). |
| `service.py` | `NetworkingAgentService` — seed, plan, discover, score, draft→approve→send/post, auto_action (whitelist-enforced), log_outcome, kaizen_reweight. Offline-safe, honest failures. |
| `state_client.py` | eva-state ledger emitter (stub offline / http live). Mirrors `brand-builder/state_client.py`. |
| `main.py` | FastAPI REST service (port 8793). |
| `cli.py` | Terminal-first CLI. |
| `test_networking_agent.py` | Offline, network-free unit + integration tests. |

Uses the standard-library `sqlite3` module (like `modules/outreach` and
`modules/deal-analyzer-agent`), so the service runs with no external database or
network.

## Scoring

```
score = 0.40*topical_fit + 0.30*activity + 0.20*member_norm + 0.10*access_ease
```

- `member_norm` — log-scaled member count vs. a 50k saturation point (capped).
- `activity`, `topical_fit` — expected in [0, 1], clamped.
- `access_ease` — public=1.0, private=0.7, paid=0.5, invite_only=0.4.
- `confidence` (high/med/low) reflects how much real signal fed the score.

A candidate scoring ≥ 0.5 is auto-advanced to `qualified`.

## How to run

### REST API

```bash
cd modules/networking-agent
./setup.sh                       # pip install + launch on :8793
# or directly:
python main.py --port 8793
```

- Docs:   http://localhost:8793/docs
- Status: http://localhost:8793/status

Key endpoints: `GET /status`, `GET /directives/{venture}`,
`POST /plan/{venture}`, `POST /groups/discover`, `GET /groups`,
`GET /groups/{id}`, `POST /groups/{id}/score`, `POST /groups/{id}/draft`,
`POST /groups/{id}/approve`, `POST /groups/{id}/send`,
`POST /groups/{id}/auto-action`, `POST /groups/{id}/log-outcome`,
`GET /contacts`, `POST /kaizen/reweight`, `GET /docs`.

### CLI (terminal-first)

```bash
python cli.py seed
python cli.py directives --venture storeys
python cli.py plan --venture eva_growth_agency

python cli.py groups discover --venture eva_growth_agency --seed seed/seed_eva_growth_agency.json
python cli.py groups list --venture eva_growth_agency
python cli.py groups score <group_id>

python cli.py draft <group_id> --content "A helpful, non-pitchy comment." --action comment
python cli.py groups approve <draft_id>
python cli.py groups send <draft_id>

python cli.py auto join_public_group <group_id>     # whitelisted → runs now
python cli.py auto post <group_id>                  # rejected → must be drafted
python cli.py log-outcome <group_id> --outcome reply --signal reply_received

python cli.py kaizen reweight
```

**Seed format** — JSON (`{"groups": [...]}`), CSV, or a markdown table. Columns:
`name`, `platform`, `url`, `member_count`, `activity_score`, `topical_fit_score`,
`access_type`, `notes`.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVA_NETWORKING_DB` | `modules/networking-agent/eva-networking.db` | SQLite database path. |
| `EVA_NETWORKING_OFFLINE` | unset | `1` → stub eva-state emitter (no network). |
| `EVA_NETWORKING_DIRECTIVES_DIR` | unset | Directory of `<venture>.md` blueprint overrides. |
| `EVA_STATE_URL` | `http://localhost:8769` | eva-state ledger URL (live mode). |
| `EVA_NETWORKING_PORT` | `8793` | Port for `setup.sh`. |
| `EVA_NETWORKING_HOST` | `0.0.0.0` | Host for `setup.sh`. |

## Guardrails

- **All outbound content is draft-and-approve only.** Posts, comments, DMs, and
  connection-request notes MUST go through `draft() → approve() → send()/post()`.
  This is enforced in `service.py`, not left to convention: `auto_action`
  rejects (`code: not_auto_allowed`) any action outside the whitelist and records
  the rejection on the append-only outcomes ledger.
- **Only two actions run autonomously:** `join_public_group` and
  `monitor_keyword_mention`. They carry no reputational/compliance risk (no
  content reaches a person) but are still logged to the outcomes ledger.
- **No live automated activity.** Every platform-specific discovery provider is a
  stub in this pass. This respects each platform's ToS on automated activity
  (LinkedIn/Reddit/Discord/Facebook) until live, ToS-compliant, per-platform
  integrations are explicitly configured later.
- **Append-only audit trail.** The `outcomes` ledger is immutable (SQLite
  triggers block UPDATE/DELETE), so every action and outcome is auditable — same
  pattern as `modules/outreach`'s compliance ledger.

## Tests

```bash
cd modules/networking-agent
python test_networking_agent.py     # standalone runner (no pytest needed)
# or, if pytest is installed:
pytest test_networking_agent.py
```

Covers scoring math, store CRUD + migration idempotency + ledger immutability,
the autonomy whitelist enforcement (including the mandatory rejection of a
non-whitelisted action via the auto path), the draft→approve→send state machine,
directive resolution across all three ventures, and KAIZEN reweighting. No test
touches the network.
