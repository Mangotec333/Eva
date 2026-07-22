# EVA Treasurer

**Provider-abstracted personal & business finance module** — accounts,
transactions, budgeting rollups, bill tracking, and credit-utilization
monitoring, with **strict personal ↔ business separation** enforced at the
data-access layer.

It follows the standard EVA module contract: its own FastAPI app on its own port
(**8794**), its own SQLite databases, its own CLI, and its own offline test
suite. stdlib `sqlite3` only — no paid dependencies.

```
modules/treasurer/
├── main.py         ← FastAPI app, port 8794, /summary dashboard endpoint
├── models.py       ← Pydantic models (Account, Transaction, Rule, Bill)
├── store.py        ← TreasurerStore — single-side SQLite persistence + dedup
├── providers.py    ← IngestionProvider Protocol + CSV / Mock / SimpleFIN + factory
├── ingest.py       ← provider result → store (upsert, dedup, auto-categorize)
├── budgeting.py    ← daily/weekly/monthly spend-vs-income rollups
├── bills.py        ← bill due-date tracking + credit utilization alerts
├── categorize.py   ← categorization rules engine
├── cli.py          ← CLI (every command takes --side personal|business)
└── tests/          ← offline pytest suite (no network)
```

---

## Quick start

```bash
cd modules/treasurer
./setup.sh                     # installs deps, launches on :8794
# or, for the CLI only:
pip install -r requirements.txt
```

### CLI

Every command requires `--side personal|business` and operates on **only** that
side's database.

```bash
python cli.py ingest --side personal --provider mock          # fixture data, no network
python cli.py ingest --side business --provider csv --csv-path data/txns.csv
python cli.py budget --side personal                          # daily+weekly+monthly rollups
python cli.py budget --side business --period week
python cli.py bills --side personal --within-days 30          # upcoming bills
python cli.py utilization --side business --threshold 0.30    # credit-score protection
```

### API

```bash
uvicorn main:app --port 8794
```

| Method | Path                         | Purpose                                  |
|--------|------------------------------|------------------------------------------|
| GET    | `/health`                    | liveness                                 |
| GET    | `/summary`                   | **personal + business as separate sections** (dashboard tile) |
| GET    | `/{side}/accounts`           | list accounts for one side               |
| POST   | `/{side}/accounts`           | create/upsert an account                 |
| GET    | `/{side}/transactions`       | list transactions (filter by account/date)|
| POST   | `/{side}/transactions`       | add a transaction (auto-categorized)     |
| POST   | `/{side}/ingest`             | run ingestion (`csv` / `mock` / `simplefin`)|
| GET    | `/{side}/budget`             | rollups (optional `?period=day\|week\|month`)|
| GET    | `/{side}/bills`              | upcoming bills (`?within_days=30`)       |
| POST   | `/{side}/bills`              | add a bill                               |
| GET    | `/{side}/utilization`        | per-card utilization + alerts (`?threshold=0.30`)|
| GET/POST | `/{side}/rules`            | categorization rules                     |
| POST   | `/{side}/recategorize`       | re-run rules over uncategorized txns     |

`{side}` must be `personal` or `business`; anything else returns `400`.

---

## Personal vs. business separation — how it is enforced

Separation is **structural, not a query-time flag**. This is the load-bearing
invariant of the module:

1. **Separate database files.** Each side has its own SQLite file —
   `treasurer_personal.db` and `treasurer_business.db` (paths overridable via
   `TREASURER_PERSONAL_DB` / `TREASURER_BUSINESS_DB`). There is no shared table
   filtered by a boolean.
2. **A store is bound to one side.** `TreasurerStore(side, db_path)` opens
   exactly one file. `open_side("personal")` and `open_side("business")` are the
   only entry points, and each returns a store that can touch only its own file.
   No connection ever opens both databases; no query ever unions them.
3. **Cross-side writes are rejected.** Every write stamps the store's `side`, and
   a record explicitly labeled with the *other* side raises `ValueError` before
   it can be persisted (`_guard_side`). A mislabeled inbound row cannot cross the
   boundary.
4. **Every response is labeled and scoped.** Ledgers, budget rollups, bill lists,
   utilization reports, and the `/summary` payload all carry an explicit `side`
   and are computed from a single side's data. `/summary` returns `personal` and
   `business` as two separate sections built from two separate databases —
   nothing is merged.

The test suite proves this in `tests/test_separation.py` (distinct files on
disk, no data bleed, cross-side write blocked).

---

## Ingestion providers (swap-and-play)

