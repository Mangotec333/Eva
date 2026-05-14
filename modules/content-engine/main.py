from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import aiosqlite
import json
import uuid
import requests
from datetime import datetime, timezone

from models import (
    DraftCreate, DraftUpdate, RejectRequest,
    BatchApproveRequest, GenerateRequest, VoiceUpdate
)
from database import init_db, DB_PATH

# Optional imports — graceful fallback if modules not yet present
try:
    from generator import generate_drafts as _generate_drafts_sync
except ImportError:
    def _generate_drafts_sync(activity_summary, source_type="activity_stream", platforms=None, count=3):
        return []

def generate_drafts(activity_summary, platforms=None, count=3, source_type="activity_stream"):
    return _generate_drafts_sync(activity_summary, platforms or ["linkedin"], count, source_type)

try:
    from linkedin import post_text
except ImportError:
    async def post_text(draft_text, config):
        return {"posted": False, "error": "linkedin module not available"}

try:
    from scheduler import start_scheduler, stop_scheduler
except ImportError:
    def start_scheduler():
        pass
    def stop_scheduler():
        pass


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="EVA Content Engine", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def row_to_dict(row, cursor):
    """Convert aiosqlite Row to dict using cursor description."""
    return {cursor.description[i][0]: row[i] for i in range(len(row))}


async def get_draft_or_404(draft_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM content_drafts WHERE id=?", (draft_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Draft not found")
            return row_to_dict(row, cur)


async def get_linkedin_config():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM linkedin_config WHERE id='default'") as cur:
            row = await cur.fetchone()
            if not row:
                return {}
            return row_to_dict(row, cur)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "module": "eva-content-engine", "version": "1.0.0"}


# ── Draft Queue ────────────────────────────────────────────────────────────────

@app.get("/drafts/queue")
async def get_draft_queue():
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM content_drafts WHERE status='draft' AND created_at LIKE ? ORDER BY created_at DESC",
            (f"{today}%",)
        ) as cur:
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


# ── Drafts CRUD ────────────────────────────────────────────────────────────────

@app.get("/drafts")
async def list_drafts(status: str = None, platform: str = None):
    query = "SELECT * FROM content_drafts WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if platform:
        query += " AND platform=?"
        params.append(platform)
    query += " ORDER BY created_at DESC"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


@app.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    return await get_draft_or_404(draft_id)


@app.post("/drafts", status_code=201)
async def create_draft(body: DraftCreate):
    draft_id = str(uuid.uuid4())
    now = now_iso()
    hashtags_json = json.dumps(body.hashtags or [])
    scheduled_for = body.scheduled_for or ""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO content_drafts
               (id, platform, content_type, source_type, source_summary, draft_text,
                hook, hashtags, estimated_reach, status, scheduled_for, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (draft_id, body.platform, body.content_type, body.source_type,
             body.source_summary or "", body.draft_text, body.hook or "",
             hashtags_json, body.estimated_reach or "medium", "draft",
             scheduled_for, now, now)
        )
        await db.commit()
    return {"id": draft_id, "status": "draft", "created_at": now}


@app.post("/drafts/generate")
async def generate_drafts_endpoint(body: GenerateRequest):
    drafts = generate_drafts(
        activity_summary=body.activity_summary,
        source_type=body.source_type,
        platforms=body.platforms,
        count=body.count,
    )
    inserted = []
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        for d in drafts:
            draft_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO content_drafts
                   (id, platform, content_type, source_type, source_summary, draft_text,
                    hook, hashtags, estimated_reach, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (draft_id,
                 d.get("platform", body.platforms[0] if body.platforms else "linkedin"),
                 d.get("content_type", "thought_leader"),
                 body.source_type,
                 body.activity_summary,
                 d.get("draft_text", ""),
                 d.get("hook", ""),
                 json.dumps(d.get("hashtags", [])),
                 d.get("estimated_reach", "medium"),
                 "draft", now, now)
            )
            inserted.append({"id": draft_id, **d})
        await db.commit()
    return inserted


