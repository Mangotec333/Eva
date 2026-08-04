# EVA Deal Scout — Module 3

**FastAPI microservice for digital business acquisition deal sourcing and scoring.**

EVA Deal Scout is the third module of the EVA (Enterprise Valuation & Acquisition) intelligence system.
It ingests acquisition candidates from Flippa and Empire Flippers, scores them across five dimensions,
computes seller-finance / HELOC cash flow projections, and surfaces the strongest deals for action.

---

## Architecture

```
EVA System
├── Module 1: eva-core          — system orchestration & memory
├── Module 2: eva-intel         — market intelligence & research
└── Module 3: eva-deal-scout    ← THIS MODULE — deal sourcing & scoring
```

Data flows: `scraper → raw listing` → `analyzer → scored deal` → `SQLite DB` → `REST API`

---

## Module Structure

```
eva-deal-scout/
├── main.py                ← FastAPI app, all 11 endpoints, port 8766
├── models.py              ← Pydantic models: Deal, DealCreate, DealUpdate
├── database.py            ← aiosqlite async SQLite layer, seeding
├── deals_schema.py        ← Additive `deals` column migrations + pass-reason grouping
├── analyzer.py            ← Scoring engine + financial analysis
├── box_evaluator.py       ← Post-scoring buy-box evaluator (real_estate | digital_micro)
├── deal_box_config.json   ← real_estate box thresholds (adjustable without code changes)
├── deal_box_config_digital_micro.json  ← digital_micro box thresholds
├── acquire_ingest.py      ← Reusable Acquire.com listing ingest (gated marketplace)
├── ef_active_listings.py  ← EF active/for-sale listing discovery (public API)
├── scheduler.py           ← APScheduler wiring: automated discover→score→box cycle
├── scrapers/
│   ├── __init__.py
│   ├── flippa.py          ← Flippa public listing fetcher
│   └── empire_flippers.py ← Empire Flippers public listing fetcher
├── requirements.txt
├── setup.sh
└── README.md
```

Database file: `eva-deal-scout.db` (SQLite, created on first run)

---

## Quick Start

```bash
# 1. Install dependencies and start server
chmod +x setup.sh && ./setup.sh

# or manually:
pip install -r requirements.txt
python main.py --port 8766
```

The server starts at **http://localhost:8766**

Interactive API docs: **http://localhost:8766/docs**

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service liveness check |
| `GET` | `/deals` | List all deals (sorted by score desc) |
| `POST` | `/deals` | Manually add a deal |
| `GET` | `/deals/shortlist` | Deals with `overall_score >= 7.5` |
| `GET` | `/deals/passed` | Passed deals grouped by `pass_reason` (+ `allowed_pass_reasons`) |
| `GET` | `/deals/export` | Export all deals as JSON |
| `GET` | `/deals/{id}` | Get single deal with full analysis |
| `PUT` | `/deals/{id}` | Update deal fields (re-scores automatically) |
| `DELETE` | `/deals/{id}` | Remove a deal |
| `POST` | `/deals/{id}/analyze` | Re-run scoring engine on a deal |
| `GET` | `/deals/{id}/competitors` | List researched competitors linked to a deal |
| `POST` | `/deals/{id}/competitors` | Attach a competitor to a deal (upserts shared entity) |
| `GET` | `/deals/{id}/box?box_type=` | Buy-box verdict for a scored deal (evaluates on demand); `real_estate` (default) or `digital_micro` |
| `GET` | `/box/deals?box_type=` | List in-box deals (`box_pass=True`), best cash flow first; all profiles unless filtered |
| `POST` | `/deals/fetch/flippa/{listing_id}` | Fetch + persist a Flippa listing |
| `POST` | `/deals/fetch/ef/{listing_id}` | Fetch + persist an Empire Flippers listing |
| `GET` | `/pipeline/sources` | List source adapters + SEED sources with trust levels |
| `POST` | `/pipeline/source/{source}` | Stage 1 SOURCE: normalize + persist raw listings |
| `POST` | `/pipeline/score` | Stage 2 SCORE: run the gated v6 scorer over DB rows |
| `POST` | `/pipeline/run-now` | Trigger one full automated sourcing cycle immediately |
| `POST` | `/pipeline/backfill` | Import `deal_scout_data/*.json` + `closed_deals_dataset.json` |
| `GET` | `/pipeline/scored` | List scored deals (best first) |
| `GET` | `/pipeline/trends` | Trend stats over open vs closed comps |
| `POST` | `/pipeline/trends/report` | Build + save the markdown trend report |

