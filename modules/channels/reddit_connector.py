"""
EVA Channels Hub - Reddit Connector
Uses PRAW to post to subreddits.
Credentials read from ~/.eva/channels_config.json
"""

import logging

logger = logging.getLogger(__name__)

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    logger.warning("PRAW not installed. Reddit connector will be unavailable.")


def get_reddit_status(cfg: dict) -> dict:
    """Return connection status for Reddit."""
    reddit_cfg = cfg.get("reddit", {})
    client_id = reddit_cfg.get("client_id", "")
    client_secret = reddit_cfg.get("client_secret", "")
    username = reddit_cfg.get("username", "")
    password = reddit_cfg.get("password", "")
    connected = bool(client_id and client_secret and username and password)
    return {
        "connected": connected,
        "username": username if username else None,
        "praw_available": PRAW_AVAILABLE,
    }


def _build_reddit_client(cfg: dict):
    """Instantiate a PRAW Reddit client from config."""
    reddit_cfg = cfg.get("reddit", {})
    return praw.Reddit(
        client_id=reddit_cfg.get("client_id", ""),
        client_secret=reddit_cfg.get("client_secret", ""),
        username=reddit_cfg.get("username", ""),
        password=reddit_cfg.get("password", ""),
        user_agent="EVA-ChannelsHub/1.0",
    )


def post_to_subreddit(title: str, content: str, subreddit: str, cfg: dict) -> dict:
    """
    Submit a self (text) post to a subreddit.

    Args:
        title:     Post title (max 300 chars enforced by Reddit)
        content:   Post body text
        subreddit: Target subreddit name (without r/)
        cfg:       Loaded channels config dict

    Returns:
        dict with keys: status, url, post_id   (on success)
        dict with keys: status, error           (on failure / not connected)
    """
    if not PRAW_AVAILABLE:
        return {"status": "error", "error": "PRAW library not installed"}

    reddit_cfg = cfg.get("reddit", {})
    client_id = reddit_cfg.get("client_id", "")
    client_secret = reddit_cfg.get("client_secret", "")
    username = reddit_cfg.get("username", "")
    password = reddit_cfg.get("password", "")

    if not all([client_id, client_secret, username, password]):
        logger.warning("Reddit: credentials not fully configured")
        return {"status": "not_connected", "error": "Reddit credentials not configured"}

    # Enforce Reddit's 300-char title limit
    if len(title) > 300:
        title = title[:297] + "..."

    try:
        reddit = _build_reddit_client(cfg)
        submission = reddit.subreddit(subreddit).submit(
            title=title,
            selftext=content,
        )
        url = f"https://www.reddit.com{submission.permalink}"
        post_id = submission.id
        logger.info(f"Reddit post successful: {url}")
        return {"status": "posted", "url": url, "post_id": post_id}

    except Exception as exc:
        err_str = str(exc)
        logger.error(f"Reddit post failed: {err_str}")

        # Provide human-readable messages for common PRAW errors
        if "INVALID_CREDENTIALS" in err_str or "invalid_grant" in err_str:
            return {
                "status": "error",
                "error": "Reddit credentials are invalid. Check client_id, client_secret, username, and password.",
            }
        if "SUBREDDIT_NOEXIST" in err_str or "404" in err_str:
            return {
                "status": "error",
                "error": f"Subreddit r/{subreddit} does not exist or is private.",
            }
        if "Forbidden" in err_str or "403" in err_str:
            return {
                "status": "error",
                "error": f"Not allowed to post in r/{subreddit}. Check subreddit rules or account karma.",
            }
        return {"status": "error", "error": f"Reddit error: {err_str}"}
