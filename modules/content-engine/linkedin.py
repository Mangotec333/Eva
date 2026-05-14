import requests

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"

def post_text(text: str, access_token: str, person_urn: str) -> dict:
    if not access_token or not person_urn:
        return {"error": "LinkedIn not configured — set access_token and person_urn via /linkedin/config", "posted": False}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "author": f"urn:li:person:{person_urn}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        resp = requests.post(f"{LINKEDIN_API_BASE}/ugcPosts", headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            post_id = resp.headers.get("X-RestLi-Id", "")
            return {"posted": True, "post_id": post_id, "status_code": resp.status_code}
        return {"posted": False, "error": resp.text, "status_code": resp.status_code}
    except Exception as e:
        return {"posted": False, "error": str(e)}

def get_post_analytics(post_id: str, access_token: str) -> dict:
    if not access_token or not post_id:
        return {"error": "Missing credentials or post_id"}
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(f"{LINKEDIN_API_BASE}/socialActions/{post_id}", headers=headers, timeout=10)
        if resp.ok:
            data = resp.json()
            return {
                "likes": data.get("likesSummary", {}).get("totalLikes", 0),
                "comments": data.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
                "shares": 0, "impressions": 0,
            }
        return {"error": resp.text}
    except Exception as e:
        return {"error": str(e)}
