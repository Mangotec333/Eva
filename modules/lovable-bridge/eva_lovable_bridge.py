#!/usr/bin/env python3
"""
EVA Lovable Bridge — Module 8
FastAPI server on :8769 that wraps Lovable's Build-with-URL API.

Endpoints:
  POST /build         — take a plain-English idea → inject EVA context → return Lovable URL + open in browser
  POST /import        — clone a Lovable GitHub repo into ~/Eva/modules/
  GET  /history       — list all builds generated this session (SQLite)
  GET  /health        — health check

Start: python eva_lovable_bridge.py
"""

import os
import sqlite3
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────
PORT      = 8769
EVA_HOME  = Path.home() / "Eva"
DB_PATH   = EVA_HOME / "logs" / "lovable_bridge.db"
LOVABLE_BASE = "https://lovable.dev/?autosubmit=true#"

# EVA context injected into every Lovable prompt
EVA_CONTEXT_PREFIX = """You are building a module for EVA — an autonomous AI operating system built by Mangotec LLC (Los Angeles, CA).

EVA design system rules:
- Dark theme: bg-gray-950, text-gray-100, accent cyan-400 (#06b6d4)
- Font: font-mono for labels/headers, font-sans for body
- Tailwind CSS + React + TypeScript + Vite
- All components must be standalone and export a default React component
- Backend: FastAPI (Python), SQLite for storage
- Each module exposes a REST API and runs on its own port
- Module should be production-grade, minimal, and fast

Brand: EVA Command Center — Revenue-First Operator Console
Company: Mangotec LLC | Owner: Vineet Ravi | vineetkumar@mangotecusa.com

Now build the following module:
"""

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS builds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            idea        TEXT NOT NULL,
            full_prompt TEXT NOT NULL,
            lovable_url TEXT NOT NULL,
            module_name TEXT,
            imported    INTEGER DEFAULT 0,
            created_at  REAL NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id    INTEGER,
            repo_url    TEXT NOT NULL,
            module_path TEXT NOT NULL,
            status      TEXT NOT NULL,
            created_at  REAL NOT NULL
        )
    """)
    con.commit()
    con.close()


def db_save_build(idea, full_prompt, lovable_url, module_name=None) -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        "INSERT INTO builds (idea, full_prompt, lovable_url, module_name, created_at) VALUES (?,?,?,?,?)",
        (idea, full_prompt, lovable_url, module_name, time.time())
    )
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


def db_save_import(build_id, repo_url, module_path, status):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO imports (build_id, repo_url, module_path, status, created_at) VALUES (?,?,?,?,?)",
        (build_id, repo_url, module_path, status, time.time())
    )
    if status == "success":
        con.execute("UPDATE builds SET imported=1 WHERE id=?", (build_id,))
    con.commit()
    con.close()


def db_get_history(limit=50):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM builds ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="EVA Lovable Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# ── Schemas ───────────────────────────────────────────────────────────────────
class BuildRequest(BaseModel):
    idea: str                        # plain English: "a deal tracker for Empire Flippers"
    module_name: Optional[str] = None  # optional: "deal-tracker-v2"
    extra_context: Optional[str] = None  # any additional instructions
    open_browser: bool = True          # auto-open on Mac


class ImportRequest(BaseModel):
    repo_url: str                    # Lovable GitHub repo URL
    module_name: str                 # what to call it in ~/Eva/modules/
    build_id: Optional[int] = None   # link back to the build record


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "online", "service": "eva_lovable_bridge", "port": PORT}


@app.post("/build")
def build(req: BuildRequest):
    """
    Construct a Lovable Build-with-URL link, save to history, and optionally
    open it in the Mac's default browser.
    """
    # Build full prompt
    parts = [EVA_CONTEXT_PREFIX.strip()]
    if req.module_name:
        parts.append(f"Module name: {req.module_name}")
    parts.append(req.idea)
    if req.extra_context:
        parts.append(f"\nAdditional requirements:\n{req.extra_context}")

    full_prompt = "\n\n".join(parts)

    # Enforce Lovable's 50K char limit
    if len(full_prompt) > 50000:
        full_prompt = full_prompt[:49997] + "..."

    # Encode and build URL
    encoded_prompt = urllib.parse.quote(full_prompt, safe="")
    lovable_url = f"{LOVABLE_BASE}prompt={encoded_prompt}"

    # Save to DB
    build_id = db_save_build(req.idea, full_prompt, lovable_url, req.module_name)

    # Open in browser on Mac
    opened = False
    if req.open_browser:
        try:
            subprocess.run(["open", lovable_url], check=True, timeout=5)
            opened = True
        except Exception:
            pass  # non-Mac or open not available

    return {
        "build_id":    build_id,
        "lovable_url": lovable_url,
        "prompt_chars": len(full_prompt),
        "module_name": req.module_name,
        "opened_in_browser": opened,
        "timestamp":   time.time(),
    }


@app.post("/import")
def import_repo(req: ImportRequest):
    """
    Clone a Lovable-generated GitHub repo into ~/Eva/modules/<module_name>/.
    """
    target_path = EVA_HOME / "modules" / req.module_name

    if target_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Module already exists at {target_path}. Choose a different module_name or delete it first."
        )

    try:
        result = subprocess.run(
            ["git", "clone", req.repo_url, str(target_path)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            db_save_import(req.build_id, req.repo_url, str(target_path), "failed")
            raise HTTPException(status_code=500, detail=result.stderr)

        db_save_import(req.build_id, req.repo_url, str(target_path), "success")

        # List top-level files for confirmation
        files = [f.name for f in target_path.iterdir()] if target_path.exists() else []

        return {
            "status":      "imported",
            "module_name": req.module_name,
            "path":        str(target_path),
            "repo_url":    req.repo_url,
            "files":       files,
            "timestamp":   time.time(),
        }

    except subprocess.TimeoutExpired:
        db_save_import(req.build_id, req.repo_url, str(target_path), "timeout")
        raise HTTPException(status_code=504, detail="Git clone timed out after 120s")


@app.get("/history")
def history(limit: int = 50):
    """Return all Lovable builds generated through this bridge."""
    builds = db_get_history(limit)
    # Truncate full_prompt for readability in the UI
    for b in builds:
        if b.get("full_prompt") and len(b["full_prompt"]) > 300:
            b["full_prompt_preview"] = b["full_prompt"][:300] + "..."
        else:
            b["full_prompt_preview"] = b.get("full_prompt", "")
        del b["full_prompt"]   # don't send 50K chars over the wire
    return {"builds": builds, "total": len(builds)}


@app.delete("/history/{build_id}")
def delete_build(build_id: int):
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM builds WHERE id=?", (build_id,))
    con.commit()
    con.close()
    return {"deleted": build_id}


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"""
  ██╗      ██████╗ ██╗   ██╗ █████╗ ██████╗ ██╗     ███████╗
  ██║     ██╔═══██╗██║   ██║██╔══██╗██╔══██╗██║     ██╔════╝
  ██║     ██║   ██║██║   ██║███████║██████╔╝██║     █████╗
  ██║     ██║   ██║╚██╗ ██╔╝██╔══██║██╔══██╗██║     ██╔══╝
  ███████╗╚██████╔╝ ╚████╔╝ ██║  ██║██████╔╝███████╗███████╗
  ╚══════╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝
  EVA Lovable Bridge — Module 8  |  :8769
""")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
