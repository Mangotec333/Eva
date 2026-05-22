"""
EVA Shopify OAuth Server
Handles OAuth flow to get Admin API access token
Credentials loaded from ~/.eva/channels_config.json
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import urllib.request
import json
import os

def load_config():
    config_path = os.path.expanduser("~/.eva/channels_config.json")
    with open(config_path) as f:
        return json.load(f).get("shopify", {})

PORT = 8772
REDIRECT_URI = "http://localhost:8772/shopify/callback"
SCOPES = "read_products,write_products,read_orders,write_orders,read_inventory,write_inventory,read_fulfillments,write_fulfillments"

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        config = load_config()
        CLIENT_ID = config.get("client_id")
        CLIENT_SECRET = config.get("client_secret")
        STORE = config.get("store_url")
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/shopify/install":
            auth_url = (
                f"https://{STORE}/admin/oauth/authorize"
                f"?client_id={CLIENT_ID}&scope={SCOPES}"
                f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}&state=eva_auth_001"
            )
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()

        elif parsed.path == "/shopify/callback":
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            if not code:
                self.send_response(400); self.end_headers()
                return
            payload = json.dumps({"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": code}).encode()
            req = urllib.request.Request(
                f"https://{STORE}/admin/oauth/access_token", data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                token = data.get("access_token")
                config_path = os.path.expanduser("~/.eva/channels_config.json")
                with open(config_path) as f: full = json.load(f)
                full["shopify"]["admin_api_token"] = token
                with open(config_path, "w") as f: json.dump(full, f, indent=2)
                print(f"✅ Token saved: {token[:20]}...")
                self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers()
                self.wfile.write(b"<h1>EVA Connected to Shopify</h1><p>Token saved. Close this window.</p>")
                import threading; threading.Thread(target=self.server.shutdown).start()

    def log_message(self, *args): pass

if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), OAuthHandler)
    print(f"Open: http://localhost:{PORT}/shopify/install")
    server.serve_forever()
