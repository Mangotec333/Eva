# EVA Projects

A project-tracking module that renders the whole roadmap as a **collapsible
mind-map / tree** in the browser — the standard way Eva tracks projects. Ported
from the proven standalone `project_mindmap.html`: dark theme, colour-coded tier
dots, status badges, click-to-expand/collapse, a legend, and links that open in
a new tab. The view is populated **live from the DB**.

- **Tree in SQLite** — every project is a node (`id`, `parent_id`, `title`,
  `tier`, `status`, `meta`, `link`, `sort_order`, timestamps). Nodes form a tree
  via a self-referential FK with `ON DELETE CASCADE`, so deleting a node deletes
  its whole subtree.
- **Mind-map view at `GET /`** — the same look + behaviour as the reference,
  with the tree JSON injected into a single self-contained HTML page (inline
  CSS/JS, no build step, no CDN, no external deps).
- **Import / export** — load or dump the whole tree as nested JSON in one call.
  Import *replaces* the tree, so re-importing is idempotent (no dupes).
- **Idempotent seed** — `seed` loads the current roadmap (the tree ported from
  `project_mindmap.html`). Idempotent on top-level title.
- **Move guards cycles** — reparenting refuses to make a node a child of its own
  descendant (or of itself).
- **Append-only change ledger** — every `node_created`, `node_updated`,
  `node_moved`, `node_deleted`, `tree_imported`, and `seed_run` is recorded (DB
  triggers block UPDATE/DELETE), exportable as CSV/JSON.

Uses the standard library `sqlite3` module (like `outreach` and `postcards`), so
the module runs fully offline with no external database and no network calls.

## Architecture

| File | Responsibility |
|------|----------------|
| `models.py` | Pydantic request models + domain constants (tiers, statuses, defaults). |
| `database.py` | Stdlib `sqlite3` persistence (`Store`). Schema, indexes, and the append-only ledger triggers. |
| `service.py` | `ProjectsService` — CRUD, cascade delete, cycle-safe move, import/export, seed, ledger. All rules live here so the API and CLI behave identically. Holds the seed roadmap tree. |
| `templates/map.html` | The mind-map page (ported CSS/JS). `__TREE_JSON__` is replaced with the live tree by the API. |
| `main.py` | FastAPI REST service + mind-map view (port 8779). |
| `cli.py` | Terminal-first CLI. |
| `test_projects.py` | Offline unit + integration tests. |

## Data model

```
project_nodes(id, parent_id, title, tier, status, meta, link, sort_order, created_at, updated_at)
project_ledger(id, ts, event_type, entity_id, actor, details_json)   -- append-only via triggers
```

- `tier` ∈ `t1 | t2 | t3 | none` — colour-coded dot.
- `status` ∈ `done | inprog | pending | ""` — status badge (`""` = no badge).

## How to run

### REST API + mind-map

```bash
cd modules/projects
./setup.sh                      # pip install, seed, launch on :8779
# or directly:
python main.py --port 8779
```

- Mind map: http://localhost:8779/
- Docs:     http://localhost:8779/docs
- Health:   http://localhost:8779/health

### CLI (terminal-first)

```bash
python cli.py seed                                        # load the roadmap (idempotent)
python cli.py list                                        # flat list of nodes
python cli.py list --tree                                 # nested tree
python cli.py add --title "New task" --parent <id> --tier t2 --status pending
python cli.py update <id> --status done
python cli.py move <id> --parent <id>                     # reparent (rejects cycles)
python cli.py delete <id>                                 # cascades to subtree
python cli.py export --file roadmap.json
python cli.py import --file roadmap.json                  # replaces the tree
python cli.py ledger --export csv
```

## API (port 8779)

| Method & path | Description |
|---------------|-------------|
| `GET /` (`/map`) | Mind-map HTML, populated from the DB |
| `GET /api/nodes` | Full tree as nested JSON |
| `POST /api/nodes` | Create a node |
| `PATCH /api/nodes/{id}` | Update a node |
| `DELETE /api/nodes/{id}` | Delete a node (cascades to subtree) |
| `POST /api/nodes/{id}/move` | Reparent a node (rejects cycles) |
| `POST /api/import` | Replace the tree from JSON |
| `GET /api/export` | Export the tree as JSON |
| `POST /api/seed` | Load the roadmap (idempotent on title) |
| `GET /api/ledger` | Query the change ledger |
| `GET /api/ledger/export?format=csv\|json` | Export the ledger |
| `GET /health` | Health check |

## Tests

```bash
cd modules/projects
python test_projects.py     # standalone runner
pytest test_projects.py     # if pytest is installed
```

Covers (spec section 8): import builds the tree + re-import is idempotent, delete
cascades to children, move reparents and blocks cycles, the ledger is
append-only, and `/` renders every top-level title.
