# EVA Social-Scheduler — native daily LinkedIn + X publisher

> The autonomous daily publisher for the eva-acquisition pipeline. 5 posts/day on
> a fixed America/New_York schedule, each gated through the existing
> **social-publish** Slack approve-per-post flow, then **LIKE + CTA
> comment/reply**, with **all** content, post history, and engagement analytics
> in **Eva's own local sqlite** — no Postiz, no SaaS DB. Eva owns the data.

---

## Role

Eva runs the top-of-funnel for eva-acquisition by posting to LinkedIn + X every
day. This module is the scheduler + publisher that ties together the pieces Eva
already has, without duplicating any of them:

- **Queue** — a rolling content queue in local sqlite (`store.py`), day-1
  pre-seeded and future days drafted by `content-engine`.
- **Gate** — the existing `modules/social-publish` approve-then-publish Slack
  gate (imported behind a seam). Nothing publishes without an explicit approve.
- **CTA** — after publish, LIKE the post + comment/reply the CTA using the
  existing `modules/channels` LinkedIn/X connectors.
- **Analytics** — a unified local engagement store; X metrics via the X API v2,
  LinkedIn metrics reused from `modules/linkedin-analytics`.
- **Ledger** — every published post + sync is logged to `eva-state` (`:8769`).

## The schedule (America/New_York — ET)

5 posts/day at **08:00, 11:00, 14:00, 15:00, 17:00 ET**. All slot math uses
`zoneinfo("America/New_York")`, so it is correct regardless of the Mac's own
timezone (the Mac is `America/Los_Angeles`). Analytics sync runs hourly during
**8am–6pm ET**.

## Self-fire loop (no cron needed)

When the service starts (the launcher SERVICES entry runs `main.py`), it spins up
**one daemon thread** (`loop.py`) that computes the next ET slot, sleeps until it,
then fires a single `run()` pass (submit due → publish approved → LIKE + CTA).
Then it computes the next slot and repeats — forever. No launchd timer or cron
required.

- **Resilient** — every tick is wrapped in try/except at two levels. A failing
  `run()` (network, gate, ledger, anything) is caught, logged, emitted to
  `eva-state` as `loop_fire_failed`, and the loop keeps going. It never crashes
  the service.
- **Idempotent** — a double-fire is safe: the store dedupes queued headlines by
  `headline_hash` and the gate approves per post, so re-firing a slot cannot
  double-post.
