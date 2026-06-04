# EVA Signal Intelligence DB — Module 13

Living knowledge layer. Every signal captured from a morning brief with timestamps.
Active list. Monthly validation. Opinion versioning. Nothing deleted — ever.

## Architecture

```
eva_signals.db (SQLite + FTS5)
├── signals          — one row per insight, full lifecycle
├── signal_validations — every review event logged
├── active_signals   — view: active, sorted by actionable + confidence
├── signals_due_for_validation — view: overdue monthly reviews
└── opinion_ledger   — view: beliefs that changed + what happened
```

## Signal Lifecycle

```
captured (active)
    ├── validated      → proved true by outcome/evidence
    ├── invalidated    → proved false by outcome/evidence
    ├── superseded     → replaced by new version (chains old → new)
    └── expired        → time-window passed (HN, trend signals)
```

**Nothing is deleted.** The opinion ledger shows every mind-change with evidence.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | DB schema — signals, validations, views, FTS5 triggers |
| `signal_repository.py` | All DB operations: save, validate, close, supersede, search |
| `signal_extractor.py` | Parses morning brief text → structured signals |
| `signals_router.py` | FastAPI endpoints (prefix: /signals) |
| `monthly_validation_cron.py` | Monthly LLM-driven re-evaluation of all due signals |
| `__init__.py` | Module exports |

## Signal Types

| Type | Source | Auto-captured? |
|---|---|---|
| `hormozi` | Mozi Minutes / Hormozi emails | ✓ Morning brief |
| `unusual_whiz` | Callan / Unusual Business emails | ✓ Morning brief |
| `learning` | Business signals section | ✓ Morning brief |
| `hn` | Hacker News stories | ✓ Morning brief |
| `trend` | Google Trends | ✓ Morning brief |
| `deal_signal` | Deal flow emails | ✓ Morning brief |
| `market` | General market insight | Manual |
| `opinion` | Strong personal belief | Manual |
| `personal` | Personal development | Manual |

## Quick Start

```python
from eva_signal_db import SignalRepository, extract_and_save_brief

# Save a signal manually
repo = SignalRepository()
signal_id = repo.save(
    signal_type="opinion",
    source="manual",
    title="SaaS multiples compressing in 2026",
    body="Bootstrapped exits now 2–3x ARR vs 4–5x in 2022.",
    domain=["saas", "acquisition"],
    applies_to=["batch-ai"],
    confidence=0.75,
    is_actionable=True,
)

# Extract signals from a morning brief
result = extract_and_save_brief(brief_text, brief_date="2026-06-02")

# Active signals
for s in repo.active():
    print(s["title"])

# Monthly validation
due = repo.due_for_validation()

# Opinion ledger (changed beliefs)
history = repo.opinion_ledger()

# Full-text search
results = repo.search("SaaS multiples")
```

## FastAPI Integration

```python
from fastapi import FastAPI
from eva_signal_db.signals_router import router

app = FastAPI()
app.include_router(router)
```

### Endpoints

| Method | Path | Action |
|---|---|---|
| POST | /signals/ | Save new signal |
| GET | /signals/active | List active signals |
| GET | /signals/stats | DB health stats |
| GET | /signals/due | Signals due for validation |
| GET | /signals/opinion-ledger | Changed beliefs history |
| GET | /signals/search?q= | Full-text search |
| GET | /signals/recent?days= | Recent brief signals |
| GET | /signals/{id} | Get single signal |
| POST | /signals/{id}/validate | Record validation review |
| POST | /signals/{id}/close | Close permanently |
| POST | /signals/{id}/supersede | Version a signal (opinion change) |
| POST | /signals/batch/brief | Batch save from morning brief |

## Monthly Validation Cron

Scheduled: 1st of each month at 6:00 AM PT (13:00 UTC)

```
0 13 1 * *
```

Runs: `python -m eva_signal_db.monthly_validation_cron`

For each signal due for review:
1. LLM evaluates if still true (GPT-4o-mini for cost)
2. Verdict: `still_true | partially_true | false | outdated | needs_more_data`
3. Actions: keep_active / close_validated / close_invalidated / update_confidence
4. Logs every decision to `signal_validations`
5. Sends in-app notification summary

Set `OPENAI_API_KEY` env var to enable LLM evaluation.
Without it, all signals default to `needs_more_data` → manual review.

## Integration with Morning Brief Cron

The morning brief cron (4e9d9238) calls `extract_and_save_brief(brief_body, brief_date)`
at the end of each run, after the notification is sent.

Signals auto-expire:
- HN stories: 14 days
- Trends: 7 days  
- Learning/Opinion: 30-day review cycle (never auto-expires, just gets re-evaluated)

## Kaizen Principle

> We save important things from the morning briefs, our learnings, signals with timestamps.
> We keep an active list. We validate if true every month.
> We end-date and close items that don't apply from what we have learned.
> We change our opinion if proved otherwise. — Vineet Ravi