Ingestion logic depends only on the `IngestionProvider` Protocol; the concrete
provider is chosen at the edge by the env-driven `make_provider` factory —
mirroring the `BrainClient` / `ResearchClient` seam used elsewhere in EVA. No
provider dependency leaks into the agent/budgeting logic.

| Provider   | Works offline | Notes                                              |
|------------|---------------|----------------------------------------------------|
| `mock`     | ✅ (default)  | fixture data for demos/tests                       |
| `csv`      | ✅            | local CSV / manual import, zero external deps       |
| `simplefin`| network       | pulls from a SimpleFIN Bridge (see below)          |

Select a provider via `--provider`, the `TREASURER_PROVIDER` env var, or the
`provider` field on `POST /{side}/ingest`.

### CSV format

Header row (case-insensitive):

```
institution,account,account_type,date,amount,description[,category,credit_limit,balance,external_id]
```

`amount` is in dollars; **negative = spend, positive = income**. Each distinct
`(institution, account)` pair becomes/updates one account.

### Plugging in a real SimpleFIN token later

No live SimpleFIN token is bundled — the provider is fully wired and documented
but, in tests, exercised only through a mocked HTTP layer (an injected
`http_get`, so no network is touched). To go live:

1. Get a **setup token** from a SimpleFIN Bridge (e.g. <https://bridge.simplefin.org>).
2. Claim it once to obtain an **access URL** (contains basic-auth credentials):
   ```bash
   curl -X POST -d "" $(echo -n "<SETUP_TOKEN>" | base64 -d)
   # → https://<user>:<pass>@bridge.simplefin.org/simplefin
   ```
3. Export it (keep it out of git — it lives only in the environment):
   ```bash
   export SIMPLEFIN_BRIDGE_URL="https://<user>:<pass>@bridge.simplefin.org/simplefin"
   ```
4. **Map each account to a side (one-time).** SimpleFIN has no personal/business
   concept — it returns *every* linked account regardless of side. So before you
   can ingest, you must tell Treasurer which account belongs to which side.
   First list your raw linked accounts (no `--side`, no DB write):
   ```bash
   python cli.py accounts --provider simplefin
   # → [{"external_id": "...", "institution": "...", "name": "...", "account_type": "..."}, ...]
   ```
   Then hand-write `account_sides.json` next to the module (gitignored — it holds
   real account ids), assigning each id to exactly one side:
   ```json
   {
     "personal": ["<checking-id>", "<personal-card-id>"],
     "business": ["<operating-id>", "<business-card-id>"]
   }
   ```
   An id listed under neither side is simply not ingested (allowed). An id listed
   under **both** sides is a hard error at load time. A missing map file is also a
   hard error — Treasurer never silently ingests every account into a side. Set
   `TREASURER_ACCOUNT_MAP_PATH` to override the default location.
5. Ingest per side (each side pulls only its mapped accounts):
   ```bash
   python cli.py ingest --side personal --provider simplefin
   python cli.py ingest --side business --provider simplefin
   ```

The provider GETs `<SIMPLEFIN_BRIDGE_URL>/accounts`, maps the SimpleFIN JSON
schema (org → institution, positive credit-limit → `credit_card`, txn `id` →
dedup key) into Treasurer's normalized shape, filters to the requested side via
`account_sides.json`, then hands off to the same idempotent ingestion path as
every other provider.

---

## Budgeting & credit-score protection

- **Budgeting** (`budgeting.py`): daily / weekly (Monday-anchored) / monthly
  windows; income, spend, net, and per-category spend — computed separately for
  each side.
- **Credit utilization** (`bills.py`): for every credit account,
  `utilization = balance / credit_limit`. Any card at or above the configurable
  threshold (**default 30%**) is flagged as an alert. High utilization is the
  single biggest controllable factor in a credit score, so this is the module's
  credit-score-protection feature.
- **Bills**: due-date tracking with minimum payments; `upcoming_bills` returns
  unpaid bills within a horizon (default 30 days), flagging overdue items.

---

## Data safety

Real financial data **never** enters the repo. `treasurer_personal.db`,
`treasurer_business.db`, all `*.db` files, local `data/` & `imports/` dirs, and
`.env` are gitignored (module-level `.gitignore`, plus the repo-root `*.db`
rule). SimpleFIN access URLs live only in the environment, and
`account_sides.json` (which maps real account ids to sides) is gitignored too.

---

## Tests

Fully offline — no live network calls; the SimpleFIN HTTP layer is mocked with a
fixture.

```bash
cd modules/treasurer
python -m pytest tests -q
```

Covers: data model, dedup, budgeting math, categorization, utilization threshold
alerts, CSV/mock/SimpleFIN ingestion, and personal/business separation.