- **Observable** — each fire logs `loop_fired` to `eva-state` (slot, #submitted,
  #published). `GET /health` reports `loop_running` + `next_slot_et`.
- **Offline-safe** — with `EVA_SOCIAL_SCHEDULER_OFFLINE=1` (sandbox default) the
  loop **no-ops**: `start()` does not spawn a thread and `fire()` fires nothing
  real. Set `EVA_SOCIAL_SCHEDULER_NO_LOOP=1` to disable autostart even when live
  (e.g. to drive `run()` purely via the HTTP/CLI surface).

## Per-post flow

1. At/after a slot's ET time, the next queued post is submitted to the
   social-publish Slack gate (a ping goes to the founder DM per post).
2. On approval (✅ reaction or `approve` reply — or the launcher endpoint), the
   gate publishes to **LinkedIn + X**.
3. Immediately after publish, Eva **LIKEs** the post and posts the CTA:
   `DM or comment "Eva-acquisition" to try it for free`
   (LinkedIn: a comment on the own UGC post. X: a reply to the own tweet.)
4. The published post + platform IDs (LinkedIn UGC urn, X tweet id, comment/reply
   ids) are logged to the local store and to `eva-state`.

## Data — Eva owns it (local sqlite only)

One sqlite file, three tables (`store.py`):

- `content_queue` — the rolling queue. `headline_hash` is UNIQUE, so a headline
  is **never** queued/posted twice (30-day rolling window; `queue.prune`).
- `post_history` — one row per published post with all platform IDs.
- `analytics` — the unified engagement store: `platform, post_id, impressions,
  likes, comments, clicks, retrieved_at` snapshots over time.

DB path defaults beside the module; override with `SOCIAL_SCHEDULER_DB` to point
at the Eva data directory. Gitignored (`*.db`). **No third-party data store.**

## HTTP surface (port 8787)

| Method | Route | Purpose |
|---|---|---|
| GET  | `/health`         | health + slots + offline flag |
| GET  | `/schedule`       | content queue grouped by status + ET slots |
| POST | `/schedule/seed`  | pre-seed the day-1 content queue (deduped) |
| POST | `/schedule/run`   | one pass: submit due → publish approved → prune |
| POST | `/schedule/sync`  | sync engagement metrics into the local store |
| GET  | `/analytics`      | latest engagement snapshot per post + totals |

Also registered on the **launcher** (`:8768`) via lazy import: `GET /schedule`,
`POST /schedule/seed`, `POST /schedule/run`, `POST /schedule/sync`,
`GET /analytics`, plus the `social_scheduler` entry in the launcher `SERVICES`
dict.

## CLI

```bash
python cli.py seed                 # pre-seed day-1 content queue
python cli.py schedule             # show queue + fixed ET slots
python cli.py run                  # one pass (submit due → publish approved)
python cli.py sync --window-days 30
python cli.py analytics            # latest per-post snapshot + totals
```

## Credentials — config file is PRIMARY, env is FALLBACK (never hardcoded)

Credentials resolve through `modules/social-publish/credentials.build_cfg()`,
which reads `~/.eva/channels_config.json` as the **primary** source (the same
file the channels connectors use) and falls back to env vars **only** when a
field is missing from the file. Per field: config file → env → legacy `TWITTER_*`
env. **Nothing is hardcoded.**

Live secrets live **only** in the local `~/.eva/channels_config.json`, which is
gitignored (`.eva/`, `**/channels_config.json`) so it can never be committed. The
in-repo `channels_config.template.json` ships with **empty** placeholders — no
real token. (This closes the previously-committed LinkedIn token: it has been
removed from both the template and `channels_api.py`'s default config.)

If you prefer env vars over the config file, set them in `~/.zshrc`: 

**LinkedIn** (UGC post + like + comment):

```bash
export LINKEDIN_ACCESS_TOKEN="…"     # w_member_social scope
export LINKEDIN_PERSON_URN="…"       # e.g. urn:li:person:XXXX (or the raw id)
```

**X / Twitter** — OAuth 1.0a **user context** for posting/replying/liking
(4 values), plus an app **Bearer token** for reading metrics:

```bash
export X_API_KEY="…"                 # consumer key
export X_API_SECRET="…"              # consumer secret
export X_ACCESS_TOKEN="…"            # user access token
export X_ACCESS_SECRET="…"           # user access token secret
export X_BEARER_TOKEN="…"            # app bearer token (metrics read only)
```

Legacy `TWITTER_API_KEY` / `TWITTER_API_SECRET` / `TWITTER_ACCESS_TOKEN` /
`TWITTER_ACCESS_SECRET` names are also accepted for the OAuth 1.0a set.

Card images are resolved against `EVA_SOCIAL_CARD_DIR` (a queue item stores just
the card basename):

```bash
export EVA_SOCIAL_CARD_DIR="$HOME/Eva/assets/cards"
```

> **launchd note:** launchd services do **not** source `~/.zshrc`. For the
> scheduled service, put these env vars in the plist `EnvironmentVariables`
> (or start it from an interactive shell).

## Offline / tests

`test_social_scheduler.py` is a stdlib-only, fully offline suite. The gate,
engagement, analytics, and state-ledger seams are all injected with fakes/stubs,
so the tests **never** post / like / comment to real platforms and touch no
network. With `EVA_SOCIAL_SCHEDULER_OFFLINE=1` (the sandbox default) the service
uses no-op seams too.

```bash
python test_social_scheduler.py     # 23 passed, 0 failed
```

## Reuse (imported, not duplicated)

- `modules/social-publish/gate.py` + `slack_client.py` — the approve-per-post gate.
- `modules/channels/linkedin_connector.py` + `twitter_connector.py` — transports.
  This module added `linkedin_connector.like_post` / `comment_on_post` and
  `twitter_connector.reply_tweet` / `like_tweet` / `get_tweet_metrics`.
- `modules/linkedin-analytics` — LinkedIn per-post metrics.
- `modules/content-engine` — drafts future-day queue items.
- `state_client.py` follows the `modules/triage-brain` / `finance-tracker` pattern.
