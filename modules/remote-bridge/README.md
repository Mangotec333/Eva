# EVA Remote-Bridge — the ONE authenticated front door

**Port:** 8795 (`REMOTE_BRIDGE_PORT`) · **Bind:** `0.0.0.0` (intentionally exposable) · **Stack:** FastAPI + stdlib sqlite3

Remote-Bridge is the single authenticated entry point that lets the founder
(Vineet) send Eva a natural-language instruction from **anywhere** — phone,
Slack, Perplexity Computer — over a cloudflared tunnel. It gives the founder an
instant receipt, then forwards the goal to Diracatron's registry-scoped dispatch
brain and tracks the outcome.

This closes Eva's "no remote instruction channel / no delivery guarantee / no
auth" gap. It is the deliberate opposite of `local-exec` (which is loopback-only
and must never be tunneled): Remote-Bridge *is* meant to be tunnel-exposed, so
authentication is mandatory on every request.

## Flow

```
founder → POST /remote/instruct  →  persist "received" + audit  →  instant {instruction_id}
                                          │ (background)
                                          ▼
                                 Diracatron /triage/dispatch (registry-scoped)
                                          │
                                    complete | failed  →  status + append-only ledger
```

1. `POST /remote/instruct {"goal", "context"?}` — persists the instruction as
   `received`, audits it, and returns `{instruction_id, status}` **immediately**
   (never blocks on the downstream dispatch).
2. In the background it marks `dispatched`, forwards the goal to Diracatron, and
   records `complete` / `failed`.
3. The founder polls `GET /remote/instruct/{id}` for status, or
   `.../{id}/ledger` for the full audit trail.

## Endpoints

| Method | Route | Auth | Purpose |
| ------ | ----- | ---- | ------- |
| GET  | `/health`                       | none  | Health + `api_key_configured` (boolean only) + offline flag |
| POST | `/remote/instruct`              | bearer | Submit a goal → `{instruction_id, status}` |
| GET  | `/remote/instruct`              | bearer | Recent instructions, newest first (capped) |
| GET  | `/remote/instruct/{id}`         | bearer | Status of one instruction (404 if unknown) |
| GET  | `/remote/instruct/{id}/ledger`  | bearer | Append-only audit trail for one instruction |

## Why this is safe

1. **Mandatory bearer auth.** Every `/remote/*` route requires
   `Authorization: Bearer <token>`, checked against env `REMOTE_BRIDGE_API_KEY`.
   `/health` is the only unauthenticated route, and it exposes only a *boolean*
   for whether the key is configured — never the key itself.
2. **Fails closed.** If `REMOTE_BRIDGE_API_KEY` is unset at startup, every
   `/remote/*` route returns `503 not configured` — it never degrades to
   allow-all. The condition is logged loudly on boot.
3. **Rate limited.** A fixed-window in-memory limiter caps each API key at 30
   requests/minute; excess returns `429`.
4. **No raw execution — ever.** The bridge runs nothing itself. It only forwards
   a *goal* to Diracatron's `/triage/dispatch`, which is already registry-scoped:
   Diracatron can invoke only agents Eva has explicitly registered — never raw
   shell, never `local-exec` directly. That indirection is the safety boundary.
5. **Fully audited.** Every instruction and every security event
   (`unauthorized`, `rate_limited`) is written to an append-only
   `instruction_ledger` (immutability enforced by SQLite triggers) and mirrored
   to the governed Eva State Ledger. An audit-write failure never blocks or
   fails the founder's response.
6. **This is the only intentionally tunnel-exposed module.** Expose it with:

   ```bash
   cloudflared tunnel --url http://localhost:8795
   ```

   Set `REMOTE_BRIDGE_API_KEY` **before** exposing it. Keep the key only in
   `~/.eva/*.json`, your `~/.zshrc`, or the launchd plist `EnvironmentVariables`
   — **never commit it**.

## Run

```bash
# install + launch (fails closed with a loud warning if the key is unset)
REMOTE_BRIDGE_API_KEY='<a-strong-secret>' ./setup.sh

# offline / sandbox posture — stub dispatch + stub state, no network
EVA_REMOTE_BRIDGE_OFFLINE=1 python main.py
```

## CLI

```bash
python cli.py instruct "review the acquisition pipeline and flag stalls"
python cli.py instruct "post the nightly digest" --context '{"channel":"ops"}'
python cli.py status  <instruction_id>
python cli.py list    --limit 20
python cli.py ledger  <instruction_id>
```

## Tests

Fully offline — Diracatron and the State Ledger are stubbed, every run uses a
throwaway temp sqlite, and nothing real is contacted.

```bash
python test_remote_bridge.py          # standalone (bundled pytest shim)
python -m pytest test_remote_bridge.py # under real pytest
```

## Config

| Env var | Default | Purpose |
| ------- | ------- | ------- |
| `REMOTE_BRIDGE_API_KEY`     | *(unset → fails closed)* | Bearer token for all `/remote/*` routes |
| `REMOTE_BRIDGE_PORT`        | `8795`                   | Listen port |
| `REMOTE_BRIDGE_HOST`        | `0.0.0.0`                | Bind host |
| `REMOTE_BRIDGE_DB`          | `remote_bridge.db` (beside the module) | SQLite path (gitignored) |
| `EVA_DIRACATRON_URL`        | `http://localhost:8784`  | Diracatron dispatch base URL |
| `EVA_STATE_URL`             | `http://localhost:8769`  | Eva State Ledger base URL |
| `EVA_REMOTE_BRIDGE_OFFLINE` | *(unset)*                | `1` → stub dispatch + state, no network |
