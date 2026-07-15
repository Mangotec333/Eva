# EVA Treasurer — the finance / spend tracker

> Treasurer tracks all Eva operational spend (API/LLM credits, subscriptions, marketplace fees, ad spend, deal costs) vs budget so Vineet always knows burn rate. Tight, lean, stdlib-only — no bank integrations yet.

---

## Role

Eva incurs cost across many surfaces — Anthropic/OpenAI credits, SaaS
subscriptions (GHL, Vercel, Slack, Apollo…), marketplace/broker fees (Empire
Flippers, Flippa), ad spend, per-deal diligence costs, and hosting/domains —
but nothing added them up against a budget. Treasurer is that ledger: agents
(or the CLI/HTTP surfaces) **log** each spend, and Treasurer aggregates it by
category and period, compares it to per-category caps, alerts on threshold
breach, and projects the monthly burn rate.

Spend is *reported to* Treasurer — there are **no bank/card integrations**. It
is deliberately lean and stdlib-only (`sqlite3`, `urllib`, `csv`, FastAPI).

## Categories

`llm_api` (Anthropic/OpenAI) · `subscriptions` (GHL/Vercel/Slack/Apollo/…) ·
`marketplace_fees` (Empire Flippers/Flippa) · `ad_spend` · `deal_costs` ·
`hosting_domains` · `other`

Incoming labels are normalised (e.g. `Anthropic` → `llm_api`, `GHL` →
`subscriptions`, `Empire Flippers` → `marketplace_fees`); anything unknown
falls to `other`.

## The flow

```
track ──▶ aggregate (by category + period) ──▶ budget check ──▶ alert ──▶ learn
```

1. **track** — log `{category, amount_cents, vendor, source_agent, timestamp,
   note}`. Idempotent: a stable `signature` (or an explicit `event_key`) dedups
   retries / cron re-runs so spend is never double-counted (cron-safe, like the
   social-publish / diracatron stores).
2. **aggregate** — sum by category for a period (`day` / `week` / `month`).
3. **budget** — compare actual vs per-category cap; usage bands are
   `ok` / `warn` (≥80%) / `over` (≥100%) / `uncapped`.
4. **alert** — when a spend *newly crosses* the 80% or 100% line, fire a
   best-effort Slack alert. The Slack client is **reused** from
   `modules/social-publish/slack_client.py` (imported, never duplicated); with
   no `SLACK_BOT_TOKEN` it returns an honest `ok=False` and touches no network.
5. **learn** — every spend, breach, and a daily summary is logged back to
   eva-state (`:8769`) via `state_client`, so burn-rate lives on the backbone.

## Routes (`:8786`)

| Route | Purpose |
|-------|---------|
| `GET  /health` | health + category list + offline flag |
| `POST /finance/track` | log a spend event |
| `GET  /finance/summary?period=month` | spend by category (day/week/month) |
| `GET  /finance/budget` | caps vs actual, per-category usage status |
| `POST /finance/budget` | set / update a category cap |
| `GET  /finance/export` | CSV dump of all spend events |
| `GET  /finance/burn` | current-month run-rate projection vs budget |

Also registered on the launcher (`:8768`) via lazy import as the same
`/finance/*` routes — exactly like social-publish and Apollo.

### Track payload

```json
POST /finance/track
{"category": "anthropic", "amount_cents": 1299, "vendor": "Anthropic",
 "source_agent": "diracatron", "note": "opus tokens", "event_key": "optional"}
```

### Set a budget cap

```json
POST /finance/budget
{"category": "ad_spend", "cap_cents": 500000, "period": "month"}
```

## CLI

```bash
python cli.py track --category llm_api --amount-cents 1299 --vendor anthropic
python cli.py summary --period month
python cli.py budget
python cli.py set-budget --category ad_spend --cap-cents 500000
python cli.py export
python cli.py burn
python cli.py daily-summary        # log today's spend summary to eva-state
```

## Relations

- **Writes** every spend / breach / daily summary back to **eva-state** `:8769`
  via `state_client` (`SOURCE_SURFACE = "treasurer"`).
- **Reuses** `modules/social-publish/slack_client.py` for budget-threshold
  alerts (imported, not duplicated).
- **Registered** in the launcher `SERVICES` dict (`treasurer`, `:8786`) and via
  lazy `/finance/*` routes.
- **Logged to by** any Eva agent that incurs spend (e.g. diracatron, deal
  agents, content/ad surfaces) via HTTP/CLI.

## Config (env)

| Var | Meaning |
|-----|---------|
| `EVA_TREASURER_OFFLINE=1` | use the stub state client; fire no Slack/ledger network (sandbox default) |
| `TREASURER_DB` | override the sqlite path (defaults beside this module, gitignored) |
| `EVA_STATE_URL` | eva-state base URL (default `http://localhost:8769`) |
| `SLACK_BOT_TOKEN` | read by the reused social-publish client; absent ⇒ alerts no-op |

No secrets are hardcoded — tokens are read from env, like the sibling modules.

## Tests

```bash
python modules/finance-tracker/test_finance_tracker.py
```

Offline-only: the state client is a stub and `SLACK_BOT_TOKEN` is cleared, so
nothing real (Slack / eva-state) is ever fired. All green.

## Status

active (scaffold; offline-safe stubs by default; no bank integrations yet)
