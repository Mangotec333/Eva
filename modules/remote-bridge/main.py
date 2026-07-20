"""
EVA Remote-Bridge — FastAPI microservice (the ONE authenticated front door)
===========================================================================
Port: 8795  |  Bind: 0.0.0.0 (this is the ONLY module intentionally exposed)

Remote-Bridge is the single authenticated entry point that lets the founder
(Vineet) send Eva a natural-language instruction from anywhere — phone, Slack,
Perplexity Computer — over a cloudflared tunnel. It takes a goal, hands the
founder an instant receipt (``instruction_id``), then forwards the goal to
Diracatron's registry-scoped dispatch brain in the background and tracks the
outcome (received → dispatched → complete | failed).

Security posture (opposite of local-exec, which is loopback-only):
  * **Bearer auth is mandatory** on every ``/remote/*`` route, checked against
    env ``REMOTE_BRIDGE_API_KEY``.
  * **Fail CLOSED** — if ``REMOTE_BRIDGE_API_KEY`` is unset, every ``/remote/*``
    route returns 503 "not configured" (never allow-all). Logged loudly here.
  * **Rate limited** — fixed-window, max 30 requests/min per API key → 429.
  * Forwards ONLY to Diracatron's registry-scoped dispatch — never raw shell,
    never local-exec directly.
  * Every instruction + every security event is append-only audited.

Endpoints:
  GET  /health                        No auth. Health + whether the API key is
                                      configured (boolean only) + offline flag.
  POST /remote/instruct               Submit a goal; returns {instruction_id, status}.
  GET  /remote/instruct               List recent instructions (newest first).
  GET  /remote/instruct/{id}          Status of one instruction (404 if unknown).
  GET  /remote/instruct/{id}/ledger   Append-only audit trail for one instruction.
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from service import RemoteBridgeService

AGENT_VERSION = "0.1.0"
PORT = int(os.environ.get("REMOTE_BRIDGE_PORT", "8795"))
API_KEY_ENV = "REMOTE_BRIDGE_API_KEY"

RATE_LIMIT_MAX = 30          # requests ...
RATE_LIMIT_WINDOW = 60.0     # ... per this many seconds (fixed window)

logger = logging.getLogger("eva.remote-bridge")
logging.basicConfig(level=logging.INFO)

service = RemoteBridgeService()

# Fixed-window rate-limit state: api_key -> (window_start_epoch, count).
_rate_state: dict[str, list] = {}
_rate_lock = threading.Lock()


def _configured_key() -> str:
    """The current API key from the environment ('' if unset). Read per-request
    so tests (and a live key rotation) take effect without a restart."""
    return (os.environ.get(API_KEY_ENV) or "").strip()


if not _configured_key():
    logger.warning(
        "%s is NOT set — Remote-Bridge is FAILING CLOSED: every /remote/* route "
        "will return 503 until an API key is configured. Set %s before exposing "
        "this service via a tunnel.", API_KEY_ENV, API_KEY_ENV)


def _rate_limited(api_key: str) -> bool:
    """Fixed-window limiter. Returns True if this call exceeds the quota."""
    now = time.time()
    with _rate_lock:
        window_start, count = _rate_state.get(api_key, [now, 0])
        if now - window_start >= RATE_LIMIT_WINDOW:
            window_start, count = now, 0
        count += 1
        _rate_state[api_key] = [window_start, count]
        return count > RATE_LIMIT_MAX


def require_auth(request: Request) -> str:
    """Auth + rate-limit gate for every /remote/* route.

    Order matters: fail closed on missing config first (503), then reject bad
    credentials (401), then enforce the rate limit (429). Security events are
    audited to eva-state best-effort (never blocks the response)."""
    configured = _configured_key()
    if not configured:
        raise HTTPException(status_code=503, detail="Remote-Bridge not configured")

    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token or token != configured:
        service._emit(
            "remote_instruction_unauthorized",
            summary="Rejected unauthenticated remote request",
            entity_id="auth",
            payload={"path": request.url.path, "has_token": bool(token)})
        raise HTTPException(status_code=401, detail="Unauthorized")

    if _rate_limited(token):
        service._emit(
            "remote_instruction_rate_limited",
            summary="Rejected remote request over rate limit",
            entity_id="auth",
            payload={"path": request.url.path, "limit": RATE_LIMIT_MAX})
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return token


app = FastAPI(
    title="EVA Remote-Bridge",
    description=(
        "The ONE authenticated front door: send Eva a natural-language "
        "instruction from anywhere. Mandatory bearer auth (fails closed), "
        "rate limited, forwards only to Diracatron's registry-scoped dispatch, "
        "every instruction append-only audited."
    ),
    version=AGENT_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InstructRequest(BaseModel):
    goal: str
    context: dict | None = None


@app.get("/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "module": "eva-remote-bridge",
        "version": AGENT_VERSION,
        "port": PORT,
        "api_key_configured": bool(_configured_key()),
        "offline": service.offline,
    }


@app.post("/remote/instruct", tags=["Remote-Bridge"])
async def remote_instruct(body: InstructRequest, background: BackgroundTasks,
                          _token: str = Depends(require_auth)):
    """Submit a goal. Persists + audits it, returns an instant receipt, and
    dispatches to Diracatron in the background (never blocks the response)."""
    goal = (body.goal or "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")
    record = service.create_and_ack(goal, body.context)
    background.add_task(service.run_dispatch, record["id"])
    return {"instruction_id": record["id"], "status": record["status"]}


@app.get("/remote/instruct", tags=["Remote-Bridge"])
async def remote_list(limit: int = 20, _token: str = Depends(require_auth)):
    """Recent instructions, newest first (capped)."""
    items = service.list(limit=limit)
    return {"count": len(items), "items": items}


@app.get("/remote/instruct/{instruction_id}", tags=["Remote-Bridge"])
async def remote_status(instruction_id: str, _token: str = Depends(require_auth)):
    """Status of one instruction (404 if unknown)."""
    record = service.get(instruction_id)
    if record is None:
        raise HTTPException(status_code=404, detail="instruction not found")
    return record


@app.get("/remote/instruct/{instruction_id}/ledger", tags=["Remote-Bridge"])
async def remote_ledger(instruction_id: str, _token: str = Depends(require_auth)):
    """Append-only audit trail for one instruction."""
    return {"instruction_id": instruction_id,
            "ledger": service.ledger(instruction_id)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA Remote-Bridge service")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Host to bind (0.0.0.0 OK — auth is mandatory)")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
