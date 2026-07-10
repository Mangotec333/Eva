"""
EVA LinkedIn Analytics — FastAPI microservice
==============================================
Port: 8780  (deal-scout 8766, deal-analyzer 8767, outreach 8768,
             postcards 8778, projects 8779, linkedin-analytics 8780)

Reads LinkedIn post analytics (impressions, clicks, reactions, comments,
shares, engagement rate) for an author and stores normalized snapshots + raw
payloads in SQLite. Sync is idempotent and safe to drive from a cron. The real
LinkedIn API call lives behind a single subprocess chokepoint
(``linkedin_analytics.py``); until OAuth is wired on the Eva host, sync returns
``ok=False`` with a clear error and never fakes data. Every sync is recorded in
an append-only ledger.

Endpoints (spec section 5):
  GET    /                       HTML dashboard (posts + latest metrics)
  GET    /health                 Agent status + last-run summary
  POST   /sync                   Trigger a sync
  POST   /tick                   Sync if due (cron-safe)
  GET    /posts                  List posts (latest snapshot joined)
  GET    /posts/{post_urn}       Post + all its snapshots
  GET    /snapshots?post_urn=    Time-series for a post
  GET    /summary                Totals + top post by impressions
  GET    /config                 Get sync config
  PATCH  /config                 Update author_urn / window / token env
  GET    /ledger                 Query the analytics ledger
  GET    /ledger/export          Export the ledger (csv|json)
  GET    /memory                 List agent memory
  GET    /alignment              Mission + current-goals presence
"""

from __future__ import annotations

import argparse
import html
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

import database as db
from models import ConfigUpdate, HealthResponse, MemoryWrite, SyncRequest
from service import LinkedInAnalyticsService, NotFoundError

VERSION = "1.0.0"

service = LinkedInAnalyticsService()

