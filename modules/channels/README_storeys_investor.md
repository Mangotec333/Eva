# Storeys investor-outreach sourcing pipeline

Sources US-based RE investors / family offices / HNW allocators from Apollo,
dedups them, gets founder approval in Slack, then files approved contacts
into GHL's **Storeys Investor Outreach** pipeline (`New Lead` stage).

**Separate from Eva Acquisition** — different ICP, different pipeline,
different ledger, different tables. Per standing instruction, this pipeline
never reads or writes `apollo_gate.py` / `apollo_store.py` /
`enrolled_contacts.py` or touches the Eva Acquisition GHL pipeline
(`hODxp7jDIraP6FaNZqNU`). `apollo_connector.py` (Apollo search itself) is
reused unmodified — only the search parameters differ per call.

```
apollo_connector.py          Apollo People search (SHARED, unmodified)
storeys_investor_ledger.py   dedup ledger (sqlite; Storeys-only)
storeys_investor_store.py    batch persistence (sqlite; survives restarts)
storeys_investor_gate.py     extract → dedup → Slack approve → GHL file-into-pipeline
test_storeys_investor.py     offline test suite (7/7)
```

## Data flow

1. **Extract** — `apollo_connector.extract_contacts()` runs Apollo People
   search with the Storeys ICP overrides below (not Eva Acquisition's
   PE/M&A defaults), paginates, caps the first batch at **100**.
2. **Dedup (layer 1)** — each email is checked against
   `storeys_investor_ledger` (sqlite). Already-enrolled emails are dropped.
3. **Approve** — the deduped batch (count + 10 sample rows) is posted to the
   founder Slack DM. Nothing files into GHL until a ✅ reaction / `approve`
   reply, or a `POST /storeys/apollo/enroll/{batch_id}`.
4. **Enroll** — each contact is upserted through `ghl_client` into location
   `kyK4yAY6Hur3F4deCx2n` with tags `storeys-investor-lead` +
   `source:apollo-re-investor`. **Dedup (layer 2)** is GHL's own
   upsert-by-email. The contact is then filed as an opportunity in the
   **Storeys Investor Outreach** pipeline's **New Lead** stage (pipeline/
   stage resolved by name via `list_pipelines()` — no hardcoded IDs). No
   workflow-trigger tag: Storeys has no dedicated nurture workflow yet
   (unlike Eva Acquisition's `8024cff0`).
5. Success/skip/fail counts are reported back to the Slack thread, and every
   success is written to `storeys_investor_ledger`.

## Search parameters (Storeys ICP)

Set by `storeys_investor_gate.DEFAULT_*` (override per call) — these are
**Storeys-specific overrides passed into the shared `apollo_connector`**, not
edits to `apollo_connector.py` itself:

| Param | Default |
|-------|---------|
| `person_titles` | Managing Partner, General Partner, Managing Director, Principal, Family Office Principal, Chief Investment Officer, Investment Director, Portfolio Manager, Wealth Advisor, Private Investor |
| firm keywords (`q_organization_keyword_tags`) | Family Office, Real Estate Private Equity, Real Estate Investment, Private Wealth Management, RIA |
| `person_locations` | United States |
| `per_page` / batch cap | 100 (Apollo hard max) |

Auth: shared `APOLLO_API_KEY` (same credential as Eva Acquisition sourcing).

## Launcher routes (`:8768`)

| Route | Purpose |
|-------|---------|
| `GET  /storeys/apollo/creds` | credential status (no secrets) |
| `POST /storeys/apollo/extract` | extract + dedup + stage to Slack |
| `GET  /storeys/apollo/batch/{id}` | inspect a staged batch |
| `POST /storeys/apollo/enroll/{batch_id}` | explicit approval → file into GHL pipeline |
| `POST /storeys/apollo/reject/{batch_id}` | reject a staged batch |
| `POST /storeys/apollo/check-approvals` | poll Slack and file approved batches |

Also registered on the `launcher` lobe in `agent_registry.json`
(`storeys_extract`, `storeys_enroll`, `storeys_batch`) for Diracatron dispatch.

## Running this through Perplexity Computer ("PC")

Apollo's connector inside Perplexity Computer requires an explicit,
non-bypassable human confirmation before every credit-consuming search/
enrich call — that guardrail is enforced by PC itself and this repo does not
(and should not) try to route around it. The intended split of
responsibility:

- **PC** runs the actual Apollo search/enrich call each time (1 credit per
  search call; 1 credit per contact matched on enrich), with the founder
  confirming cost up front each run.
- **This repo** holds the ICP definition, the dedup ledger, the Slack
  approve gate, and the GHL pipeline-filing logic — so once PC has a batch
  of sourced/enriched leads, filing them into Storeys Investor Outreach is
  one call to `POST /storeys/apollo/extract` (or a direct
  `storeys_investor_gate.extract_and_stage(..., _search_fn=...)` call using
  the PC-sourced rows as the mock search function) followed by the existing
  Slack-approve → `/storeys/apollo/enroll/{batch_id}` flow.

A weekly PC cron can drive this end-to-end, but each run still needs the
founder to tap through Apollo's confirmation once per run — it is
semi-autonomous, not fully unattended, by design.

## Compliance notes

- **US B2B/accredited-investor targeting only.** Search is scoped to
  `United States` and to investment decision-makers, not consumers.
- **Apollo credits.** Email addresses are only revealed when explicitly
  requested, and each reveal consumes an Apollo credit. Un-revealed
  (`email_not_unlocked@...`) rows are filtered out before staging.
- **Consent.** Filing a contact into the Storeys Investor Outreach pipeline
  only happens after founder approval in the Slack gate — never automatic.
