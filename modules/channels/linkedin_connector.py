"""
EVA Channels Hub - LinkedIn Connector
Uses LinkedIn UGC API to post content.
Credentials read from ~/.eva/channels_config.json
"""

import logging
import requests

logger = logging.getLogger(__name__)

LINKEDIN_UGC_URL = "https://api.linkedin.com/v2/ugcPosts"


def get_linkedin_status(cfg: dict) -> dict:
    """Return connection status for LinkedIn."""
    linkedin = cfg.get("linkedin", {})
    token = linkedin.get("access_token", "")
    urn = linkedin.get("person_urn", "")
    connected = bool(token and urn)
    return {
        "connected": connected,
        "person_urn": urn if urn else None,
        "has_token": bool(token),
    }


def post_to_linkedin(content: str, cfg: dict) -> dict:
    """
    Post a text update to LinkedIn via UGC API.

    Returns:
        dict with keys: status, url, post_id   (on success)
        dict with keys: status, error           (on failure)
    """
    linkedin = cfg.get("linkedin", {})
    access_token = linkedin.get("access_token", "")
    person_urn = linkedin.get("person_urn", "")

    if not access_token:
        logger.warning("LinkedIn: access_token not configured")
        return {"status": "not_connected", "error": "LinkedIn access_token not set"}

    if not person_urn:
        logger.warning("LinkedIn: person_urn not configured")
        return {"status": "not_connected", "error": "LinkedIn person_urn not set"}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Full person URN format expected by LinkedIn API
    author_urn = (
        person_urn
        if person_urn.startswith("urn:li:person:")
        else f"urn:li:person:{person_urn}"
    )

    body = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": content,
                },
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
        },
    }

    try:
        response = requests.post(LINKEDIN_UGC_URL, headers=headers, json=body, timeout=15)

        if response.status_code == 201:
            post_id = response.headers.get("x-restli-id", "")
            url = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "https://www.linkedin.com/feed/"
            logger.info(f"LinkedIn post successful: {post_id}")
            return {"status": "posted", "url": url, "post_id": post_id}

        elif response.status_code == 401:
            logger.error("LinkedIn: token expired or invalid (401)")
            return {
                "status": "error",
                "error": "LinkedIn token expired or invalid. Please reconnect your LinkedIn account.",
            }

        elif response.status_code == 403:
            logger.error("LinkedIn: insufficient permissions (403)")
            return {
                "status": "error",
                "error": "LinkedIn token lacks required permissions (w_member_social scope needed).",
            }

        else:
            detail = response.text[:300]
            logger.error(f"LinkedIn post failed: {response.status_code} {detail}")
            return {
                "status": "error",
                "error": f"LinkedIn API error {response.status_code}: {detail}",
            }

    except requests.exceptions.Timeout:
        logger.error("LinkedIn: request timed out")
        return {"status": "error", "error": "LinkedIn API request timed out"}

    except requests.exceptions.RequestException as exc:
        logger.error(f"LinkedIn: network error: {exc}")
        return {"status": "error", "error": f"LinkedIn network error: {exc}"}
