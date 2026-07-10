# EVA Postcards

A content module that stores Vineet's quote-cards, renders each into a
LinkedIn-style image card (**Adam Grant style** — soft-pink background, rounded
corners, profile header, two-paragraph reframe), queues them on a publish
schedule, and auto-posts to LinkedIn through a wired transport.

- **Approval-gated** — cards are authored as `draft`; a human `approve`s a card
  before the scheduler will release it. A bad card can never go live
  automatically (consistent with Eva's collaborative-autonomy model).
- **Transport behind an interface** — `StubPublisher` (renders + logs, no
  network) and `LinkedInPublisher` that shells out to `linkedin_post.py`, the
  single network chokepoint. Until wired on the Eva host, LinkedIn publish
  returns `ok=False` with a clear error; it never silently fakes a post.
- **Scheduler** — `tick()` posts the next due `approved` card and advances
  `next_due` by `cadence_days` (default 3). First post is scheduled for
  **2026-07-22**. Idempotent and safe to drive from an external cron.
- **Append-only publish ledger** — every render, approve, post, and failure is
  recorded (DB triggers block UPDATE/DELETE), exportable as CSV/JSON.

No network call is made in v1: publishing goes through the `StubPublisher`, and
rendering uses Pillow + the system DejaVu fonts, so the module runs fully
offline.

## Architecture

| File | Responsibility |
|------|----------------|
| `models.py` | Pydantic request models + domain constants (statuses, transitions, defaults). |
| `database.py` | Stdlib `sqlite3` persistence (`Store`). Schema, indexes, and the append-only ledger triggers. |
| `renderer.py` | Ports `render_cards.py`: 1200x1200 Adam Grant-style PNG (soft pink, "VR" avatar, verified badge, two paragraphs). |
| `publisher.py` | `Publisher` protocol, `StubPublisher` (v1 default), `LinkedInPublisher` (shells to `linkedin_post.py`), `build_publisher()` factory. |
| `linkedin_post.py` | The single network chokepoint. `_post_via_linkedin_api` is the one function to wire on the Eva host. |
| `service.py` | `PostcardsService` — seed, render, approval gate, and the scheduler `tick`. All rules live here so API and CLI behave identically. |
| `main.py` | FastAPI REST service (port 8778). |
| `cli.py` | Terminal-first CLI. |
| `test_postcards.py` | Offline unit + integration tests. |

Uses the standard library `sqlite3` module (like `outreach` and
`deal-analyzer-agent`), so the service runs fully offline with no external
database.

## How to run

### REST API

```bash
cd modules/postcards
./setup.sh                      # pip install + launch on :8778
# or directly:
python main.py --port 8778
```

- Docs:   http://localhost:8778/docs
- Health: http://localhost:8778/health

### CLI (terminal-first)

```bash
python cli.py seed                                   # load the 8 authored quotes
python cli.py list --status draft
python cli.py approve <id>                            # approve for scheduling
python cli.py render <id>                             # (re)render the PNG
python cli.py schedule --cadence-days 3 --start 2026-07-22
python cli.py tick                                    # post next due (safe for cron)
python cli.py ledger --export csv
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVA_POSTCARDS_DB` | `modules/postcards/eva-postcards.db` | SQLite database path. |
| `EVA_POSTCARDS_IMAGE_DIR` | `modules/postcards/data/postcards` | Where rendered PNGs are written. |
| `EVA_POSTCARDS_PUBLISHER` | `stub` | Publisher: `stub` (log only) or `linkedin` (chokepoint). |
| `EVA_POSTCARDS_PORT` | `8778` | Port for `setup.sh`. |
| `EVA_POSTCARDS_HOST` | `0.0.0.0` | Host for `setup.sh`. |
| `LINKEDIN_ACCESS_TOKEN` | — | LinkedIn OAuth token (`w_member_social` scope), read by `linkedin_post.py`. |

## Publisher + chokepoint

The publish workflow is fully decoupled from the transport. To wire real
publishing later, implement the one function in `linkedin_post.py`:

```python
def _post_via_linkedin_api(text, image_path, access_token) -> dict: ...
```

`linkedin_post.py` speaks a JSON stdin/stdout contract (same spirit as
outreach's `gmail_send.py`):

```
stdin  {"text": "...", "image_path": "...", "access_token_env": "LINKEDIN_ACCESS_TOKEN"}
stdout {"ok": true|false, "provider": "linkedin", "post_url": "...", "error": "..."}
```

On the Eva host, implement `_post_via_linkedin_api` using LinkedIn's Images
upload + UGC Posts API with an OAuth token carrying the `w_member_social`
scope. `LinkedInPublisher` and the `service.py` scheduler never change.

## Scheduling

`tick()` releases at most one card per call: the next `approved` card that is
due, provided the schedule clock has reached `next_due` (default `start_date`,
`2026-07-22`). It then advances `next_due` by `cadence_days`. Because it is a
pure step function with no daemon, the platform `schedule_cron` can call
`eva postcards tick` starting 2026-07-22 and every 3 days after; repeated or
early calls are safe no-ops.

## Tests

```bash
cd modules/postcards
python test_postcards.py     # standalone runner (no pytest needed)
# or, if pytest is installed:
pytest test_postcards.py
```

Covers all cases from spec section 9: seed idempotency, render produces a
nonzero PNG, `tick` no-op when nothing due, `tick` posts + advances `next_due`,
`tick` skips drafts, ledger append-only, LinkedIn chokepoint fails loudly until
wired, plus the seed→approve→tick and tick-before-start integrations.