---

## Unified DB-backed pipeline

A two-stage, DB-first pipeline sits alongside the legacy `deals` table
(existing JSON export compat is preserved). Everything is persisted through a
swappable **`DealStore`** abstraction (`store.py`) backed by owned local SQLite
via ordered **migrations** (`migrations.py`) — no external/3rd-party DB. A future
`MongoDealStore` can implement the same interface.

### Tables

| Table | Purpose |
|-------|---------|
| `source_runs` | One row per adapter invocation (timestamps + counts) |
| `raw_deals` | Normalized listings, deduped by `(source, listing_id/url)` |
| `deal_snapshots` | Point-in-time status/price observations |
| `scored_deals` | v6 11-param composite output for gated deals |
| `trend_reports` | Saved market-trend analyses |
| `competitors` | Normalized competitor entities, deduped by name |
| `deal_competitors` | Join: links competitors to deals + per-deal `moat_comparison` |
| `case_studies` | 4-lens deal case studies (JSON `snapshot` + `analysis`), upserted by `source_url` |
| `deal_box_evaluations` | Post-scoring buy-box verdicts (criteria breakdown + pass/fail + advisory `flags`), upserted by `(deal_id, box_type)` |

Every run/deal/snapshot/score is timestamped (`created_at`, `updated_at`,
`sourced_at`, `scored_at`).

### Two stages

1. **SOURCE** (`pipeline.source_deals`) — adapters normalize source payloads into
   `raw_deals` rows first, recording a `source_run` + `deal_snapshots`.
2. **SCORE** (`pipeline.score_pending`) — reads persisted rows back out and runs
   the v6 scorer. Transient JSON is never scored directly.

### Scoring gate (credit saver)

The scorer only runs on a deal where **`US_eligible OR trust_high`**:

* `US_eligible` = `registration_country=US` OR `primary_customer_market=US` OR
  `seller_location=US`.
* `trust_high` = high-trust source (Empire Flippers). A high-trust source
  **bypasses** the US filter. Acquire.com / Flippa / BizBuySell are medium-trust.

Non-scored open deals stay stored raw. Closed/sold comps are ingested for **all
geographies** (no US filter) and feed the trend analyzer rather than the scorer.

#### Empire Flippers closed comps (public API)

The closed-comps set was previously ~92 rows, mostly Flippa. `ingest-ef-closed`
de-biases it by pulling **SOLD** listings from Empire Flippers' public API
(`https://api.empireflippers.com/api/v1/listings/list`) into the same
closed-comps set (`raw_deals` with `is_closed=True`, `source=empire_flippers`):

```bash
python cli.py ingest-ef-closed                       # pull all EF sold pages
python cli.py ingest-ef-closed --max-pages 5         # cap the pull
python cli.py ingest-ef-closed --closed-comps-source empire_flippers
```

It pages the API until a page is empty or `total_pages` is reached, keeps only
sold listings, maps each to the closed-comp schema (`sale_price`,
`monthly_profit`, `multiple` → annual ÷12, `category`, `url`, geography), and
routes them through the normal SOURCE stage — so dedupe (by EF listing number)
holds within a run and across re-runs. Like all closed comps, EF sold rows feed
the trend analyzer and are never scored.

#### Empire Flippers ACTIVE listing discovery (public API)

`ef_active_listings.py` (`ingest_ef_active_listings`) mirrors the same
pagination/dedupe/injectable-fetch pattern as `ef_closed_comps.py` but pulls
currently-active (for-sale) listings instead of sold comps, writing them into
the normal open-deal set (`raw_deals` with `is_closed=False`) so they flow
through `score_pending` and the deal box like any other sourced listing. This
is the piece that lets Deal Scout *discover* new candidates automatically
instead of requiring a manual listing ID via `/deals/fetch/ef/{listing_id}`.

