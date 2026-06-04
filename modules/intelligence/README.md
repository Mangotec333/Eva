# Eva — Intelligence Modules

Living knowledge layer for the Eva Founder OS.

## Modules

### `eva_signal_db/` — Module 13: Signal Intelligence DB
SQLite + FTS5 + semantic embeddings. Captures every signal from every morning brief.
Full lifecycle: active → validated | invalidated | superseded | expired.
Opinion ledger tracks belief changes with evidence. Monthly LLM validation cron.

**Key files:**
- `schema.sql` — DB schema, FTS5, views (active_signals, opinion_ledger, signals_due_for_validation)
- `signal_repository.py` — All CRUD + lifecycle ops (save, validate, close, supersede, search)
- `signal_extractor.py` — Parses morning brief text → structured signals automatically
- `signal_embeddings.py` — OpenAI embeddings, semantic dedup (cosine ≥ 0.88), sentiment + topic tagging
- `signals_router.py` — FastAPI /signals/* endpoints
- `monthly_validation_cron.py` — Monthly LLM re-evaluation of all due signals

**Crons:**
- `4e9d9238` — Morning Brief v2 (5:31am PDT): auto-extracts signals after each brief
- `0ae91303` — Monthly Validation (1st of month, 6am PT): LLM review + closes disproved signals

### `eva_deal_db/` — Module 11: Deal Intelligence DB
SQLite + FTS5 deal pipeline. Tracks all acquisition targets with scoring, events, and lifecycle.

**Key files:**
- `schema.sql` — deals, deal_events, FTS5
- `deal_repository.py` — DealRepository (save, score, search, close, event log)
- `deals_router.py` — FastAPI /deals/* endpoints
- `seed_deals.py` — Seeds 10 deals (batch-ai, mission-villa, tier-1s, tier-3s)

### `morning_brief_task.txt`
Full task prompt for the EVA Morning Brief v2 cron (4e9d9238).
Includes Steps 1–6: calendar scan, deal flow, intelligence feed, compile, send, signal extraction.

---

## Kaizen Principle
> We save important things from the morning briefs. We validate monthly.
> We change our opinion if proved otherwise. — Vineet Ravi
