# Eva X Autopost (Free tier: 1 post/24h)
# Upgrade: set POST_FREQUENCY + X Basic tier ($100/mo, 3000 posts/mo)

import os, json, tweepy, sys
from datetime import datetime
from pathlib import Path

SCHEDULED_DIR = Path(__file__).parent / "scheduled"

class EvaGuardrail:
    """Run before every post. Never bypass."""
    RED_TERMS = ["dive", "simulate", "simulation"]
    def check(self, text):
        t = text.lower()
        for term in self.RED_TERMS:
            if term in t:
                return False, f"BLOCK: red term '{term}' - reframe as 'draw/win the foul' or 'assist/finish'"
        # Claims about named individuals stated as fact = require reframing
        # (handled by Eva's content layer; this is the hard-stop backstop)
        return True, "PASS"

class EvaXPoster:
    def __init__(self):
        self.auth = tweepy.OAuth1UserHandler(
            os.getenv("X_API_KEY"),
            os.getenv("X_API_SECRET"),
            os.getenv("X_ACCESS_TOKEN"),
            os.getenv("X_ACCESS_TOKEN_SECRET"),
        )
        self.api = tweepy.API(self.auth)
        self.guardrail = EvaGuardrail()

    def post(self, text, thread=None):
        """Post a single tweet or a thread. Runs guardrail first."""
        ok, msg = self.guardrail.check(text)
        if not ok:
            return {"status": "blocked", "reason": msg}
        if len(text) > 280:
            return {"status": "error", "reason": f"{len(text)} chars > 280"}
        try:
            # Single post (free tier = 1/24h)
            resp = self.api.update_status(status=text)
            return {"status": "posted", "id": resp.id, "url": f"https://x.com/i/web/status/{resp.id}"}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def post_thread(self, posts):
        """Post a thread. NOTE: requires X Basic tier for reliable threading."""
        results = []
        reply_to = None
        for p in posts:
            ok, msg = self.guardrail.check(p)
            if not ok:
                return {"status": "blocked", "reason": msg}
            try:
                resp = self.api.update_status(status=p, in_reply_to_status_id=reply_to) if reply_to else self.api.update_status(status=p)
                reply_to = resp.id
                results.append(resp.id)
            except Exception as e:
                return {"status": "error", "reason": str(e), "posted": results}
        return {"status": "threaded", "ids": results}

# Schedule: 1 post/day. To upgrade frequency:
#   1. Set POST_FREQUENCY=twice_daily (or custom cron)
#   2. Upgrade to X Basic tier at developer.x.com
# Manual posts bypass the daily limit - post as many as you want manually.

def load_and_post(filename, poster=None):
    """Load a staged payload from eva/scheduled/ and post it.
    Thread = posts in order (needs X Basic tier).
    Free tier = posts first one only, prints rest as manual-ready."""
    if poster is None:
        poster = EvaXPoster()
    path = SCHEDULED_DIR / filename
    if not path.exists():
        return {"status": "error", "reason": f"file not found: {path}"}
    data = json.loads(path.read_text())
    posts = [p["text"] for p in data["posts"]]
    if len(posts) == 1:
        return poster.post(posts[0])
    return poster.post_thread(posts)

if __name__ == "__main__":
    poster = EvaXPoster()
    dry = "--dry-run" in sys.argv
    if dry:
        print("=== DRY RUN (no posts sent) ===")
    if "--file" in sys.argv:
        fname = sys.argv[sys.argv.index("--file") + 1]
        if dry:
            # Preview file payload without sending
            path = SCHEDULED_DIR / fname
            if not path.exists():
                print(json.dumps({"status": "error", "reason": f"file not found: {path}"}, indent=2))
            else:
                data = json.loads(path.read_text())
                for p in data["posts"]:
                    ok, msg = poster.guardrail.check(p["text"])
                    print(f"[{p['index']}] ({p.get('char_count', len(p['text']))} chars) guardrail={ok} - {msg}")
                    print(f"    {p['text']}")
                    print()
        else:
            print(json.dumps(load_and_post(fname, poster), indent=2))
    else:
        post = "Messi didn't invent the far-post finish. He codified it — right half-space, open body, left foot, bend it away from the keeper into the far corner. A principle turned into a signature weapon."
        if dry:
            ok, msg = poster.guardrail.check(post)
            print(json.dumps({"status": "dry_run", "guardrail": ok, "msg": msg, "text": post, "chars": len(post)}, indent=2))
        else:
            print(json.dumps(poster.post(post), indent=2))