**⚠️ Unverified assumption — verify against the live API after deploy:** the
same EF API endpoint is called with **no** `sale_status`/`status` filter at
all. The working assumption (documented prominently in `ef_active_listings.py`)
is that the default/unfiltered feed returns active/for-sale listings, mirroring
how `ef_closed_comps.py` needs an explicit `status="sold"` filter to get sold
comps. This sandbox has no internet access, so that assumption has never been
checked against a real response — spot-check the live pagination totals and a
sample of returned listings' `status` fields against empireflippers.com's
marketplace after the first scheduled run in production. A safety-net filter
(`_looks_active`) already drops anything that explicitly looks sold, but it
cannot catch a feed that is silently empty or wrongly scoped.

### Automated scheduled sourcing (no manual listing ID required)

`scheduler.py` wires an APScheduler `AsyncIOScheduler` into `main.py`'s FastAPI
lifespan so the full pipeline runs on its own, on an interval — no manual
trigger needed:

1. **Discover** — `ef_active_listings.ingest_ef_active_listings` pulls
   currently-active EF listings.
2. **Score** — `pipeline.score_pending` scores every pending open raw deal.
3. **Box-evaluate** — `box_evaluator`'s `real_estate` box runs over every deal
   scored in step 2.

`run_pipeline_cycle(store, per_page=100)` returns a summary dict (`sourced`,
`scored`, `box_evaluated`, `box_passed`, plus any per-step `errors` — one
failing step never kills the rest of the cycle). The interval is controlled by
the `DEAL_SCOUT_CYCLE_HOURS` env var (default `6` hours); set
`DEAL_SCOUT_DISABLE_SCHEDULER=1` to run the API without the background job
(e.g. for tooling that only needs the HTTP surface). The running scheduler is
stored on `app.state.scheduler` and shut down cleanly on lifespan exit.

`POST /pipeline/run-now` triggers the same cycle synchronously — useful right
after a fresh deploy, without waiting for the schedule.

### Sources

All configured sources now have **live adapters** (no more seed-only tier):

* **Empire Flippers** (high trust) — bypasses the US filter.
* **Acquire.com** (medium, gated), **Flippa**, **BizBuySell** (medium).
* Newly activated: **QuietLight**, **FE International**, **WebsiteClosers**,
  **Motion Invest** (medium), **Investors Club** (medium, gated),
  **Dealslide**, **BusinessesForSale** (low).

Each adapter carries a `feed_url` and an `access` hint (`public` | `gated`).

#### Wide source run

`wide_source_run` (CLI: `wide-source`) attempts to source every activated
source into `raw_deals`:

* callers may supply ready payloads per source (ingested via the SOURCE stage);
* **gated** sources (auth/browser only, e.g. Investors Club, Acquire.com) are
  logged as a `source_runs` row with status **`seeded_not_fetchable`** + the
  blocking reason — no fetch attempted;
