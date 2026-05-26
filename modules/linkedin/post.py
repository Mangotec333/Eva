"""
EVA LinkedIn Post CLI
Post to LinkedIn directly from terminal using stored credentials.

Usage:
  python post.py "Your post text here"
  python post.py --file post.txt
  python post.py --status          # check connection status

Reads token from ~/.eva/channels_config.json (set by oauth_handler.py)
"""

import sys
import json
import os
import argparse
import requests

CONFIG_PATH      = os.path.expanduser("~/.eva/channels_config.json")
LINKEDIN_UGC_URL = "https://api.linkedin.com/v2/ugcPosts"


def load_credentials():
    if not os.path.exists(CONFIG_PATH):
        print("❌ channels_config.json not found. Run OAuth flow first.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    li = config.get("linkedin", {})
    token = li.get("access_token")
    urn   = li.get("person_urn")
    if not token or not urn:
        print("❌ LinkedIn not connected. Run: uvicorn oauth_handler:app --port 8773 → open http://localhost:8773/linkedin/login")
        sys.exit(1)
    return token, urn


def post_to_linkedin(text: str) -> dict:
    token, urn = load_credentials()

    author_urn = urn if urn.startswith("urn:li:person:") else f"urn:li:person:{urn}"

    headers = {
        "Authorization":             f"Bearer {token}",
        "Content-Type":              "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    body = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary":    {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    resp = requests.post(LINKEDIN_UGC_URL, headers=headers, json=body, timeout=15)

    if resp.status_code == 201:
        post_id = resp.headers.get("x-restli-id", "")
        url     = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "https://www.linkedin.com/feed/"
        print(f"✅ Posted successfully!")
        print(f"   URL: {url}")
        return {"posted": True, "post_id": post_id, "url": url}
    elif resp.status_code == 401:
        print("❌ Token expired. Re-run the OAuth flow: http://localhost:8773/linkedin/login")
    elif resp.status_code == 403:
        print("❌ Missing permission. Ensure w_member_social scope is enabled in your LinkedIn app.")
    else:
        print(f"❌ Error {resp.status_code}: {resp.text[:300]}")

    return {"posted": False, "error": resp.text}


def check_status():
    try:
        token, urn = load_credentials()
        print(f"✅ LinkedIn connected")
        print(f"   URN:   {urn}")
        print(f"   Token: {token[:12]}...")
    except SystemExit:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVA LinkedIn Post CLI")
    parser.add_argument("text",        nargs="?", help="Post text")
    parser.add_argument("--file",      help="Read post text from file")
    parser.add_argument("--status",    action="store_true", help="Check connection status")
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.file:
        with open(args.file) as f:
            text = f.read().strip()
        post_to_linkedin(text)
    elif args.text:
        post_to_linkedin(args.text)
    else:
        parser.print_help()
