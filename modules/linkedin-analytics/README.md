# EVA LinkedIn Analytics

Reads LinkedIn **post analytics** (impressions, clicks, reactions, comments,
shares, engagement rate) for an author (person or organization), stores
normalized snapshots + raw payloads in its own SQLite, and exposes them via REST
+ CLI. Sync is **idempotent** and safe to drive from a cron.

This is an autonomous-agent microservice per Eva's architecture directive: own
FastAPI app on its own port (`:8780`), own SQLite, own CLI, own tests, own
`requirements.txt` / `setup.sh` / `README.md`. Reading analytics is read-only
and non-irreversible, so **sync has no human approval gate** (unlike the
postcards publish flow) — but every sync is still recorded in an append-only
ledger.

The real LinkedIn API call lives behind a single subprocess **chokepoint**
(`linkedin_analytics.py`). Until OAuth is wired on the Eva host, sync returns
`ok=False` with a clear error and **never fakes data**.

## Quick start

```bash
cd modules/linkedin-analytics
bash setup.sh                     # installs deps + starts the service on :8780
# open http://localhost:8780/     # HTML dashboard (posts + latest metrics)
```

Run the offline test suite:

```bash
python test_linkedin_analytics.py     # standalone runner (prints PASS/FAIL)
# or: python -m pytest test_linkedin_analytics.py
```

## Architecture

| File | Responsibility |
|------|----------------|
| `models.py` | Pydantic request models + domain constants |
| `database.py` | stdlib `sqlite3` store; schema, upserts, append-only ledger triggers, memory table |
| `client.py` | `AnalyticsClient` Protocol + `StubAnalyticsClient` (offline) + `LinkedInAnalyticsClient` (shells out to the chokepoint) |
| `linkedin_analytics.py` | **the single network chokepoint** — `_fetch_via_linkedin_api` (host implements) |
| `service.py` | all enforced rules: `sync`, `tick`, engagement-rate computation, memory, mission/goals reads |
| `main.py` | FastAPI service on `:8780` + dependency-free HTML dashboard |
| `cli.py` | terminal-first CLI (`eva linkedin-analytics <cmd>`) |
| `test_linkedin_analytics.py` | offline test suite (Stub / fake-success clients only) |

### Data model (SQLite)

- `linkedin_posts(post_urn PK, share_urn, author_urn, posted_at, text, post_url, first_seen_at, updated_at)`
- `linkedin_analytics(id PK, post_urn FK, snapshot_ts, window_start, window_end, impressions, unique_impressions, clicks, reactions, comments, shares, engagement_rate, raw_json, source, UNIQUE(post_urn, window_start, window_end, source))`
- `linkedin_sync_config(key PK, value)` — `author_urn`, `access_token_env`, `last_sync_at`, `sync_window_days`, `next_due`
- `analytics_ledger(id PK, ts, event_type, entity_type, entity_id, actor, details_json)` — append-only (BEFORE UPDATE/DELETE triggers reject mutations)
- `memory(key PK, value, ts, source)` — the agent's long-term context

`engagement_rate` is always computed canonically as
`(reactions + comments + shares) / impressions` (guarded against divide-by-zero),
regardless of what the transport reports.

## REST API (`:8780`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | HTML dashboard (posts + latest metrics) |
| `GET` | `/health` | Agent status + last-run summary (`provider`, `last_sync_at`, `post_count`, `snapshot_count`) |
| `POST` | `/sync` | Trigger `service.sync()` |
| `POST` | `/tick` | Sync if due (cron-safe, idempotent) |
| `GET` | `/posts` | List posts with latest snapshot joined |
| `GET` | `/posts/{post_urn}` | Post + all its snapshots |
| `GET` | `/snapshots?post_urn=` | Time-series for a post |
| `GET` | `/summary?days=28` | Totals + top post by impressions |
| `GET` / `PATCH` | `/config` | Get / update `author_urn`, `sync_window_days`, `access_token_env` |
| `GET` | `/ledger` | Query the analytics ledger |
| `GET` | `/ledger/export?format=csv\|json` | Export the ledger |
| `GET` / `POST` | `/memory` | List / write agent memory |
| `GET` | `/alignment` | Mission + current-goals presence |

## CLI