* **public** sources are fetched best-effort; any failure (network/HTTP, or "no
  structured parser yet") is likewise recorded as `seeded_not_fetchable` with
  the reason, so it stays queryable ("what needs a browser/parser").

Then run `score` to apply the gate (US-eligible OR high-trust) to new rows.

### Buy vs Build

Every scored deal also gets a build-feasibility assessment (persisted on
`scored_deals`, surfaced in the radar + trend report):

| Field | Meaning |
|-------|---------|
| `moat_build_years` | Years to rebuild a defensible moat from scratch — **the deal-killer for the build path** (`0.03·moat + 0.02·ai_proof`, 0–5 yrs). |
| `build_feasibility` | `high` (<1 yr), `medium` (1–2.5 yr), `low` (≥2.5 yr). |
| `build_time_estimate` | Engineering calendar estimate matching feasibility. |
| `buy_vs_build_recommendation` | `build` (<1 yr), `either` (1–2.5 yr), `buy` (≥2.5 yr). |
| `buy_vs_build_rationale` | Plain-language justification. |

### CLI

```bash
python cli.py migrate                     # apply migrations
python cli.py sources                     # list sources + trust levels
python cli.py backfill                    # import existing JSON datasets
python cli.py backfill \
    --source-dir /path/to/deal_scout_data \
    --closed-comps-file /path/to/closed_deals_dataset.json
python cli.py source --source flippa --file listings.json
python cli.py ingest-ef-closed            # pull EF SOLD comps into closed_comps (paginated)
python cli.py ingest-acquire \
    --url "https://app.acquire.com/startup/<id>/<tail>" \
    --raw-json /path/to/listing.json      # one manually-saved Acquire.com listing
python cli.py wide-source                 # source ALL activated sources; log unfetchable
python cli.py score                       # gated v6 scoring + buy-vs-build
python cli.py trends --output /home/user/workspace/deal_trend_report_2026-07-16.md
python cli.py stats                        # counts + gate audit + top-10 radar
python cli.py export                      # JSON dump (legacy-compatible)

# Competitor intelligence — compounds researched intel per deal
python cli.py add-competitor --deal-id RAW_DEAL_ID --name "CrowdStrike" \
    --description "Endpoint detection & response" --pricing "per-endpoint annual" \
    --url "https://crowdstrike.com" --source-url "https://research/notes" \
    --moat "this deal has a narrower vertical focus" --category "cybersecurity"
python cli.py list-competitors --deal-id RAW_DEAL_ID

# Case studies — compounding 4-lens deal intelligence (our USP)
python cli.py add-case-study --source-url "https://flippa.com/12345" \
    --deal-type within_box --title "Acme vertical SaaS" --deal-id RAW_DEAL_ID \
    --snapshot '{"asking":1200000,"profit":400000,"margin":0.5,"location":"US","usp":"vertical SaaS"}' \
    --analysis '{"lens1_box_fit":"profitable US SaaS, fits the box","lens2_what_selling":"recurring workflow lock-in","lens3_juggernaut_arc":"bolt on adjacent modules to 10x","lens4_build_vs_buy":"buy: 3yr moat, cheaper than build"}' \
    --pattern-tags '["vertical_saas","workflow_lockin"]' \
    --formula-insight "boring vertical + switching cost = durable cashflow"
python cli.py list-case-studies --deal-type juggernaut_study

# Deal box — post-scoring hard-criteria verdict (in-box vs out-of-box)
python cli.py eval-box --deal-id RAW_DEAL_ID                       # real_estate (default)
python cli.py eval-box --deal-id RAW_DEAL_ID --box-type digital_micro
python cli.py eval-box --deal-id RAW_DEAL_ID --config /path/to/deal_box_config.json
python cli.py list-box-deals              # in-box deals across all profiles
python cli.py list-box-deals --box-type digital_micro
```

### Acquire.com ingest (gated marketplace)

Acquire.com has no public scrape API, so a listing arrives as a **manually saved
JSON blob**. `ingest-acquire` runs that blob through the same
normalize → score → persist pipeline as every other source, tagged
`source=acquire_com`:

```bash
python cli.py ingest-acquire --url "<listing url>" --raw-json listing.json
python cli.py ingest-acquire --url "<listing url>" --raw-json listing.json --no-force-score
```

- The listing id is derived from the **URL tail** (the same identity rule every
  adapter applies), so re-ingesting the same URL updates the row in place.
- Scoring is **forced past the gate by default** — Acquire.com is a
  medium-trust, frequently non-US marketplace the automated gate would skip.
  The gate's verdict is still recorded on the scored row
  (`skip_reason="manual_score_gate_would_skip"` + the would-be `gate_reason`),
  so the audit trail stays honest. `--no-force-score` respects the gate instead.
- `acquire_ingest.ingest_listing(store, payload, ...)` is the library entry
  point and also accepts researched `competitors` and a `case_study` to attach
  in the same call. Per-listing scripts under `scripts/` hold only their
  hand-researched intel and delegate the generic work here — a new listing needs
  no new script.
- Digital-micro inputs carried in the payload (`ttm_revenue`, `ttm_profit`,
  `last_month_revenue`, `last_month_net`, `monthly_churn`, `age_months`) survive
  into `raw_json` and feed the `digital_micro` buy box.

### Deal box (post-scoring hard-criteria filter)

The **deal box** is a POST-SCORING layer: scoring still runs on every
US-eligible deal (the score gate is unchanged), and the box then tags each
**scored** deal as **in-box** (a stable-base acquisition candidate) or
**out-of-box** by testing hard criteria at the **current run-rate**.

Two buy-box profiles are available, selected with `box_type`:

| `box_type` | Funding | Criteria |
|-----------|---------|----------|
| `real_estate` (**default**) | Debt (seller note + HELOC) | free cash flow, DSCR, trend |
| `digital_micro` | Cash | price cap, payback, net margin, churn, trend |

A deal may hold **one verdict per profile** — `deal_box_evaluations` is upserted
by `(deal_id, box_type)`.

#### `real_estate` (default, unchanged)

It models the intended financing structure:

```
seller_note_pmt = amort((1 - down_pct) * asking, seller_note_rate, seller_note_months)
heloc_pmt       = down_pct * asking * heloc_rate / 12      # interest-only
total_debt      = seller_note_pmt + heloc_pmt
free_cash_flow  = monthly_net - total_debt
dscr            = monthly_net / total_debt
trend_pass      = last_month_net >= ttm_avg_net * (1 - tol)  # else False if no last-month figure
box_pass        = (free_cash_flow >= min_free_cash_flow_mo)
                  AND (dscr >= min_dscr) AND trend_pass
```

`run_rate="current"` uses `last_month_net` as the monthly net (falling back to
the TTM average when unavailable); the raw deal's `monthly_net` is the TTM
average, and an optional `last_month_net` / `ttm_avg_net` may be carried in the
source `raw_json`. `box_reason` records each sub-check's pass/fail and the
verdict persists to `deal_box_evaluations` (upserted by `(deal_id, box_type)`)
with a full `config_snapshot` so the thresholds behind a verdict stay auditable.

Criteria live in **`deal_box_config.json`** (loadable + adjustable without code
changes; a partial file is merged over the built-in defaults):

| Key | Default | Meaning |
|-----|---------|---------|
| `min_free_cash_flow_mo` | `10000` | Minimum monthly free cash flow after debt |
| `min_dscr` | `1.5` | Minimum debt-service coverage ratio |
| `trend_decline_tolerance` | `0.05` | Flat-or-growing if last month ≥ TTM avg × (1 − tol) |
| `financing.down_pct` | `0.20` | Down payment (funded by the HELOC) |
| `financing.seller_note_rate` | `0.07` | Seller-note APR |
| `financing.seller_note_months` | `60` | Seller-note amortization term |
| `financing.heloc_rate` | `0.085` | HELOC APR (interest-only) |
| `financing.run_rate` | `"current"` | `current` = last month, fallback TTM avg |

#### `digital_micro` (cash-funded micro-acquisitions)

For Acquire.com / Flippa / Empire Flippers style micro-SaaS listings bought with
cash. **No financing is modelled** — `seller_note_pmt` / `heloc_pmt` /
`total_debt` / `dscr` are all zero and `free_cash_flow` is simply the run-rate
monthly net:

```
payback_months = asking / last_month_net              # None if last month <= 0
net_margin     = last_month_net / last_month_revenue  # falls back to ttm_profit / ttm_revenue
trend_pass     = last_month_net >= ttm_avg_net * (1 - tol)
box_pass       = (asking <= max_asking_price) AND (payback_months <= max_payback_months)
                 AND (net_margin >= min_net_margin) AND (churn <= max_monthly_churn)
                 AND trend_pass
```

Criteria live in **`deal_box_config_digital_micro.json`**:

| Key | Default | Meaning |
|-----|---------|---------|
| `max_asking_price` | `150000` | Price cap for a cash purchase |
| `max_payback_months` | `18` | Months of last-month net to repay the price |
| `min_net_margin` | `0.40` | Minimum net margin |
| `max_monthly_churn` | `0.05` | Churn ceiling to pass |
| `churn_hard_fail` | `0.10` | Above the ceiling but at/below this → `high_churn_warn` flag |
| `min_age_months` | `12` | Below this → `thin_track_record` flag |
| `trend_decline_tolerance` | `0.05` | Flat-or-growing if last month ≥ TTM avg × (1 − tol) |

Inputs come from the raw deal's `raw_json` (`last_month_net`,
`last_month_revenue`, `ttm_revenue`, `ttm_profit`, `monthly_churn`,
`age_months` — falling back to `age_years * 12`). Unreported churn is not held
against a deal; a missing revenue figure or a non-positive last-month net fails
the margin / payback checks outright.

