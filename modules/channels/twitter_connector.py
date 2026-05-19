"""
EVA Channels Hub - Twitter/X Connector
Uses Tweepy v4+ to post tweets.
Credentials read from ~/.eva/channels_config.json
"""

import logging

logger = logging.getLogger(__name__)

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    logger.warning("Tweepy not installed. Twitter connector will be unavailable.")

TWEET_MAX_CHARS = 280


def get_twitter_status(cfg: dict) -> dict:
    """Return connection status for Twitter/X."""
    twitter_cfg = cfg.get("twitter", {})
    api_key = twitter_cfg.get("api_key", "")
    api_secret = twitter_cfg.get("api_secret", "")
    access_token = twitter_cfg.get("access_token", "")
    access_secret = twitter_cfg.get("access_secret", "")
    connected = bool(api_key and api_secret and access_token and access_secret)
    return {
        "connected": connected,
        "tweepy_available": TWEEPY_AVAILABLE,
    }


def _truncate_tweet(content: str) -> str:
    """Truncate content to 280 chars with ellipsis if needed."""
    if len(content) <= TWEET_MAX_CHARS:
        return content
    return content[: TWEET_MAX_CHARS - 3] + "..."


def _build_twitter_client(cfg: dict):
    """Instantiate a Tweepy v4 Client (OAuth 1.0a user context)."""
    twitter_cfg = cfg.get("twitter", {})
    client = tweepy.Client(
        consumer_key=twitter_cfg.get("api_key", ""),
        consumer_secret=twitter_cfg.get("api_secret", ""),
        access_token=twitter_cfg.get("access_token", ""),
        access_token_secret=twitter_cfg.get("access_secret", ""),
    )
    return client


def post_tweet(content: str, cfg: dict) -> dict:
    """
    Post a tweet using the Twitter v2 API via Tweepy.

    Content is auto-truncated to 280 characters with "..." if needed.

    Returns:
        dict with keys: status, url, tweet_id  (on success)
        dict with keys: status, error           (on failure / not connected)
    """
    if not TWEEPY_AVAILABLE:
        return {"status": "error", "error": "Tweepy library not installed"}

    twitter_cfg = cfg.get("twitter", {})
    api_key = twitter_cfg.get("api_key", "")
    api_secret = twitter_cfg.get("api_secret", "")
    access_token = twitter_cfg.get("access_token", "")
    access_secret = twitter_cfg.get("access_secret", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        logger.warning("Twitter: credentials not fully configured")
        return {"status": "not_connected", "error": "Twitter credentials not configured"}

    tweet_text = _truncate_tweet(content)

    try:
        client = _build_twitter_client(cfg)
        response = client.create_tweet(text=tweet_text)

        if response.data:
            tweet_id = response.data["id"]
            # Fetch username to build a real URL; fall back to generic link
            try:
                me = client.get_me()
                username = me.data.username if me.data else "i"
            except Exception:
                username = "i"

            url = f"https://twitter.com/{username}/status/{tweet_id}"
            logger.info(f"Tweet posted: {url}")
            return {"status": "posted", "url": url, "tweet_id": tweet_id}

        return {"status": "error", "error": "Twitter API returned no data"}

    except tweepy.errors.Unauthorized as exc:
        logger.error(f"Twitter: unauthorized: {exc}")
        return {
            "status": "error",
            "error": "Twitter credentials are invalid or expired. Please reconnect.",
        }
    except tweepy.errors.Forbidden as exc:
        logger.error(f"Twitter: forbidden: {exc}")
        return {
            "status": "error",
            "error": f"Twitter API forbidden: {exc}. Check app permissions (Read+Write required).",
        }
    except tweepy.errors.TweepyException as exc:
        logger.error(f"Twitter post failed: {exc}")
        return {"status": "error", "error": f"Twitter error: {exc}"}
    except Exception as exc:
        logger.error(f"Twitter unexpected error: {exc}")
        return {"status": "error", "error": f"Unexpected Twitter error: {exc}"}