app = FastAPI(
    title="EVA LinkedIn Analytics",
    description=(
        "Reads LinkedIn post analytics and stores normalized snapshots + raw "
        "payloads in SQLite. Idempotent, cron-safe sync behind a single network "
        "chokepoint, with an append-only analytics ledger."
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


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check():
    h = service.health()
    return HealthResponse(
        status="ok",
        module="eva-linkedin-analytics",
        version=VERSION,
        db=db.DB_PATH,
        provider=h["provider"],
        last_sync_at=h["last_sync_at"],
        post_count=h["post_count"],
        snapshot_count=h["snapshot_count"],
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

@app.post("/sync", tags=["Sync"])
def sync(payload: Optional[SyncRequest] = None):
    actor = payload.actor if payload else "api"
    return service.sync(actor=actor)


@app.post("/tick", tags=["Sync"])
def tick(payload: Optional[SyncRequest] = None):
    actor = payload.actor if payload else "cron"
    return service.tick(actor=actor)


# ---------------------------------------------------------------------------
# Posts / snapshots
# ---------------------------------------------------------------------------

@app.get("/posts", tags=["Posts"])
def list_posts():
    return {"posts": service.list_posts()}


@app.get("/posts/{post_urn:path}", tags=["Posts"])
def get_post(post_urn: str):
    return _handle(lambda: service.get_post(post_urn))


@app.get("/snapshots", tags=["Posts"])
def snapshots(post_urn: str = Query(...)):
    return _handle(lambda: {"snapshots": service.list_snapshots(post_urn)})


@app.get("/summary", tags=["Posts"])
def summary(days: int = Query(default=28)):
    return service.summary(days=days)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@app.get("/config", tags=["Config"])
def get_config():
    return service.get_config()


@app.patch("/config", tags=["Config"])
def patch_config(payload: ConfigUpdate):
    fields = payload.model_dump(exclude_none=True)
    actor = fields.pop("actor", "api")
    return service.set_config(fields, actor=actor)


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

@app.get("/ledger", tags=["Ledger"])
def query_ledger(
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
):
    rows = service.query_ledger(from_ts=from_, to_ts=to, event_type=event_type)
    return {"ledger": rows, "count": len(rows)}


@app.get("/ledger/export", tags=["Ledger"])
def export_ledger(format: str = Query(default="json")):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=422, detail="format must be csv or json")
    body = service.export_ledger(format)
    media = "text/csv" if format == "csv" else "application/json"
    return PlainTextResponse(content=body, media_type=media)


# ---------------------------------------------------------------------------
# Agent intelligence layer
# ---------------------------------------------------------------------------

@app.get("/memory", tags=["Agent"])
def list_memory():
    return {"memory": service.memory_all()}


@app.post("/memory", tags=["Agent"])
def write_memory(payload: MemoryWrite):
    return service.memory_set(payload.key, payload.value, source=payload.source)


@app.get("/alignment", tags=["Agent"])
def alignment():
    a = service.load_alignment()
    return {
        "mission_present": a["mission_present"],
        "goals_present": a["goals_present"],
    }


# ---------------------------------------------------------------------------
# HTML dashboard (dependency-free, like projects module GET /)
# ---------------------------------------------------------------------------

def _render_dashboard() -> str:
    posts = service.list_posts()
    cfg = service.get_config()
    h = service.health()

    rows = []
    for p in posts:
        er = p.get("engagement_rate")
        er_str = f"{er * 100:.2f}%" if isinstance(er, (int, float)) else "—"
        text = (p.get("text") or "")[:80]
        url = p.get("post_url") or ""
        title_cell = html.escape(text) or html.escape(p.get("post_urn", ""))
        if url:
            title_cell = f'<a href="{html.escape(url)}" target="_blank">{title_cell}</a>'
        rows.append(
            "<tr>"
            f"<td class='t'>{title_cell}</td>"
            f"<td>{p.get('impressions') if p.get('impressions') is not None else '—'}</td>"
            f"<td>{p.get('clicks') if p.get('clicks') is not None else '—'}</td>"
            f"<td>{p.get('reactions') if p.get('reactions') is not None else '—'}</td>"
            f"<td>{p.get('comments') if p.get('comments') is not None else '—'}</td>"
            f"<td>{p.get('shares') if p.get('shares') is not None else '—'}</td>"
            f"<td>{er_str}</td>"
            f"<td class='src'>{html.escape(p.get('source') or '—')}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            "<tr><td colspan='8' class='empty'>No posts yet — run "
            "<code>eva linkedin-analytics sync</code> once OAuth is wired.</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EVA LinkedIn Analytics</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ background:#0d1117; color:#e6edf3; font-family:-apple-system,
          BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
          margin:0; padding:2rem; }}
  h1 {{ font-size:1.4rem; margin:0 0 .25rem; }}
  .meta {{ color:#8b949e; font-size:.85rem; margin-bottom:1.5rem; }}
  .meta b {{ color:#e6edf3; }}
  table {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
  th, td {{ text-align:left; padding:.55rem .6rem; border-bottom:1px solid #21262d; }}
  th {{ color:#8b949e; font-weight:600; text-transform:uppercase;
        font-size:.72rem; letter-spacing:.04em; }}
  td {{ font-variant-numeric:tabular-nums; }}
  td.t {{ max-width:340px; }}
  td.t a {{ color:#58a6ff; text-decoration:none; }}
  td.src {{ color:#8b949e; }}
  .empty {{ color:#8b949e; text-align:center; padding:2rem; }}
  code {{ background:#161b22; padding:.1rem .35rem; border-radius:4px; }}
  .pill {{ display:inline-block; background:#161b22; border:1px solid #21262d;
           border-radius:999px; padding:.15rem .6rem; margin-right:.4rem; }}
</style>
</head>
<body>
  <h1>EVA LinkedIn Analytics</h1>
  <div class="meta">
    <span class="pill">provider <b>{html.escape(h['provider'])}</b></span>
    <span class="pill">author <b>{html.escape(cfg.get('author_urn') or '—')}</b></span>
    <span class="pill">posts <b>{h['post_count']}</b></span>
    <span class="pill">snapshots <b>{h['snapshot_count']}</b></span>
    <span class="pill">last sync <b>{html.escape(h['last_sync_at'] or 'never')}</b></span>
  </div>
  <table>
    <thead><tr>
      <th>Post</th><th>Impr.</th><th>Clicks</th><th>Reactions</th>
      <th>Comments</th><th>Shares</th><th>Eng. rate</th><th>Source</th>
    </tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, tags=["View"])
def dashboard():
    return HTMLResponse(content=_render_dashboard())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="EVA LinkedIn Analytics microservice"
    )
    parser.add_argument("--port", type=int, default=8780, help="Port (default: 8780)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