`flags` are **advisory** and recorded alongside the verdict without failing it
on their own: `thin_track_record` (younger than `min_age_months`) and
`high_churn_warn` (churn in the ceiling→hard-fail band).

#### Store / CLI / API surface

- `DealStore.evaluate_box(deal_id, config=None, box_type="real_estate")` —
  evaluate + persist (refused for an unscored deal).
- `DealStore.get_box_eval(deal_id, box_type="real_estate")` — the stored verdict.
- `DealStore.list_box_deals(box_type=None)` — in-box deals (`box_pass=True`)
  across every profile unless filtered.
- An unknown `box_type` raises `ValueError` (`400` via the API).
- CLI: `eval-box --box-type` / `list-box-deals --box-type`; API:
  `GET /deals/{id}/box?box_type=`, `GET /box/deals?box_type=`.

### Case studies (4-lens compounding intelligence)

Eva's USP is turning each studied deal into reusable **pattern + formula + moat**
intelligence. A `case_studies` row captures BOTH a **deal snapshot** and the
**4-lens analysis**, each stored as a JSON blob so the schema stays lightweight:

- `snapshot` (JSON) — deal metrics: asking, revenue, profit, margin, multiples,
  founded, customers, team, location, usp.
- `analysis` (JSON) — the 4 lenses:
  1. `lens1_box_fit` — does it fit our acquisition box?
  2. `lens2_what_selling` — what are they really selling?
  3. `lens3_juggernaut_arc` — how did/could it become a juggernaut?
  4. `lens4_build_vs_buy` — build it ourselves or buy?

