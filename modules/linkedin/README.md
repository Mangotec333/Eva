# EVA LinkedIn Module

Auto-posts to LinkedIn. One-time OAuth setup. Permanent token stored in `~/.eva/channels_config.json`.

---

## One-Time Setup (10 minutes)

### Step 1 — Create LinkedIn App
1. Go to https://www.linkedin.com/developers/apps
2. Click **Create App**
   - App name: `EVA`
   - LinkedIn Page: your personal page or Mangotec
   - App logo: any image
3. Under **Products** tab → request:
   - ✅ **Share on LinkedIn**
   - ✅ **Sign In with LinkedIn using OpenID Connect**
4. Under **Auth** tab:
   - Copy **Client ID** and **Client Secret**
   - Add Redirect URL: `http://localhost:8773/linkedin/callback`
5. Save changes

### Step 2 — Set env vars
Add to `~/.eva/.env` or your shell:
```bash
export LINKEDIN_CLIENT_ID=your_client_id_here
export LINKEDIN_CLIENT_SECRET=your_client_secret_here
```

### Step 3 — Run OAuth flow (once)
```bash
cd eva-repo/modules/linkedin
pip install -r requirements.txt
uvicorn oauth_handler:app --host 0.0.0.0 --port 8773
```
Open browser: **http://localhost:8773/linkedin/login**

Authorize → token auto-saved → window closes.

### Step 4 — Verify
```bash
python post.py --status
# ✅ LinkedIn connected
#    URN:   abc123xyz
#    Token: AQV...
```

---

## Daily Use

### Post from terminal
```bash
python post.py "Your post text here"
```

### Post from file
```bash
python post.py --file todays_post.txt
```

### Check status
```bash
python post.py --status
```

---

## Token Refresh
LinkedIn tokens expire after **60 days**. When expired:
```bash
uvicorn oauth_handler:app --port 8773
# Open http://localhost:8773/linkedin/login again
```
Token auto-overwrites in channels_config.json.

---

## Integration with Content Engine
The content engine (`modules/content-engine/`) uses `modules/channels/linkedin_connector.py` which reads the same `~/.eva/channels_config.json`. Once OAuth is done, the full auto-post pipeline is live.
