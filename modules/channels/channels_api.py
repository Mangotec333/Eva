"""
EVA Channels Hub - FastAPI microservice
Port: 8770
Handles multi-platform posting with GPT-powered tone adaptation.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# ── Connector imports ──────────────────────────────────────────────────────────
from linkedin_connector import post_to_linkedin, get_linkedin_status
from reddit_connector import post_to_subreddit, get_reddit_status
from twitter_connector import post_tweet, get_twitter_status
from facebook_connector import post_to_page, get_facebook_status
from signal_store import add_signal, get_signals

# ── Paths ──────────────────────────────────────────────────────────────────────
EVA_DIR = Path.home() / ".eva"
CONFIG_PATH = EVA_DIR / "channels_config.json"
LOG_PATH = EVA_DIR / "channels_log.json"

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── OpenAI client ──────────────────────────────────────────────────────────────
openai_client = OpenAI()  # reads OPENAI_API_KEY from env

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="EVA Channels Hub", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://eva.mangotec.ai"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config helpers ─────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "linkedin": {
        "access_token": "AQU9Fa7kiFqzZWVzWwUhqzH5MNEDQflF07pWFadSNdX8gKgclUwrm4Kc94RbXhKr75PI8OGMAXAtoFO1eZRGq6PdPhW9o_b4QeqjiXe_xDnEmncaxUDq-Yv-_Sle_krMo4E6PQ8cbJwRzi9zI2EQ0cpEkT2kSceHoZ4dmOPGXGP_Dqo77-IUaKze4C5ROrA4Mm9ZkfCoEcpAXC7Y6B8d5kd3kUTWA_ngKyDJUjmdApd_dsPL0TSqyDh_WFpVfW9yvuj6l3qCmM9fg4lo6KZ5ds6cr8XhYqfyFVB-Mvb8nNNVby0ZXxUBIBbidneUgDMJlHkOYbrfkHDrMLbczU_hrSmz_ku3HQ",
        "person_urn": "E_qW9RtfrV",
    },
    "reddit": {
        "client_id": "",
        "client_secret": "",
        "username": "",
        "password": "",
    },
    "twitter": {
        "api_key": "",
        "api_secret": "",
        "access_token": "",
        "access_secret": "",
    },
    "facebook": {
        "page_access_token": "",
        "page_id": "",
    },
}


def load_config() -> dict:
    """Load config, seeding defaults if missing."""
    EVA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    EVA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def append_log(entry: dict) -> None:
    """Append an entry to the channels log."""
    EVA_DIR.mkdir(parents=True, exist_ok=True)
    logs: list = []
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH) as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.append(entry)
    with open(LOG_PATH, "w") as f:
        json.dump(logs, f, indent=2)


# ── Tone adaptation ────────────────────────────────────────────────────────────

TONE_PROMPTS = {
    "linkedin": (
        "Rewrite the following text for a LinkedIn professional audience. "
        "Use a data-driven, professional tone. Lead with a strong hook. "
        "Avoid slang. End with an engaging question to prompt discussion. "
        "Keep it under 1300 characters."
    ),
    "reddit": (
        "Rewrite the following text for Reddit. Be conversational and self-aware. "
        "Avoid any marketing speak — sound genuinely helpful and community-minded. "
        "Match the tone of a thoughtful community member, not a brand. "
        "Do not use buzzwords."
    ),
    "twitter": (
        "Rewrite the following text as a punchy tweet. "
        "Maximum 280 characters for the first tweet. Be direct. "
        "Use line breaks for rhythm. Cut all filler words."
    ),
    "facebook": (
        "Rewrite the following text for a Facebook page post. "
        "Use a warm, community-focused tone. Make it slightly longer and personal — "
        "weave in a brief story angle. Invite engagement naturally."
    ),
}


def adapt_tone(content: str, platform: str) -> str:
    """Use GPT-4o-mini to adapt content tone for the target platform."""
    system_prompt = TONE_PROMPTS.get(platform)
    if not system_prompt:
        return content  # unknown platform — return as-is

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            max_tokens=600,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning(f"Tone adaptation failed for {platform}: {exc}")
        return content  # fall back to original


# ── Pydantic models ────────────────────────────────────────────────────────────

class ConnectPayload(BaseModel):
    credentials: dict


class ComposePayload(BaseModel):
    content: str
    platforms: List[str]
    reddit_subreddit: Optional[str] = "EcommerceAcquisitions"
    schedule_at: Optional[str] = None


class AdaptPayload(BaseModel):
    content: str
    platform: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/channels/health")
def health_check():
    return {"status": "ok", "service": "channels-hub", "port": 8770}


@app.get("/channels/status")
def channels_status():
    """Return connection status for all platforms."""
    cfg = load_config()
    return {
        "platforms": {
            "linkedin": get_linkedin_status(cfg),
            "reddit": get_reddit_status(cfg),
            "twitter": get_twitter_status(cfg),
            "facebook": get_facebook_status(cfg),
        }
    }


@app.post("/channels/connect/{platform}")
def connect_platform(platform: str, payload: ConnectPayload):
    """Store credentials for a platform."""
    allowed = {"linkedin", "reddit", "twitter", "facebook"}
    if platform not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    cfg = load_config()
    if platform not in cfg:
        cfg[platform] = {}
    cfg[platform].update(payload.credentials)
    save_config(cfg)
    logger.info(f"Credentials updated for {platform}")
    return {"status": "saved", "platform": platform}


@app.post("/channels/compose")
def compose(payload: ComposePayload):
    """
    Post to selected platforms with automatic tone adaptation.
    Returns per-platform results.
    """
    cfg = load_config()
    results = []

    for platform in payload.platforms:
        adapted = adapt_tone(payload.content, platform)
        entry = {"platform": platform, "adapted_content": adapted}

        try:
            if platform == "linkedin":
                result = post_to_linkedin(adapted, cfg)
            elif platform == "reddit":
                result = post_to_subreddit(
                    title=adapted[:300],
                    content=adapted,
                    subreddit=payload.reddit_subreddit or "EcommerceAcquisitions",
                    cfg=cfg,
                )
            elif platform == "twitter":
                result = post_tweet(adapted, cfg)
            elif platform == "facebook":
                result = post_to_page(adapted, cfg)
            else:
                result = {"status": "error", "error": f"Unknown platform: {platform}"}

            entry.update(result)

        except Exception as exc:
            logger.error(f"Post failed on {platform}: {exc}")
            entry["status"] = "error"
            entry["error"] = str(exc)

        results.append(entry)

        # Log the attempt
        append_log({
            "timestamp": datetime.utcnow().isoformat(),
            "platform": platform,
            "status": entry.get("status"),
            "url": entry.get("url"),
            "error": entry.get("error"),
            "adapted_content": adapted[:200],
        })

    return {"results": results}


@app.get("/channels/signal")
def signal_feed():
    """Return last 20 engagement signals across platforms."""
    signals = get_signals(limit=20)
    return {"signals": signals}


@app.post("/channels/adapt")
def adapt_endpoint(payload: AdaptPayload):
    """Adapt text for a specific platform tone."""
    adapted = adapt_tone(payload.content, payload.platform)
    return {"platform": payload.platform, "original": payload.content, "adapted": adapted}