@app.post("/drafts/generate-from-eva")
async def generate_from_eva():
    fallback_summary = (
        "Worked on EVA AI personal OS: built content engine module, "
        "integrated LinkedIn posting, reviewed analytics pipeline. "
        "Had a productive morning routine and reflected on intuition vs data in decision-making."
    )
    try:
        resp = requests.get("http://localhost:8765/context/today", timeout=3)
        resp.raise_for_status()
        data = resp.json()
        activity_summary = data.get("summary") or data.get("context") or fallback_summary
    except Exception:
        activity_summary = fallback_summary

    drafts = generate_drafts(
        activity_summary=activity_summary,
        source_type="activity_stream",
        platforms=["linkedin"],
        count=3,
    )
    inserted = []
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        for d in drafts:
            draft_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO content_drafts
                   (id, platform, content_type, source_type, source_summary, draft_text,
                    hook, hashtags, estimated_reach, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (draft_id,
                 d.get("platform", "linkedin"),
                 d.get("content_type", "thought_leader"),
                 "activity_stream",
                 activity_summary,
                 d.get("draft_text", ""),
                 d.get("hook", ""),
                 json.dumps(d.get("hashtags", [])),
                 d.get("estimated_reach", "medium"),
                 "draft", now, now)
            )
            inserted.append({"id": draft_id, **d})
        await db.commit()
    return {"generated": len(inserted), "drafts": inserted}


@app.put("/drafts/{draft_id}")
async def update_draft(draft_id: str, body: DraftUpdate):
    await get_draft_or_404(draft_id)
    fields = []
    params = []
    if body.draft_text is not None:
        fields.append("draft_text=?")
        params.append(body.draft_text)
    if body.hook is not None:
        fields.append("hook=?")
        params.append(body.hook)
    if body.hashtags is not None:
        fields.append("hashtags=?")
        params.append(json.dumps(body.hashtags))
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    fields.append("updated_at=?")
    params.append(now_iso())
    params.append(draft_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE content_drafts SET {', '.join(fields)} WHERE id=?", params
        )
        await db.commit()
    return await get_draft_or_404(draft_id)


@app.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str):
    await get_draft_or_404(draft_id)
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE content_drafts SET status='approved', approved_at=?, updated_at=? WHERE id=?",
            (now, now, draft_id)
        )
        await db.commit()
    return await get_draft_or_404(draft_id)


@app.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, body: RejectRequest):
    await get_draft_or_404(draft_id)
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE content_drafts SET status='rejected', rejection_reason=?, updated_at=? WHERE id=?",
            (body.reason, now, draft_id)
        )
        await db.commit()
    return await get_draft_or_404(draft_id)


