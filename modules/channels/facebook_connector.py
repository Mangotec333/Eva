"""
EVA Channels Hub - Facebook Connector
Uses Meta Graph API to post to a Facebook Page.
Credentials read from ~/.eva/channels_config.json
"""

import logging
import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def get_facebook_status(cfg: dict) -> dict:
    """Return connection status for Facebook."""
    fb_cfg = cfg.get("facebook", {})
    page_token = fb_cfg.get("page_access_token", "")
    page_id = fb_cfg.get("page_id", "")
    connected = bool(page_token and page_id)
    pending = bool(not page_token)
    return {
        "connected": connected,
        "pending_approval": pending,
        "page_id": page_id if page_id else None,
    }


def post_to_page(content: str, cfg: dict) -> dict:
    """
    Publish a text post to a Facebook Page via the Graph API.

    Returns:
        dict with keys: status, url, post_id   (on success)
        dict with keys: status, error           (on failure)
        dict with keys: status="pending_approval" if token is not set
    """
    fb_cfg = cfg.get("facebook", {})
    page_token = fb_cfg.get("page_access_token", "")
    page_id = fb_cfg.get("page_id", "")

    if not page_token:
        logger.info("Facebook: page_access_token not set — returning pending_approval")
        return {
            "status": "pending_approval",
            "error": "Facebook page_access_token not configured. Connect your Facebook Page to continue.",
        }

    if not page_id:
        logger.warning("Facebook: page_id not configured")
        return {"status": "not_connected", "error": "Facebook page_id not configured"}

    url = f"{GRAPH_API_BASE}/{page_id}/feed"
    params = {
        "message": content,
        "access_token": page_token,
    }

    try:
        response = requests.post(url, data=params, timeout=15)
        data = response.json()

        if response.status_code == 200 and "id" in data:
            post_id = data["id"]
            # Facebook post URL format: page_id_post_id
            post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
            logger.info(f"Facebook post successful: {post_id}")
            return {"status": "posted", "url": post_url, "post_id": post_id}

        # Handle specific Facebook error codes
        fb_error = data.get("error", {})
        code = fb_error.get("code")
        message = fb_error.get("message", "Unknown error")

        if code == 190:
            logger.error("Facebook: token expired (code 190)")
            return {
                "status": "error",
                "error": "Facebook page access token has expired. Please reconnect your Facebook Page.",
            }
        if code == 200:
            logger.error("Facebook: permission denied (code 200)")
            return {
                "status": "error",
                "error": "Facebook token lacks 'pages_manage_posts' permission.",
            }
        if code == 368:
            logger.error("Facebook: temporarily blocked (code 368)")
            return {
                "status": "error",
                "error": "Facebook has temporarily blocked this post. Try again later.",
            }

        logger.error(f"Facebook post failed: {response.status_code} — {message}")
        return {
            "status": "error",
            "error": f"Facebook API error (code {code}): {message}",
        }

    except requests.exceptions.Timeout:
        logger.error("Facebook: request timed out")
        return {"status": "error", "error": "Facebook API request timed out"}

    except requests.exceptions.RequestException as exc:
        logger.error(f"Facebook: network error: {exc}")
        return {"status": "error", "error": f"Facebook network error: {exc}"}
