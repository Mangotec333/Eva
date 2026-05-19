"""
knowledge_api.py
EVA Knowledge OS — FastAPI service on port 8771
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from knowledge_config import KnowledgeConfig as cfg

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EVA Knowledge OS",
    description="Living knowledge base — Vineet's culture, DNA, strategy, experiments & deals.",
    version=cfg.VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_doc(path: Path) -> str:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {path.name}")
    return path.read_text(encoding="utf-8")


def _append_to_doc(path: Path, entry: str) -> None:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = f"\n\n---\n_Appended: {timestamp}_\n\n{entry}\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)


def _list_playbooks() -> list[str]:
    return [
        p.stem
        for p in sorted(cfg.PLAYBOOKS_DIR.glob(f"*{cfg.PLAYBOOK_EXTENSION}"))
        if p.is_file()
    ]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AppendRequest(BaseModel):
    content: str
    author: str = cfg.FOUNDER_NAME


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/knowledge/health")
def health():
    return {
        "status": "ok",
        "service": "EVA Knowledge OS",
        "version": cfg.VERSION,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get("/knowledge/context")
def full_context():
    """
    Returns the complete founder context as structured JSON.
    Used by all EVA modules and Angels to ground themselves in Vineet's DNA.
    """
    docs = {}
    for doc_name in cfg.VALID_DOCS:
        try:
            docs[doc_name] = _read_doc(cfg.doc_path(doc_name))
        except HTTPException:
            docs[doc_name] = None

    playbooks = {}
    for name in _list_playbooks():
        pb_path = cfg.PLAYBOOKS_DIR / f"{name}{cfg.PLAYBOOK_EXTENSION}"
        try:
            playbooks[name] = _read_doc(pb_path)
        except HTTPException:
            playbooks[name] = None

    return {
        "config": cfg.as_dict(),
        "docs": docs,
        "playbooks": playbooks,
        "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get("/knowledge/{doc}")
def get_doc(doc: str):
    """Return a specific knowledge doc by name (culture | strategy | dna | experiments | deals)."""
    if doc not in cfg.VALID_DOCS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc '{doc}'. Valid options: {cfg.VALID_DOCS}",
        )
    content = _read_doc(cfg.doc_path(doc))
    return {
        "doc": doc,
        "content": content,
        "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.post("/knowledge/{doc}/append")
def append_to_doc(doc: str, body: AppendRequest):
    """Append a timestamped entry to any knowledge doc."""
    if doc not in cfg.VALID_DOCS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc '{doc}'. Valid options: {cfg.VALID_DOCS}",
        )
    doc_path = cfg.doc_path(doc)
    _append_to_doc(doc_path, body.content)
    return {
        "status": "appended",
        "doc": doc,
        "author": body.author,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get("/knowledge/playbooks")
def list_playbooks():
    """List all available playbooks."""
    names = _list_playbooks()
    return {
        "playbooks": names,
        "count": len(names),
    }


@app.get("/knowledge/playbooks/{name}")
def get_playbook(name: str):
    """Return a specific playbook by name."""
    pb_path = cfg.PLAYBOOKS_DIR / f"{name}{cfg.PLAYBOOK_EXTENSION}"
    content = _read_doc(pb_path)
    return {
        "playbook": name,
        "content": content,
        "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Entry point (for direct execution)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "knowledge_api:app",
        host=cfg.API_HOST,
        port=cfg.API_PORT,
        reload=True,
    )
