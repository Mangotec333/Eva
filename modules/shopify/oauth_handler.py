"""
EVA Shopify OAuth Handler
FastAPI endpoint that handles the Shopify OAuth callback,
exchanges the code for a shpat_ token, and stores it securely.

Setup:
1. Set EVA3 App URL to: https://eva-command-center.vercel.app (done ✅)
2. Set Redirect URL in Partners Dashboard to: https://your-eva-backend/shopify/callback
3. Run this server
4. Reinstall EVA3 on Jack store → token auto-captured and stored

Usage:
  uvicorn oauth_handler:app --host 0.0.0.0 --port 8772
"""

import os
import json
import hmac
import hashlib
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="EVA Shopify OAuth Handler")

# ── Config ─────────────────────────────────────────────────
CLIENT_ID     = os.getenv("SHOPIFY_CLIENT_ID")      # set in .env
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")  # set in .env

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET must be set in environment")
CONFIG_PATH   = os.path.expanduser("~/.eva/channels_config.json")
SCOPES        = "read_products,write_products,read_orders,write_orders,read_inventory,write_inventory,read_price_rules,write_price_rules"

# ── HMAC verification ───────────────────────────────────────
def verify_hmac(params: dict, secret: str) -> bool:
    """Verify Shopify's HMAC signature on OAuth callback."""
    hmac_value = params.pop("hmac", None)
    if not hmac_value:
        return False
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    digest = hmac.new(secret.encode(), sorted_params.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, hmac_value)

# ── Token storage ───────────────────────────────────────────
def store_token(shop: str, token: str):
    """Save shpat_ token to ~/.eva/channels_config.json"""
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)

    config.setdefault("shopify", {})
    config["shopify"]["access_token"] = token
    config["shopify"]["shop"] = shop
    config["shopify"]["token_type"] = "shpat"
    config["shopify"]["store_url"] = shop

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print(f"[OAuth] Token stored for shop: {shop}")
    return True

# ── Routes ──────────────────────────────────────────────────
@app.get("/shopify/install")
async def install(shop: str):
    """Step 1: Redirect merchant to Shopify OAuth consent screen."""
    if not shop.endswith(".myshopify.com"):
        raise HTTPException(400, "Invalid shop domain")

    redirect_uri = os.getenv("REDIRECT_URI", "https://eva-command-center.vercel.app/shopify/callback")
    auth_url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&scope={SCOPES}"
        f"&redirect_uri={redirect_uri}"
        f"&state=eva_oauth_state"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(auth_url)

@app.get("/shopify/callback")
async def callback(request: Request):
    """Step 2: Shopify redirects here with code. Exchange for shpat_ token."""
    params = dict(request.query_params)
    shop  = params.get("shop")
    code  = params.get("code")

    if not shop or not code:
        raise HTTPException(400, "Missing shop or code")

    # Verify HMAC
    verify_params = {k: v for k, v in params.items()}
    if not verify_hmac(verify_params, CLIENT_SECRET):
        raise HTTPException(403, "HMAC verification failed")

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code":          code,
            }
        )

    if response.status_code != 200:
        raise HTTPException(500, f"Token exchange failed: {response.text}")

    data  = response.json()
    token = data.get("access_token")

    if not token or not token.startswith("shpat_"):
        raise HTTPException(500, f"Unexpected token format: {token[:20] if token else 'none'}")

    # Store token
    store_token(shop, token)

    return HTMLResponse(f"""
    <html>
    <body style="font-family:monospace;background:#0d0d0d;color:#00ff88;padding:40px;">
        <h2>✅ EVA Shopify Connected</h2>
        <p>Shop: <strong>{shop}</strong></p>
        <p>Token captured and stored securely.</p>
        <p>You can close this window.</p>
        <script>setTimeout(() => window.close(), 3000)</script>
    </body>
    </html>
    """)

@app.get("/shopify/status")
async def status():
    """Check if token is stored."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        token = config.get("shopify", {}).get("access_token", "")
        if token and token.startswith("shpat_"):
            return {"status": "connected", "shop": config["shopify"].get("shop"), "token_prefix": token[:12] + "..."}
    return {"status": "not_connected"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "shopify-oauth"}