Plus meta: `pattern_tags` (JSON array), `formula_insight`. `deal_type` is one of
`within_box`, `juggernaut_study`, `build_vs_buy_reference`. `deal_id` links to a
`raw_deals` row but is **nullable** for out-of-box studies (juggernauts,
build-vs-buy references studied without sourcing them).

- `DealStore.add_case_study(source_url, deal_type, title, deal_id=None,
  snapshot=None, analysis=None, pattern_tags=None, formula_insight="")` — upserts
  by `source_url` (refreshes `updated_at`, preserves `created_at`).
- `DealStore.list_case_studies(deal_type=None)` — optional filter by type.
- CLI: `add-case-study` / `list-case-studies`.

### Competitor intelligence

Researched competitor info is stored so it **compounds per deal** instead of being
lost. Competitors are normalized into a shared `competitors` entity (deduped by
lowercased name) linked to deals through the `deal_competitors` join. The same
competitor (e.g. "CrowdStrike") can link to many deals; the deal-specific
`moat_comparison` lives on the link, while competitor-level facts
(`what_they_do`, `pricing_model`, `category`) live once on the shared entity.

- `DealStore.add_competitor(deal_id, name, ...)` — upserts the entity and links
  it to the deal. Re-calling fills blank entity fields without clobbering existing
  intel, and refreshes the link's `moat_comparison`.
- `DealStore.list_competitors(deal_id)` — returns the deal's competitors, each
  carrying its link-level `moat_comparison`.
- CLI: `add-competitor` / `list-competitors`; API: `POST`/`GET
  /deals/{id}/competitors` (where `{id}` is a `raw_deals` id).

### Tests

