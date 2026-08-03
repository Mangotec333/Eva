"""
Eva Call Capture — FastAPI microservice (port 8795)

POST /calls/upload  — multipart audio + contact info -> transcript + AI
                      summary + action items, synced to GHL as a contact note.
GET  /health        — liveness check.

Consent: this endpoint assumes the caller already disclosed recording to all
parties on the call (CA Penal Code 632 — two-party consent). Pass
`consent_disclosed=true` explicitly; the pipeline flags the GHL note when it
is false so nobody mistakes an undisclosed recording for a compliant one.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ghl-agent"))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from ghl_client import build_client as build_ghl_client  # type: ignore

from models import CallCaptureResult, ContactRef
from pipeline import CallCapturePipeline
from summarizer import build_summarizer_client
from transcriber import build_transcriber_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eva.call_capture.main")

PORT = 8795

app = FastAPI(title="Eva Call Capture", version="0.1.0")

_pipeline: CallCapturePipeline | None = None


def get_pipeline() -> CallCapturePipeline:
    global _pipeline
    if _pipeline is None:
        ghl = build_ghl_client()
        _pipeline = CallCapturePipeline(
            transcriber=build_transcriber_client(),
            summarizer=build_summarizer_client(),
            ghl=ghl,
        )
    return _pipeline


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "call-capture", "port": PORT}


@app.post("/calls/upload", response_model=CallCaptureResult)
async def upload_call(
    audio: UploadFile = File(...),
    email: str = Form(""),
    phone: str = Form(""),
    name: str = Form(""),
    consent_disclosed: bool = Form(False),
    sync_to_ghl: bool = Form(True),
) -> CallCaptureResult:
    if not email and not phone:
        raise HTTPException(400, "email or phone is required to sync to GHL")

    contact = ContactRef(email=email, phone=phone, name=name)

    suffix = Path(audio.filename or "call.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name

    try:
        pipeline = get_pipeline()
        result = pipeline.run(
            audio_path=tmp_path,
            contact=contact,
            consent_disclosed=consent_disclosed,
            sync_to_ghl=sync_to_ghl,
        )
    finally:
        os.unlink(tmp_path)

    return result


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
