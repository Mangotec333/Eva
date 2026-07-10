"""
EVA Projects — FastAPI microservice
====================================
Port: 8779  (deal-scout 8766, deal-analyzer 8767, outreach 8768,
             postcards 8778, projects 8779)

Stores the roadmap as a tree of project nodes in SQLite and serves it as a
collapsible mind-map (the standard way Eva tracks projects). ``GET /`` renders
the same dark-theme, colour-coded, click-to-expand view as the reference
standalone HTML — populated live from the DB. Every edit is recorded in an
append-only ledger.

Endpoints (spec section 5):
  GET    /                       Mind-map HTML (populated from the DB)
  GET    /map                    Alias for /
  GET    /api/nodes              Full tree as nested JSON
  POST   /api/nodes              Create a node
  PATCH  /api/nodes/{id}         Update a node
  DELETE /api/nodes/{id}         Delete a node (cascades to subtree)
  POST   /api/nodes/{id}/move    Reparent a node (rejects cycles)
  POST   /api/import             Replace the tree from JSON
  GET    /api/export             Export the tree as JSON
  POST   /api/seed               Load the roadmap (idempotent on title)
  GET    /api/ledger             Query the change ledger
  GET    /api/ledger/export      Export the ledger (csv|json)
  GET    /health                 Health check
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

import database as db
from models import (
    HealthResponse,
    ImportRequest,
    NodeCreate,
    NodeMove,
    NodeUpdate,
)
from service import NotFoundError, ProjectError, ProjectsService

VERSION = "1.0.0"

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "map.html")

service = ProjectsService()

app = FastAPI(
    title="EVA Projects",
    description=(
        "Roadmap tracker: project nodes stored as a tree, served as a "
        "collapsible mind-map, with an append-only change ledger."
    ),
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _handle(fn):
    """Translate domain exceptions into HTTP errors."""
    try:
        return fn()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProjectError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        )


def _render_map() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        template = fh.read()
    tree = service.get_tree()
    return template.replace(
        "__TREE_JSON__", json.dumps(tree, default=str, ensure_ascii=False)
    )


# ---------------------------------------------------------------------------
# Mind-map view
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["View"])
def mind_map():
    return HTMLResponse(content=_render_map())


@app.get("/map", response_class=HTMLResponse, tags=["View"])
def mind_map_alias():
    return HTMLResponse(content=_render_map())


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    return HealthResponse(
        status="ok", module="eva-projects", version=VERSION, db=db.DB_PATH
    )


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

@app.get("/api/nodes", tags=["Nodes"])
def get_nodes():
    return {"nodes": service.get_tree()}


@app.post("/api/nodes", status_code=201, tags=["Nodes"])
def create_node(payload: NodeCreate):
    return _handle(lambda: service.create_node(payload.model_dump()))


@app.patch("/api/nodes/{node_id}", tags=["Nodes"])
def update_node(node_id: str, payload: NodeUpdate):
    fields = payload.model_dump(exclude_none=True)
    actor = fields.pop("actor", "api")
    return _handle(lambda: service.update_node(node_id, fields, actor=actor))


@app.delete("/api/nodes/{node_id}", tags=["Nodes"])
def delete_node(node_id: str):
    return _handle(lambda: service.delete_node(node_id, actor="api"))


@app.post("/api/nodes/{node_id}/move", tags=["Nodes"])
def move_node(node_id: str, payload: NodeMove):
    return _handle(
        lambda: service.move_node(
            node_id, payload.parent_id, sort_order=payload.sort_order, actor=payload.actor
        )
    )


# ---------------------------------------------------------------------------
# Import / export / seed
# ---------------------------------------------------------------------------

@app.post("/api/import", tags=["Tree"])
def import_tree(payload: ImportRequest):
    nodes = [n.model_dump() for n in payload.nodes]
    return _handle(lambda: service.import_tree(nodes, actor=payload.actor))


@app.get("/api/export", tags=["Tree"])
def export_tree():
    return {"nodes": service.export_tree()}


@app.post("/api/seed", tags=["Tree"])
def seed():
    return _handle(lambda: service.seed(actor="api"))


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

@app.get("/api/ledger", tags=["Ledger"])
def query_ledger(
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
):
    rows = service.query_ledger(from_ts=from_, to_ts=to, event_type=event_type)
    return {"ledger": rows, "count": len(rows)}


@app.get("/api/ledger/export", tags=["Ledger"])
def export_ledger(format: str = Query(default="json")):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=422, detail="format must be csv or json")
    body = service.export_ledger(format)
    media = "text/csv" if format == "csv" else "application/json"
    return PlainTextResponse(content=body, media_type=media)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Projects microservice")
    parser.add_argument("--port", type=int, default=8779, help="Port (default: 8779)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