```bash
python -m pytest tests/ -q                # 106 tests (network-free); 2 more require
                                           # fastapi/aiosqlite/apscheduler installed
                                           # (self-skip otherwise via importorskip)
```

### Create a deal — POST /deals

```json
{
  "name": "My Acquisition Target",
  "source": "manual",
  "listing_id": "123",
  "url": "https://example.com",
  "category": "SaaS",
  "monthly_net": 8000,
  "annual_multiple": 2.5,
  "asking_price": 240000,
  "age_years": 4,
  "stage": "tracking",
  "status": "active",
  "notes": "Promising recurring revenue",
  "ai_proof_score": 75,
  "value_add_score": 80
}
```

Valid `category` values: `SaaS` | `Content` | `Services` | `Education` | `Digital Products`

Valid `stage` values: `tracking` | `in_progress` | `nda_signed` | `loi_sent` |
`due_diligence` | `closed`

### Review status + pass reason

`status` is a **review verdict, orthogonal to the `stage` pipeline**: a deal is
either still under consideration (`active`, the default) or has been rejected
(`passed`). Rejecting requires a structured `pass_reason` so rejection patterns
can be aggregated over time instead of being buried in free text.

Valid `status` values: `active` | `passed`

Valid `pass_reason` values: `price_too_high` | `churn_too_high` | `thin_moat` |
`crowded_competition` | `declining_revenue` | `owner_dependent` |
`bad_unit_economics` | `outside_box` | `other`

An unknown `status` or `pass_reason` is rejected by the models with a `422`, and
setting `status="passed"` on a deal that has no `pass_reason` (neither in the
payload nor already stored) is rejected with a **`400`**.

`GET /deals/passed` returns every passed deal grouped by reason — `total`,
`reason_counts`, `groups` (most common reason first, ties alphabetical), plus
`allowed_pass_reasons`. Rows predating the field fall into an `"unspecified"`
bucket. The `status` / `pass_reason` columns are added to the legacy `deals`
table by an idempotent additive migration (`deals_schema.py`), so existing rows
land on `status='active'` with no reason.

### Update a deal — PUT /deals/{id}

Send only the fields you want to change (all fields are optional):

```json
{
  "stage": "nda_signed",
  "notes": "Spoke with seller, numbers verified",
  "value_add_score": 85
}
```

Rejecting a deal:

```bash
curl -X PUT http://localhost:8766/deals/$ID \
  -H 'Content-Type: application/json' \
  -d '{"status":"passed","pass_reason":"churn_too_high"}'
```

---

## Scoring Engine

All scores are computed by `analyzer.py → analyze_deal()`:

| Dimension | Range | Logic |
|-----------|-------|-------|
| `cashflow_score` | 0–100 | `(monthly_net / 15000) × 100`, capped at 100 |
| `moat_score` | 0–100 | Age bracket (0–5yr=40, 5–10yr=70, 10+yr=90) + category bonus |
| `ai_proof_score` | 0–100 | Category baseline (Services=85, Education=82, SaaS=75, Content=68, Digital=38) + age bonus (+5 if ≥5yr) |
| `value_add_score` | 0–100 | Manual field; defaults to 70 |
| `buy_vs_build_score` | 0–10 | `moat_score / 10` |
| `risk_score` | 0–100 | `min(age_years × 8, 90)` − 20 for Digital Products |
| `overall_score` | 0–10 | Weighted: cashflow(25%) + moat(20%) + ai_proof(25%) + value_add(15%) + risk(15%), ÷ 10 |

Category moat bonuses: Services +15, Education +10, SaaS +5, Content 0, Digital Products −10

### Financial Analysis

| Field | Formula |
|-------|---------|
| `down_payment` | 20% of `asking_price` |
| `seller_finance_amount` | 80% of `asking_price` |
| `monthly_debt_service` | PMT(7% / 12, 60 months, `seller_finance_amount`) |
| `net_monthly_cashflow` | `monthly_net` − `monthly_debt_service` |
| `heloc_used` | = `down_payment` |
| `heloc_interest_monthly` | `heloc_used` × 9.5% / 12 |
| `net_after_heloc` | `net_monthly_cashflow` − `heloc_interest_monthly` |

