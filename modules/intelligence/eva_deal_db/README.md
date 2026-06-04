# Eva Deal Intelligence DB
**Module 11 — Deal Memory Layer**
SQLite + FTS5 + sqlite-vec | Zero cloud cost | Fully offline

---

## What this does

Eva can now answer deal questions **instantly from local memory** — no Google Drive fetch, no web search, no LLM inference for simple lookups:

```
"What is batch.ai's current NOI?"          → $1,371/mo   (sub-1ms, SQL index)
"Show me all Tier 1 deals"                → 5 deals sorted by NOI
"Which deal has the lowest multiple?"      → Business SaaS 0% Churn (1.20x)
"What's Mission Villa's total debt?"       → $14,697/mo
"Find deals about Adobe or SDK risk"       → batch.ai (FTS5 keyword)
"Find deals similar to batch.ai"           → semantic KNN (when embedder configured)
```

---

## Architecture

```
eva_deals.db (SQLite)
├── deals              — structured deal records, SQL-indexed
├── deals_fts          — FTS5 virtual table, auto-synced via triggers
├── deal_embeddings    — vec0 vector table (sqlite-vec, optional)
└── deal_events        — audit log: price cuts, status changes, notes
```

Three query modes — all in one file, no sync issues:
1. **Structured SQL** — exact lookup, filtered lists, field access
2. **FTS5 keyword** — always available, zero deps, <1ms
3. **Semantic KNN** — needs `pip install sqlite-vec` + embedder (add anytime)

---

## Install

```bash
# 1. Copy module into Eva
mkdir -p ~/Eva/modules/deal-db
cp deal_repository.py deals_router.py schema.sql ~/Eva/modules/deal-db/
mkdir -p ~/Eva/data

# 2. Install sqlite-vec (for semantic search — optional but recommended)
pip install sqlite-vec

# 3. Seed current deals
python seed_deals.py

# 4. Wire into FastAPI (in ~/Eva/modules/command-center/main.py or context-api)
#    from deal_repository import DealRepository
#    OR mount the router:
#    from deals_router import router as deals_router
#    app.include_router(deals_router, prefix="/deals", tags=["deals"])
```

**macOS extension check** (run before using sqlite-vec):
```bash
python3 -c "import sqlite3; db = sqlite3.connect(':memory:'); db.enable_load_extension(True); print('OK')"
# If error: pip install sqlean.py  (drop-in replacement, handles macOS extension sandboxing)
```

---

## API Endpoints (FastAPI router)

| Method | Path | Description |
|---|---|---|
| GET | `/deals/` | List all deals (filterable by tier, status, asset_type) |
| GET | `/deals/stats` | DB stats: total deals, by tier, vec enabled |
| GET | `/deals/{id}` | Full deal record |
| GET | `/deals/{id}/field/{field}` | Single field: `/deals/batch-ai/field/noi_mo` |
| GET | `/deals/search/text?q=...` | FTS5 keyword search |
| GET | `/deals/{id}/similar` | Semantic KNN (requires sqlite-vec + embedder) |
| GET | `/deals/compare/fields?fields=...` | Side-by-side comparison |
| POST | `/deals/` | Upsert deal |
| GET | `/deals/{id}/events` | Audit log |
| POST | `/deals/{id}/note` | Add note to event log |

---

## Enable Semantic Search (Optional)

Wire in an embedder to unlock `search_similar()` and hybrid search:

```python
# OpenAI (cheapest option — text-embedding-3-small = $0.02/1M tokens)
import openai
def my_embedder(text: str):
    res = openai.embeddings.create(model="text-embedding-3-small", input=text)
    return res.data[0].embedding

repo.set_embedder(my_embedder)
repo.upsert(deal, embed=True)   # embed=True to compute+store

# Local (free, ~50ms/query on M-series Mac)
# pip install ollama
import ollama
def local_embedder(text: str):
    return ollama.embeddings(model="nomic-embed-text", prompt=text)["embedding"]
```

With 10–20 deals, embedding cost on OpenAI is negligible (~$0.001 total).

---

## Current Deals (June 2026)

| Deal | Tier | Status | NOI/mo | Multiple | Eva Score |
|---|---|---|---|---|---|
| Mission Villa (SSS) | 1 | in-dd | $7,128 | N/A | 81 |
| B2B HR Data Platform | 1 | watch | $6,000 | 1.67x | 61 |
| HTML Framework SaaS | 1 | watch | $4,786 | 2.75x | 74 |
| AI Dropshipping SaaS | 1 | watch | $3,680 | 2.15x | 67 |
| batch.ai | 1 | loi-sent | $1,371 | 3.47x | 62 |
| Business SaaS 0% Churn | 2 | watch | $2,696 | 1.20x | 58 |
| Design Education (QL) | 3 | watch | — | 3.17x | — |
| Food Content Site (QL) | 3 | watch | — | 2.26x | — |
| Amazon FBA (QL) | 3 | watch | — | 1.49x | — |
| Women's Health (QL) | 3 | watch | — | 2.50x | — |

---

## Adding New Deals

```python
from deal_repository import DealRepository, Deal

repo = DealRepository(db_path="~/Eva/data/eva_deals.db")

new_deal = Deal(
    id           = "my-new-deal",
    name         = "My New Deal",
    platform     = "Empire Flippers",
    asset_type   = "saas",
    tier         = 2,
    asking_price = 150_000,
    mrr          = 5_000,
    noi_mo       = 4_200,
)
repo.upsert(new_deal)
repo.log_event("my-new-deal", "created", note="Added from deal sourcing run June 2026")
```

---

## Why not Supabase or Chroma?

- **Supabase free tier auto-pauses after 7 days of inactivity** — breaks Eva silently
- **Chroma = second data store** — dual-write drift, no SQL aggregations
- **sqlite-vec = zero extra infra**, hybrid FTS5+vector in one query, $0/month, fully offline

Reconsider Supabase only if Eva needs multi-device access or a web dashboard.
