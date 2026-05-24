# EVA — 3-Layer Database Stack

## Architecture

```
┌──────────────────────────────────────────────────┐
│  LAYER 1 — PostgreSQL + pgvector                 │
│  Deals, emails, events, orders, logs             │
│  Port: 5432                                      │
└──────────────────────────────────────────────────┘
           ↕ embeddings on write
┌──────────────────────────────────────────────────┐
│  LAYER 2 — Qdrant                                │
│  Angel memory, narrations, Sense Profile (SQ)    │
│  Port: 6333 (HTTP) · 6334 (gRPC)                 │
└──────────────────────────────────────────────────┘
           ↕ entity extraction by angels
┌──────────────────────────────────────────────────┐
│  LAYER 3 — ArcadeDB                              │
│  People → Deals → Companies → Signals (graph)    │
│  Port: 2480 (HTTP + Studio) · 8182 (Gremlin)     │
└──────────────────────────────────────────────────┘
```

**Total cost: $0** — all self-hosted via Docker.
**Cloud migration: one line** — update `.env` QDRANT_URL + API_KEY.

---

## Quickstart

```bash
cd eva-repo/infra

# 1. Copy env
cp .env.example .env

# 2. Boot all 3 layers
docker compose up -d

# 3. Install Python deps
pip install -r requirements.txt

# 4. Init Qdrant collections + ArcadeDB graph schema
python db_client.py

# 5. Migrate existing SQLite data (run once)
python migrate_sqlite.py
```

---

## Ports & UIs

| Service    | Port | UI |
|------------|------|----|
| PostgreSQL | 5432 | psql / any Postgres client |
| Qdrant     | 6333 | http://localhost:6333/dashboard |
| ArcadeDB   | 2480 | http://localhost:2480 (Studio) |

---

## Qdrant Collections

| Collection      | Dimensions | Purpose |
|----------------|------------|---------|
| angel_memory    | 1536       | Angel narrations + outputs |
| deal_context    | 1536       | Deal semantic search |
| email_signals   | 1536       | Email embeddings |
| sense_profile   | 1536       | Sensory Quotient (SQ) vectors |
| narrations      | 1536       | Triage inputs |

---

## ArcadeDB Graph Schema

```
(Person) --[KNOWS]--> (Person)
(Person) --[WORKS_AT]--> (Company)
(Person) --[ASSOCIATED]--> (Deal)
(Company) --[ASSOCIATED]--> (Deal)
(Signal) --[TRIGGERED]--> (Deal)
(Person) --[OWNS]--> (Company)
```

---

## Cloud Migration (when ready)

Only `.env` changes — zero code changes:

```env
# Before (local)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# After (Qdrant Cloud)
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_cloud_api_key
```

---

## Phase Cost Map

| Phase | Vectors | Qdrant Cost |
|-------|---------|-------------|
| Now → launch | < 100K | $0 (local) |
| First 50 users | < 100K | $0 (cloud free) |
| SaaS scale | ~500K | $114/mo |
| Multi-tenant | ~1M+ | $228/mo |
