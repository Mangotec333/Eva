# Apollo → GHL cold-outreach pipeline

Sources US-based acquisition buyers from Apollo, dedups them, gets founder
approval in Slack, then enrolls approved contacts into GHL's tag-triggered
7-touch sequence.

```
apollo_connector.py   Apollo People search (urllib, stdlib-only)
enrolled_contacts.py  dedup ledger (Postgres primary, sqlite fallback)
apollo_store.py       batch persistence (sqlite; survives restarts)
apollo_gate.py        extract → dedup → Slack approve → GHL enroll
```

## Data flow

1. **Extract** — `apollo_connector.extract_contacts()` runs Apollo People
   search, paginates, and caps the first batch at **100** contacts.
2. **Dedup (layer 1)** — each email is checked against `enrolled_contacts`
   (Postgres table from `infra/init/postgres/02_enrolled_contacts.sql`).
   Already-enrolled emails are dropped. This is the "don't ask again" gate.
3. **Approve** — the deduped batch (count + 10 sample rows) is posted to the
   founder Slack DM `D0ARUK4JEDA`. Nothing enrolls until a ✅ reaction /
   `approve` reply (via the existing Slack poller) **or** a
   `POST /apollo/enroll/{batch_id}`.
4. **Enroll** — each contact is upserted through `ghl_client` into location
   `kyK4yAY6Hur3F4deCx2n` with tags `eva-acquisition-lead` + `source:apollo-pe-ma`.
   **Dedup (layer 2)** is GHL's own upsert-by-email. The contact is then tagged
   `eva-acquisition`, which fires GHL workflow `8024cff0` (the 7-touch).
5. Success/skip/fail counts are reported back to the Slack thread, and every
   success is written to `enrolled_contacts`.

## Search parameters

Set by `apollo_connector.DEFAULT_*` (override per call):

| Param | Default |
|-------|---------|
| `person_titles` | Partner, Managing Director, Principal, Associate, VP, Vice President, Director, Deal Origination |
| firm keywords (`q_organization_keyword_tags`) | Private Equity, M&A advisory, Mergers and Acquisitions, Investment Banking, Search Fund |
| `person_locations` | United States |
| `per_page` / batch cap | 100 (Apollo hard max) |
| `contact_email_status` | verified, likely to engage |

Auth: `APOLLO_API_KEY` (Bearer token; also sent as `X-Api-Key`). Never hardcoded.

## Launcher routes (`:8768`)

| Route | Purpose |
|-------|---------|
| `GET  /apollo/creds` | credential status (no secrets) |
| `GET  /apollo/search?q=` | one-page live preview |
| `POST /apollo/extract` | extract + dedup + stage to Slack |
| `GET  /apollo/batch/{id}` | inspect a staged batch |
| `POST /apollo/enroll/{batch_id}` | explicit approval → enroll (fires 7-touch) |
| `POST /apollo/check-approvals` | poll Slack and enroll approved batches |

## Compliance notes

- **US B2B only.** Search is scoped to `United States` and to business
  decision-makers. Do not source consumers or non-US contacts through this
  pipeline.
- **CAN-SPAM.** Every GHL email in workflow `8024cff0` **must** keep a working
  unsubscribe link and Mangotec's physical mailing address in the footer.
  Removing either violates CAN-SPAM. The connector cannot enforce this (GHL
  workflow email bodies are UI/owner-edited) — it is the founder's
  responsibility on the GHL side.
- **Apollo credits.** Email addresses are only revealed when explicitly
  requested, and each reveal consumes an Apollo credit. This connector reads
  whatever Apollo returns and does **not** call any credit-consuming reveal
  endpoint automatically. Un-revealed (`email_not_unlocked@...`) rows are
  filtered out before staging.
- **Consent to the sequence.** The `eva-acquisition` trigger tag starts a real
  outbound sequence — only apply it to contacts the founder has approved in the
  Slack gate.