```bash
python cli.py sync                                          # pull latest (cron-safe)
python cli.py posts
python cli.py snapshots urn:li:ugcPost:123
python cli.py summary --days 28
python cli.py config set --author-urn urn:li:organization:XXX --window-days 28
python cli.py config get
python cli.py ledger --export csv
python cli.py tick                                          # sync if due
python cli.py memory list
```

## Agent intelligence layer

Per the PR #16 directive, this module includes the intelligence boundary:

- **Memory** — a `memory(key, value, ts, source)` table read at task start and
  written on a decision/learning. Distinct from the event ledger: memory records
  *what the agent knows*, the ledger records *what it did*.
- **Mission** — reads `docs/MISSION.md` at startup as a read-only alignment
  artifact (graceful no-op if absent; never crashes).
- **Current goals** — reads `docs/CURRENT_GOALS.md` at startup to pick up the
  time-varying priority stack (graceful no-op if absent).
- **`/health`** exposes agent status + last-run summary so the command center
  can observe the agent.

Paths can be overridden with `EVA_MISSION_PATH` / `EVA_CURRENT_GOALS_PATH`.

## Host wiring (LinkedIn OAuth is out of scope for this module)

Everything above runs offline. To read **real** analytics, the Eva host wires
OAuth and implements the one chokepoint function. LinkedIn OAuth itself is out of
scope for this module — only the chokepoint + interface are provided here.

1. **Create a LinkedIn app** at <https://www.linkedin.com/developers/apps>.
   Associate it with the Company Page you want statistics for and request the
   **Community Management API** / **Marketing Developer Platform** product.
2. **Redirect URL** — add an OAuth 2.0 authorized redirect URL for your host,
   e.g. `https://<your-eva-host>/oauth/linkedin/callback`.
3. **Required scopes** (organization post statistics):
   - `r_organization_social` — read the organization's posts/shares
   - `r_organization_statistics` — read post/share statistics
   (For personal-profile analytics, use the person-post statistics endpoints and
   the corresponding member scopes as your app is approved for them.)
4. **Access token** — complete the OAuth flow, then export the token on the host:
   ```bash
   export LINKEDIN_ACCESS_TOKEN="<oauth-access-token>"
   ```
   The env var name is configurable via `config set --access-token-env`.
5. **Implement the chokepoint** — fill in
   `linkedin_analytics.py::_fetch_via_linkedin_api`. It is the **only** place a
   real network call is made. Suggested endpoints:
   - List the author's UGC posts:
     `GET https://api.linkedin.com/v2/ugcPosts?q=authors&authors=List({author_urn})`
   - Per-post lifetime statistics (organization shares):
     `GET https://api.linkedin.com/rest/organizationalEntityShareStatistics?q=shares&shares=List(urn:li:share:...)`
   - Aggregate reactions/comments:
     `GET https://api.linkedin.com/v2/socialActions/{share_urn}`

   Return the normalized `posts[]` shape documented at the top of
   `linkedin_analytics.py`. `engagement_rate` may be left null — the service
   computes it canonically.
6. **Select the real client** and run a sync on the host:
   ```bash
   export EVA_LINKEDIN_ANALYTICS_CLIENT=linkedin
   python cli.py config set --author-urn urn:li:organization:XXXXXX
   eva linkedin-analytics sync        # or: python cli.py sync
   ```

If the token is missing/expired the chokepoint returns
`ok=False, error="LinkedIn access token not set in $LINKEDIN_ACCESS_TOKEN"`,
and no analytics are read.

## Chokepoint contract

`linkedin_analytics.py` reads a JSON request on **stdin** and writes a JSON
result on **stdout**:

```jsonc
// stdin
{"author_urn": "urn:li:organization:123", "access_token_env": "LINKEDIN_ACCESS_TOKEN", "window_days": 28}

// stdout
{"ok": true, "provider": "linkedin",
 "posts": [{"post_urn": "...", "share_urn": "...", "posted_at": "...", "text": "...",
            "post_url": "...", "impressions": 0, "unique_impressions": 0, "clicks": 0,
            "reactions": 0, "comments": 0, "shares": 0, "engagement_rate": null, "raw": {}}],
 "error": ""}
```

## Two-phase release

Per the directive, the module ships, then gets a 2-week manual test window before
autonomous operation. After that, the platform schedules
`eva linkedin-analytics tick` daily to keep snapshots fresh — `tick` is
idempotent and safe to call repeatedly.
