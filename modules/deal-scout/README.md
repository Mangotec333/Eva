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
├── analyzer.py            ← Scoring engine + financial analysis
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
| `GET` | `/deals/export` | Export all deals as JSON |
| `GET` | `/deals/{id}` | Get single deal with full analysis |
| `PUT` | `/deals/{id}` | Update deal fields (re-scores automatically) |
| `DELETE` | `/deals/{id}` | Remove a deal |
| `POST` | `/deals/{id}/analyze` | Re-run scoring engine on a deal |
| `GET` | `/deals/{id}/competitors` | List researched competitors linked to a deal |
| `POST` | `/deals/{id}/competitors` | Attach a competitor to a deal (upserts shared entity) |
| `GET` | `/case-studies` | List 4-lens case studies (query: `deal_type`, `pattern`) |
| `POST` | `/case-studies` | Store a 4-lens deal case study (upserts by `source_url`) |
| `POST` | `/deals/fetch/flippa/{listing_id}` | Fetch + persist a Flippa listing |
| `POST` | `/deals/fetch/ef/{listing_id}` | Fetch + persist an Empire Flippers listing |
| `GET` | `/pipeline/sources` | List source adapters + SEED sources with trust levels |
| `POST` | `/pipeline/source/{source}` | Stage 1 SOURCE: normalize + persist raw listings |
| `POST` | `/pipeline/score` | Stage 2 SCORE: run the gated v6 scorer over DB rows |
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
| `case_studies` | 4-lens deal case studies (snapshot + analysis), deduped by `source_url` |

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
python cli.py add-case-study --title "Acme vertical SaaS" \
    --source-url "https://flippa.com/12345" --deal-id RAW_DEAL_ID \
    --deal-type within_box --asking-price 1200000 --ttm-profit 400000 \
    --lens1-box-fit "profitable US SaaS, fits the box" \
    --lens2-what-selling "recurring workflow lock-in" \
    --lens3-juggernaut-arc "bolt on adjacent modules to 10x" \
    --lens4-build-vs-buy "buy: 3yr moat, cheaper than build" \
    --pattern-tags '["vertical_saas","workflow_lockin"]' \
    --formula-insight "boring vertical + switching cost = durable cashflow"
python cli.py list-case-studies --deal-type juggernaut_study --pattern payments
```

### Case studies (4-lens compounding intelligence)

Eva's USP is turning each studied deal into reusable **pattern + formula + moat**
intelligence. A `case_studies` row captures BOTH a **deal snapshot** (title,
metrics, USP) AND the **4-lens analysis**:

1. `lens1_box_fit` — does it fit our acquisition box?
2. `lens2_what_selling` — what are they really selling?
3. `lens3_juggernaut_arc` — how did/could it become a juggernaut?
4. `lens4_build_vs_buy` — build it ourselves or buy?

Plus meta: `pattern_tags` (JSON array), `formula_insight`. `deal_type` is one of
`within_box`, `juggernaut_study`, `build_vs_buy_reference`. `deal_id` links to a
`raw_deals` row but is **nullable** for out-of-box studies (juggernauts,
build-vs-buy references studied without sourcing them).

- `DealStore.add_case_study(study)` — upserts by `source_url` (blank URLs are
  always inserted, never deduped).
- `DealStore.list_case_studies(deal_type=None, pattern=None)` — filter by type
  and/or a single pattern tag.
- `DealStore.get_case_study(id)` — fetch one.
- CLI: `add-case-study` / `list-case-studies`; API: `POST`/`GET /case-studies`
  (query `deal_type`, `pattern`).

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
python -m pytest tests/ -q                # 60 tests, pure stdlib + pydantic
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
  "status": "tracking",
  "notes": "Promising recurring revenue",
  "ai_proof_score": 75,
  "value_add_score": 80
}
```

Valid `category` values: `SaaS` | `Content` | `Services` | `Education` | `Digital Products`

Valid `status` values: `tracking` | `nda_requested` | `under_review` | `passed` | `pursuing`

### Update a deal — PUT /deals/{id}

Send only the fields you want to change (all fields are optional):

```json
{
  "status": "nda_requested",
  "notes": "Spoke with seller, numbers verified",
  "value_add_score": 85
}
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

# 5. Update status after NDA
curl -X PUT http://localhost:8766/deals/{id} \
  -H "Content-Type: application/json" \
  -d '{"status":"nda_requested"}'

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
