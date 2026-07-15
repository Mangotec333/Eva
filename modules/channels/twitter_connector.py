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


def reply_tweet(content: str, in_reply_to_tweet_id: str, cfg: dict) -> dict:
    """Reply to a tweet (used for the CTA reply on our own tweet).

    OAuth 1.0a user context via Tweepy, same creds as ``post_tweet``.

    Returns:
        {status: "posted", url, tweet_id}   on success
        {status: "error"|"not_connected", error}   otherwise
    """
    if not TWEEPY_AVAILABLE:
        return {"status": "error", "error": "Tweepy library not installed"}
    if not in_reply_to_tweet_id:
        return {"status": "error", "error": "in_reply_to_tweet_id required"}

    twitter_cfg = cfg.get("twitter", {})
    if not all([twitter_cfg.get("api_key"), twitter_cfg.get("api_secret"),
                twitter_cfg.get("access_token"), twitter_cfg.get("access_secret")]):
        return {"status": "not_connected", "error": "Twitter credentials not configured"}

    reply_text = _truncate_tweet(content)
    try:
        client = _build_twitter_client(cfg)
        response = client.create_tweet(
            text=reply_text, in_reply_to_tweet_id=str(in_reply_to_tweet_id))
        if response.data:
            tweet_id = response.data["id"]
            url = f"https://twitter.com/i/status/{tweet_id}"
            logger.info(f"Reply posted: {url}")
            return {"status": "posted", "url": url, "tweet_id": tweet_id}
        return {"status": "error", "error": "Twitter API returned no data"}
    except tweepy.errors.TweepyException as exc:
        logger.error(f"Twitter reply failed: {exc}")
        return {"status": "error", "error": f"Twitter error: {exc}"}
    except Exception as exc:
        logger.error(f"Twitter reply unexpected error: {exc}")
        return {"status": "error", "error": f"Unexpected Twitter error: {exc}"}


def like_tweet(tweet_id: str, cfg: dict) -> dict:
    """Like a tweet (our own, right after publishing). OAuth 1.0a user context.

    Returns {status: "liked"} on success, else {status, error}.
    """
    if not TWEEPY_AVAILABLE:
        return {"status": "error", "error": "Tweepy library not installed"}
    if not tweet_id:
        return {"status": "error", "error": "tweet_id required"}

    twitter_cfg = cfg.get("twitter", {})
    if not all([twitter_cfg.get("api_key"), twitter_cfg.get("api_secret"),
                twitter_cfg.get("access_token"), twitter_cfg.get("access_secret")]):
        return {"status": "not_connected", "error": "Twitter credentials not configured"}

    try:
        client = _build_twitter_client(cfg)
        client.like(str(tweet_id))
        return {"status": "liked", "tweet_id": tweet_id}
    except tweepy.errors.TweepyException as exc:
        logger.error(f"Twitter like failed: {exc}")
        return {"status": "error", "error": f"Twitter error: {exc}"}
    except Exception as exc:
        logger.error(f"Twitter like unexpected error: {exc}")
        return {"status": "error", "error": f"Unexpected Twitter error: {exc}"}


def get_tweet_metrics(tweet_id: str, cfg: dict) -> dict:
    """Read public engagement metrics for a tweet via X API v2.

    Uses the app-only Bearer token (``twitter.bearer_token`` in cfg / env
    ``X_BEARER_TOKEN``) to GET /2/tweets/:id?tweet.fields=public_metrics.
    Stdlib urllib — no extra deps needed for the read path.

    Returns:
        {status:"ok", impressions, likes, comments, retweets, clicks}
        {status:"error"|"not_connected", error}
    """
    if not tweet_id:
        return {"status": "error", "error": "tweet_id required"}

    twitter_cfg = cfg.get("twitter", {})
    bearer = (twitter_cfg.get("bearer_token") or "").strip()
    if not bearer:
        return {"status": "not_connected",
                "error": "X bearer token not configured (X_BEARER_TOKEN)"}

    import json as _json
    import urllib.error
    import urllib.request

    url = (f"https://api.twitter.com/2/tweets/{tweet_id}"
           "?tweet.fields=public_metrics,non_public_metrics")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"status": "error", "error": f"X metrics HTTP {exc.code}"}
    except Exception as exc:
        return {"status": "error", "error": f"X metrics error: {exc}"}

    data = body.get("data", {}) or {}
    pm = data.get("public_metrics", {}) or {}
    npm = data.get("non_public_metrics", {}) or {}
    return {
        "status": "ok",
        "tweet_id": tweet_id,
        "impressions": int(npm.get("impression_count", pm.get("impression_count", 0)) or 0),
        "likes": int(pm.get("like_count", 0) or 0),
        "comments": int(pm.get("reply_count", 0) or 0),
        "retweets": int(pm.get("retweet_count", 0) or 0),
        "clicks": int(npm.get("url_link_clicks", 0) or 0),
    }
