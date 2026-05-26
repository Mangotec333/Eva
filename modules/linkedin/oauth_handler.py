"""
EVA LinkedIn OAuth Handler
FastAPI endpoint that handles LinkedIn OAuth 2.0 flow,
exchanges the code for an access_token, fetches person URN,
and stores both securely in ~/.eva/channels_config.json.

LinkedIn App Requirements:
  - Products: "Share on LinkedIn" + "Sign In with LinkedIn using OpenID Connect"
  - Scopes needed: openid, profile, w_member_social
  - Redirect URL: http://localhost:8773/linkedin/callback

Setup:
1. Go to https://www.linkedin.com/developers/apps → create/select app
2. Under "Auth" tab → add redirect URL: http://localhost:8773/linkedin/callback
3. Copy Client ID and Client Secret → add to .env
4. Run: uvicorn oauth_handler:app --host 0.0.0.0 --port 8773
5. Open browser: http://localhost:8773/linkedin/login
6. Authorize → token + URN auto-saved to ~/.eva/channels_config.json
7. Done. Close the window. Auto-posting is live.

Token lifetime: 60 days. Re-run this flow to refresh.
"""

import os
import json
import secrets
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="EVA LinkedIn OAuth Handler")

# ── Config ──────────────────────────────────────────────────
CLIENT_ID     = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8773/linkedin/callback"
CONFIG_PATH   = os.path.expanduser("~/.eva/channels_config.json")

# LinkedIn OAuth endpoints
AUTH_URL      = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL     = "https://www.linkedin.com/oauth/v2/accessToken"
PROFILE_URL   = "https://api.linkedin.com/v2/userinfo"  # OpenID Connect userinfo

# Scopes — w_member_social = post on behalf of user
SCOPES        = "openid profile w_member_social"

# In-memory state store (single user, local only)
_state_store: dict = {}


# ── Token storage ────────────────────────────────────────────
def store_credentials(access_token: str, person_urn: str, name: str = ""):
    """Save LinkedIn token + URN to ~/.eva/channels_config.json"""
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)

    config["linkedin"] = {
        "access_token": access_token,
        "person_urn": person_urn,
        "display_name": name,
        "token_note": "Valid 60 days. Re-run OAuth flow to refresh.",
    }

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print(f"[LinkedIn OAuth] Token stored. URN: {person_urn} | Name: {name}")
    return True


# ── Routes ───────────────────────────────────────────────────
@app.get("/linkedin/login")
async def login():
    """Step 1: Redirect to LinkedIn consent screen."""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(500, "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET not set in .env")

    state = secrets.token_urlsafe(16)
    _state_store["state"] = state

    params = (
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
        f"&scope={SCOPES.replace(' ', '%20')}"
    )
    return RedirectResponse(AUTH_URL + params)


@app.get("/linkedin/callback")
async def callback(request: Request):
    """Step 2: LinkedIn redirects here with auth code. Exchange for token."""
    params = dict(request.query_params)

    # Error from LinkedIn
    if "error" in params:
        raise HTTPException(400, f"LinkedIn auth error: {params.get('error_description', params['error'])}")

    code  = params.get("code")
    state = params.get("state")

    if not code:
        raise HTTPException(400, "Missing authorization code")

    # Validate state
    if state != _state_store.get("state"):
        raise HTTPException(403, "State mismatch — possible CSRF. Restart the flow.")

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  REDIRECT_URI,
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

    if token_resp.status_code != 200:
        raise HTTPException(500, f"Token exchange failed: {token_resp.text}")

    token_data   = token_resp.json()
    access_token = token_data.get("access_token")

    if not access_token:
        raise HTTPException(500, "No access_token in LinkedIn response")

    # Fetch person URN + name via OpenID Connect userinfo
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

    if not profile_resp.ok:
        raise HTTPException(500, f"Failed to fetch LinkedIn profile: {profile_resp.text}")

    profile      = profile_resp.json()
    person_sub   = profile.get("sub", "")          # OpenID sub = LinkedIn member ID
    display_name = profile.get("name", "")

    # Store both
    store_credentials(access_token, person_sub, display_name)

    return HTMLResponse(f"""
    <html>
    <body style="font-family:monospace;background:#0d0d0d;color:#00ff88;padding:40px;text-align:center;">
        <h2>✅ EVA LinkedIn Connected</h2>
        <p>Name: <strong>{display_name}</strong></p>
        <p>Member ID: <strong>{person_sub}</strong></p>
        <p>Token saved to <code>~/.eva/channels_config.json</code></p>
        <p style="color:#888;margin-top:24px;">Token is valid for 60 days. Re-run this flow to refresh.</p>
        <p style="color:#00ff88;margin-top:32px;font-size:1.2em;">You can close this window. Auto-posting is live.</p>
        <script>setTimeout(() => window.close(), 5000)</script>
    </body>
    </html>
    """)


@app.get("/linkedin/status")
async def status():
    """Check if LinkedIn credentials are stored."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        li = config.get("linkedin", {})
        if li.get("access_token") and li.get("person_urn"):
            return {
                "status":       "connected",
                "display_name": li.get("display_name"),
                "person_urn":   li.get("person_urn"),
                "token_prefix": li["access_token"][:12] + "...",
            }
    return {"status": "not_connected"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "linkedin-oauth"}
