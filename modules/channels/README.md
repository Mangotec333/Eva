# EVA Channels — multi-platform publish (Reddit + Substack)

One Eva module that owns multi-platform **publishing transports** behind a
single common `Publisher` Protocol. v1 ships two platforms — **Reddit** and
**Substack** — each with its own subprocess *chokepoint* script that is the only
place real network code lives. This is the home for platform adapters so content
modules (postcards, content-engine) can publish to any channel *by composition*
rather than each shipping its own transport.

Follows the Eva agent-microservice directive: own FastAPI app on its own port
(`:8781`), own SQLite, own CLI, own tests, own `requirements.txt`, `setup.sh`,
and `README.md`.

> **Note:** this module supersedes the earlier `channels_*` connector prototype
> that lives in the same directory. The new module is the sanctioned
> Publisher-Protocol service (`main.py`, `service.py`, `publisher.py`, …).

## Key guarantees

- **Approval gate (publishing is irreversible).** Status flows
  `draft → approved → posted | failed`. `publish` **rejects** drafts; only
  `approved` items are released. Nothing auto-publishes.
- **Idempotent.** Re-publishing an already-`posted` item is a no-op that returns
  the existing `post_url` — never a double-post.
- **Stubs never fake success.** An unwired transport returns `ok=False` with a
  clear error. Tests inject a fake-success stub to exercise the posted path.
- **Append-only ledger.** Every create / approve / publish / fail is recorded in
  `channels_ledger`, protected by `BEFORE UPDATE`/`BEFORE DELETE` triggers.
- **Offline-runnable.** Stdlib `sqlite3` only; all tests run without a network.
- **Agent intelligence layer.** A `memory` key/value table (read on start,
  written on decision/learning) plus graceful reads of `docs/MISSION.md` and
  `docs/CURRENT_GOALS.md` (absent files are a no-op, never a crash).

## Publisher Protocol

```python
@dataclass
class PublishResult:
    ok: bool
    provider: str
    post_url: str = ""
    error: str = ""
    needs_manual_publish: bool = False

class Publisher(Protocol):
    name: str
    def publish(self, item: dict) -> PublishResult: ...
```

The shape is a **superset of postcards'** `PublishResult(ok, provider, post_url,
error)` — postcards could adopt these adapters by composition without breaking.
The service holds a `{platform: Publisher}` registry and dispatches by
`item["platform"]`.

Implementations:
- `StubPublisher(platform, fake_success=False)` — offline. Default mode returns
  `ok=False` ("not wired"); `fake_success=True` returns `ok=True` + synthetic
  URL for tests.
- `RedditPublisher` — shells out to `reddit_post.py`.
- `SubstackPublisher` — shells out to `substack_post.py`.

## Quick start

```bash
cd modules/channels
bash setup.sh                     # installs deps, serves on :8781
# or drive from the terminal:
python cli.py create --platform reddit --title "Launch" --body "We are live" --subreddit r/Entrepreneur
python cli.py list
python cli.py approve <id>
python cli.py publish <id>        # gated: only approved items post
python cli.py tick                # publish next approved-due (safe from cron)
```

## REST API (`:8781`)

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/` | Iconized HTML dashboard (items table) |
| GET  | `/health` | Agent status + last-run summary |
| POST | `/items` | Create a draft item |
| GET  | `/items` | List items (`?status=`, `?platform=`) |
| GET  | `/items/{id}` | Get an item |
| PATCH| `/items/{id}` | Update (approve, set payload/scheduled) |
| POST | `/items/{id}/publish` | Publish (gated on `status=approved`) |
| GET/PATCH | `/config/{platform}` | Per-platform config |
| GET/PATCH | `/schedule` | Cadence / next_due |
| POST | `/tick` | Publish next approved-due item, advance next_due |
| GET  | `/ledger`, `/ledger/export?format=csv\|json` | Change ledger |

## UI

`GET /` serves a dependency-free, dark-theme HTML table of items — **no CDN, no
JS framework**. Every glyph is an inline `<svg>` drawn with `currentColor` from a
single `<defs>` sprite: platform icons (Reddit antenna-head, Substack stacked
layers), status badges (draft = pencil, approved = check, posted =
arrow-up-right, failed = warning), and action buttons (publish = send, approve =
check, edit = pencil). Built iconized from day one so a later shared sprite
system drops in cleanly.

## Host wiring

### Reddit (real posting)

1. Create a **script-type** app at <https://www.reddit.com/prefs/apps>.
2. Export the credential env vars on the Eva host:
   ```bash
   export REDDIT_CLIENT_ID=...      REDDIT_CLIENT_SECRET=...
   export REDDIT_USERNAME=...       REDDIT_PASSWORD=...
   ```
3. Implement `reddit_post.py::_post_via_reddit_api`: OAuth **password grant**
   against `https://www.reddit.com/api/v1/access_token`, then
   `POST https://oauth.reddit.com/api/submit` with `sr`, `kind=self`, `title`,
   `text` (required scope: `submit`). Return the permalink as `post_url`.
   (PRAW is a convenient option — see the optional dep in `requirements.txt`.)
4. Configure + publish:
   ```bash
   python cli.py config set reddit --subreddit r/Entrepreneur --client-id-env REDDIT_CLIENT_ID
   python cli.py approve <id> && python cli.py publish <id>
   ```

Until wired, Reddit publishes return `ok=False, error="Reddit credentials not
set"` — the item goes to `failed` and the attempt is recorded in the ledger.

### Substack (no public posting API)

Substack has **no reliable public posting API**, so v1 is honest: every publish
**always** exports a ready-to-publish markdown draft to
`data/channels/substack/<id>.md` and returns
`ok=False, needs_manual_publish=True` with a clear message. Open the exported
markdown and paste it into the Substack editor to publish.

**v2 (future):** browser automation. Capture a `SUBSTACK_SESSION_COOKIE`, drive
the Substack editor (Playwright/Selenium) to create and publish a draft, and
have `substack_post.py` return the live `post_url`. Deliberately out of scope for
v1 — we never fake `ok=true`.

## Chokepoint contracts

`reddit_post.py` — stdin JSON `{title, body, subreddit, kind, client_id_env,
client_secret_env, username_env, password_env, user_agent}` →
stdout `{ok, provider:"reddit", post_url, error}`.

`substack_post.py` — stdin JSON `{id, title, body, publication_url, session_env}`
→ stdout `{ok:false, provider:"substack", post_url:"", needs_manual_publish:true,
error}` (always exports the markdown draft first).

## Tests

```bash
python test_channels.py     # standalone runner (or: pytest test_channels.py)
```

Fully offline: schema + append-only ledger, stub not-wired vs. fake-success
paths, approval gate, publish rejects drafts, posted path, idempotent re-publish,
`tick` behaviour, Substack always `needs_manual_publish`, Reddit "credentials not
set", memory read/write, and graceful mission/goals no-op.

## Data model

`channel_items` · `channel_platform_config` · `channel_schedule` ·
`channels_ledger` (append-only) · `memory`. Status enum:
`draft | approved | posted | failed`.