@app.post("/drafts/approve-batch")
async def approve_batch(body: BatchApproveRequest):
    config = await get_linkedin_config()
    results = []
    approved_count = 0
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        for draft_id in body.draft_ids:
            async with db.execute("SELECT * FROM content_drafts WHERE id=?", (draft_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    results.append({"id": draft_id, "error": "not found"})
                    continue
                draft = row_to_dict(row, cur)

            # Approve first
            await db.execute(
                "UPDATE content_drafts SET status='approved', approved_at=?, updated_at=? WHERE id=?",
                (now, now, draft_id)
            )
            approved_count += 1

            # Attempt LinkedIn post
            try:
                post_result = await post_text(draft["draft_text"], config)
                if post_result.get("posted"):
                    post_id = post_result.get("post_id", "")
                    post_url = post_result.get("post_url", "")
                    await db.execute(
                        """UPDATE content_drafts
                           SET status='posted', posted_at=?, linkedin_post_id=?, post_url=?, updated_at=?
                           WHERE id=?""",
                        (now, post_id, post_url, now, draft_id)
                    )
                    results.append({"id": draft_id, "status": "posted", "post_id": post_id})
                else:
                    results.append({"id": draft_id, "status": "approved", "error": post_result.get("error")})
            except Exception as e:
                results.append({"id": draft_id, "status": "approved", "error": str(e)})

        await db.commit()
    return {"approved_count": approved_count, "results": results}


@app.post("/drafts/{draft_id}/post")
async def post_draft(draft_id: str):
    draft = await get_draft_or_404(draft_id)
    config = await get_linkedin_config()
    try:
        post_result = await post_text(draft["draft_text"], config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = now_iso()
    if post_result.get("posted"):
        post_id = post_result.get("post_id", "")
        post_url = post_result.get("post_url", "")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE content_drafts
                   SET status='posted', posted_at=?, linkedin_post_id=?, post_url=?, updated_at=?
                   WHERE id=?""",
                (now, post_id, post_url, now, draft_id)
            )
            await db.commit()
        return {"status": "posted", "post_id": post_id, "post_url": post_url}
    else:
        raise HTTPException(status_code=502, detail=post_result.get("error", "Post failed"))


# ── Voice ──────────────────────────────────────────────────────────────────────

@app.get("/voice")
async def get_voice():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM brand_voice") as cur:
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


@app.put("/voice/{voice_id}")
async def update_voice(voice_id: str, body: VoiceUpdate):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM brand_voice WHERE id=?", (voice_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Voice not found")

    fields = []
    params = []
    if body.tone is not None:
        fields.append("tone=?")
        params.append(body.tone)
    if body.example_hooks is not None:
        fields.append("example_hooks=?")
        params.append(json.dumps(body.example_hooks))
    if body.example_posts is not None:
        fields.append("example_posts=?")
        params.append(json.dumps(body.example_posts))
    if body.avoid is not None:
        fields.append("avoid=?")
        params.append(json.dumps(body.avoid))
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    fields.append("updated_at=?")
    params.append(now_iso())
    params.append(voice_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE brand_voice SET {', '.join(fields)} WHERE id=?", params
        )
        await db.commit()
        async with db.execute("SELECT * FROM brand_voice WHERE id=?", (voice_id,)) as cur:
            row = await cur.fetchone()
            return row_to_dict(row, cur)


# ── Analytics ──────────────────────────────────────────────────────────────────

@app.get("/analytics/summary")
async def analytics_summary():
    async with aiosqlite.connect(DB_PATH) as db:
        # Count by status
        async with db.execute(
            "SELECT status, COUNT(*) as count FROM content_drafts GROUP BY status"
        ) as cur:
            status_rows = await cur.fetchall()
            by_status = {r[0]: r[1] for r in status_rows}

        # Total engagement for posted drafts
        async with db.execute(
            """SELECT
                COALESCE(SUM(likes),0) as total_likes,
                COALESCE(SUM(comments),0) as total_comments,
                COALESCE(SUM(shares),0) as total_shares,
                COALESCE(SUM(impressions),0) as total_impressions
               FROM content_drafts WHERE status='posted'"""
        ) as cur:
            eng_row = await cur.fetchone()
            engagement = {
                "total_likes": eng_row[0],
                "total_comments": eng_row[1],
                "total_shares": eng_row[2],
                "total_impressions": eng_row[3],
            } if eng_row else {}

    return {"by_status": by_status, "engagement": engagement}


@app.get("/analytics/weekly")
async def analytics_weekly():
    from datetime import timedelta
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT content_type, COUNT(*) as count,
                      COALESCE(SUM(likes),0) as likes,
                      COALESCE(SUM(comments),0) as comments,
                      COALESCE(SUM(shares),0) as shares,
                      COALESCE(SUM(impressions),0) as impressions
               FROM content_drafts
               WHERE created_at >= ?
               GROUP BY content_type""",
            (seven_days_ago,)
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "content_type": r[0],
                    "count": r[1],
                    "likes": r[2],
                    "comments": r[3],
                    "shares": r[4],
                    "impressions": r[5],
                }
                for r in rows
            ]


# ── Delete ─────────────────────────────────────────────────────────────────────

@app.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str):
    draft = await get_draft_or_404(draft_id)
    if draft["status"] not in ("draft", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete draft with status '{draft['status']}'"
        )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM content_drafts WHERE id=?", (draft_id,))
        await db.commit()
    return {"deleted": True, "id": draft_id}


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8767, reload=False)