---

## Pre-seeded Deals

The database is seeded with 5 EVA session deals on first run:

| # | Name | Category | Monthly Net | Multiple | Status |
|---|------|----------|-------------|----------|--------|
| EF #87872 | Digital Media Services | Services | $11,478 | 1.9× | pursuing |
| Flippa #12166327 | Education Tutoring Platform | Education | $7,195 | 1.8× | pursuing |
| Flippa #12032980 | Real Estate Comparison Site | Content | $13,500 | 1.6× | tracking |
| Flippa #12278661 | WordPress Plugin SaaS | SaaS | $7,581 | 3.0× | tracking |
| EF #89115 | Digital Products Art Business | Digital Products | $11,338 | 1.9× | passed |

---

## Fetching from Marketplaces

```bash
# Fetch a Flippa listing by its numeric ID
curl -X POST http://localhost:8766/deals/fetch/flippa/12166327

# Fetch an Empire Flippers listing
curl -X POST http://localhost:8766/deals/fetch/ef/87872
```

**Note:** Flippa and Empire Flippers are JavaScript-heavy SPAs. The fetchers perform
best-effort HTML extraction and may not always capture all fields (especially
`monthly_net`, `annual_multiple`, and `age_years`). After fetching, update any
missing fields with `PUT /deals/{id}` and re-score with `POST /deals/{id}/analyze`.

Empire Flippers multiples are quoted monthly — the scraper automatically divides by 12
to normalise to annual before persisting.

---

## Example Workflow

```bash
# 1. Add a deal manually
curl -X POST http://localhost:8766/deals \
  -H "Content-Type: application/json" \
  -d '{"name":"My SaaS","category":"SaaS","monthly_net":9000,"annual_multiple":2.5,"asking_price":270000,"age_years":3}'

# 2. List all deals
curl http://localhost:8766/deals

# 3. View the shortlist
curl http://localhost:8766/deals/shortlist

# 4. Re-score a deal
curl -X POST http://localhost:8766/deals/{id}/analyze

# 5. Advance the stage after NDA
curl -X PUT http://localhost:8766/deals/{id} \
  -H "Content-Type: application/json" \
  -d '{"stage":"nda_signed"}'

# 5b. ...or reject it with a structured reason
curl -X PUT http://localhost:8766/deals/{id} \
  -H "Content-Type: application/json" \
  -d '{"status":"passed","pass_reason":"price_too_high"}'
curl http://localhost:8766/deals/passed

# 6. Export all deals
curl http://localhost:8766/deals/export > deals_export.json
```

---

## Development

```bash
# Hot-reload dev mode
python main.py --port 8766 --reload

# Custom port
python main.py --port 9000
```

---

## Dependencies

- **FastAPI** — ASGI web framework
- **uvicorn** — ASGI server
- **aiosqlite** — async SQLite driver
- **requests** — HTTP client for listing fetches
- **beautifulsoup4** — HTML parsing for scrapers
- **pydantic** — data validation

---

## EVA System Integration

Deal Scout exposes a standard JSON REST API that upstream EVA modules can consume:

- **Module 1 (eva-core)** can POST deals discovered via external research
- **Module 2 (eva-intel)** can enrich deals with market intelligence
- **Module 4+** (planned): CRM integration, outreach automation, LOI drafting

All cross-module communication uses the `/deals` REST endpoints.
The `overall_score` field provides a single ranking signal for pipeline prioritisation.

## Morning Startup

To start all EVA services with a single command, run:

```bash
~/Eva/eva-start.sh
```

This script will:
- Launch `screenpipe`, `eva_logger.py`, `eva_context_api.py`, and `deal-scout/main.py` each in their own macOS Terminal tab
- Wait 4 seconds for services to initialise
- Open the **Morning OS** and **Command Center** dashboards in your default browser
- Print a status summary with health-check URLs

Alternatively, click the **START EVA** button in the Command Center dashboard.

To stop all services:

```bash
~/Eva/eva-stop.sh
```
