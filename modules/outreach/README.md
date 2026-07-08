# EVA Outreach & Investor Verification

Module 6 of the EVA system. Closes the fundraising loop with a
**compliance-safe, approval-gated** outreach layer:

- **Approval-gated send queue** — every recipient starts `pending_approval`;
  only an explicit human approval moves it to `approved`; only an `approved`
  recipient can be sent. Nothing is ever auto-sent.
- **Accredited-investor verification** — `requested → documents_received →
  verified / rejected → expired`, with a 365-day expiry and automatic
  re-lock of the sale path on lapse (SEC Rule 506(c)).
- **Global suppression / opt-out list** — immutable; suppressed contacts are
  auto-excluded from campaigns and re-checked at send time.
- **Append-only compliance ledger** — every approval, send, opt-out,
  verification change and filing reminder is recorded; exportable as CSV/JSON
  for the SEC Form D / blue-sky paper trail.

No email is transmitted in v1: approved messages are handed to a pluggable
`sender` interface with a stub/log implementation. A Gmail adapter hook is
provided for later.

## Architecture

| File | Responsibility |
|------|----------------|
| `models.py` | Pydantic request models + domain constants (statuses, transitions, TTL). |
| `database.py` | Stdlib `sqlite3` persistence (`Store`). Schema, indexes, and the append-only / immutable triggers. |
| `sender.py` | `Sender` interface, `StubSender` (v1 default, logs only), `GmailSender` hook, `build_sender()` factory. |
| `service.py` | `OutreachService` — all enforced compliance rules live here so the API and CLI behave identically. |
| `main.py` | FastAPI REST service (port 8768). |
| `cli.py` | Terminal-first CLI. |
| `test_outreach.py` | Offline unit + integration tests. |

Uses the standard library `sqlite3` module (like `deal-analyzer-agent`), so the
service runs fully offline with no external database or network calls.

## How to run

### REST API

```bash
cd modules/outreach
./setup.sh                      # pip install + launch on :8768
# or directly:
python main.py --port 8768
```

- Docs:   http://localhost:8768/docs
- Health: http://localhost:8768/health

### CLI (terminal-first)

```bash
python cli.py contacts add --email jane@fund.com --name "Jane" --relationship-type cold
python cli.py contacts list

python cli.py campaign create --file email.md --to-list contacts.csv

python cli.py pending
python cli.py approve <recipient_id> --approved-by founder
python cli.py deny <recipient_id> "not a fit"
python cli.py send <recipient_id>

python cli.py optout jane@fund.com --reason "unsubscribe reply"

python cli.py verify create <contact_id> --method third_party
python cli.py verify advance <case_id> --status documents_received
python cli.py verify advance <case_id> --status verified --verifier "CPA Jane"

python cli.py sale <contact_id> --amount 50000   # blocked until verified (cold contacts)

python cli.py ledger --export csv
```

**`email.md` format** — optional `Subject:`, `From:`, `FromEmail:`,
`FromAddress:` header lines; a blank line then the body; an optional `---`
line separates the body from a disclosures footer.

**`contacts.csv` format** — a header row with an `email` column (required) plus
optional `name`, `relationship_type` (`warm`/`cold`), and `source` columns.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVA_OUTREACH_DB` | `modules/outreach/eva-outreach.db` | SQLite database path. |
| `EVA_OUTREACH_SENDER` | `stub` | Sender implementation: `stub` (log only) or `gmail` (hook, not implemented in v1). |
| `EVA_OUTREACH_PORT` | `8768` | Port for `setup.sh`. |
| `EVA_OUTREACH_HOST` | `0.0.0.0` | Host for `setup.sh`. |

## Sender adapter interface

The send workflow is fully decoupled from transport. To wire real delivery
later, implement the `Sender` protocol in `sender.py`:

```python
class Sender(Protocol):
    name: str
    def send(self, message: OutboundMessage) -> SendResult: ...
```

`OutboundMessage` carries the recipient, subject, body, disclosures, sender
identity, and the campaign/recipient IDs. `SendResult` reports `ok`, the
`provider`, a `provider_message_id`, and an `error` string (implementations
return `ok=False` on failure rather than raising). `GmailSender` is the
stubbed hook; point `build_sender()` at it (or pass an instance to
`OutreachService`) once the connected Gmail connector is available. The
approval-gate and compliance logic in `service.py` never change.

## Compliance rules (enforced in `service.py`)

- **Send** requires: `status == approved` **AND** email not on the suppression
  list. Messaging a cold prospect is permitted (general solicitation, 506(c)).
- **Sale** (`record_sale` / `POST /sales`) is blocked for a **cold** contact
  unless a verification case is `verified` and unexpired. **Warm** contacts
  transact under 506(b). This is the "sale path" gate.
- Every send records `campaign_id`, `contact_id`, `approved_by`, `sent_at`, and
  a `disclosures_hash` (SHA-256 of the campaign disclosures text) in the ledger.
- Suppression is global and immutable (DB triggers block UPDATE/DELETE).
- Verification expires 365 days after `verified_at`; a read of a lapsed case
  flips it to `expired` and re-locks the sale path. Renewal reopens a new case.
- The compliance ledger is append-only (DB triggers block UPDATE/DELETE).

## Tests

```bash
cd modules/outreach
python test_outreach.py     # standalone runner (no pytest needed)
# or, if pytest is installed:
pytest test_outreach.py
```

Covers all cases from the spec: suppressed auto-exclusion, send blocked when
not approved / suppressed, sale blocked for unverified cold contacts, opt-out
ledgering + future-send block, verification expiry, ledger immutability, plus
the happy-path, opt-out-then-resend, and verify-unblocks-sale integrations.
