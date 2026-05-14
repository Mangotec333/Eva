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
| `POST` | `/deals/fetch/flippa/{listing_id}` | Fetch + persist a Flippa listing |
| `POST` | `/deals/fetch/ef/{listing_id}` | Fetch + persist an Empire Flippers listing |

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
