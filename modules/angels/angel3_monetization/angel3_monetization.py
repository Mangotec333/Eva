#!/usr/bin/env python3
"""
Angel 3 — EVA's Daily Monetization Agent
Runs every morning at 7am PT, reviews all EVA modules and activity,
and surfaces the single best revenue opportunity for that day.
"""

import os
import json
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

try:
    from openai import OpenAI
except ImportError:
    print("openai not installed. Run: pip install openai")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Paths ─────────────────────────────────────────────────────────────────────
HOME = Path.home()
EVA_DIR = HOME / ".eva"
ANGELS_DIR = EVA_DIR / "angels"
ANGELS_DIR.mkdir(parents=True, exist_ok=True)

KNOWLEDGE_DIR = Path(__file__).parents[3] / "knowledge" / "data"
SOCIAL_DB = EVA_DIR / "eva-social-signals.db"
DEALS_DB = EVA_DIR / "eva-deals.db"
ANGEL3_DAILY = ANGELS_DIR / "angel3_daily.json"
ANGEL3_LOG = ANGELS_DIR / "angel3_log.jsonl"

# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Angel 3 — EVA's Monetization Scanner. You review what has been built, what signals exist, and what the market is paying for, then identify the single highest-leverage revenue opportunity available today.

EVA is built by Vineet Ravi (Mangotec LLC). Current modules:
- Deal Scout (online business acquisition tool) — could be sold as DealScout.ai at $49/mo
- Content Engine (LinkedIn posting with tone adaptation) — could be sold as PostOnce at $39/mo  
- Channels Hub (multi-platform posting) — could be sold as PostOnce Pro at $79/mo
- Knowledge OS (founder memory + playbooks) — could be sold as FounderMemory at $29/mo
- Full EVA OS (all modules) — target $299/mo

Pricing matrix for reference:
- Grata (deal sourcing): $10,000+/yr → EVA Deal Scout gap: $49-99/mo
- Taplio (LinkedIn): $39/mo → EVA Content Engine competitive
- Supergrow (LinkedIn): $39/mo → same
- Rewind AI: DEAD (acquired by Meta) → EVA OS fills this gap NOW
- Screenpipe: $400 lifetime, developer-focused → EVA is business-user-focused

Current GTM: LinkedIn posts with SCOUT/OPERATOR keyword CTAs. $50 each in ads running now.

Your job: Review all context provided and output ONE specific money move for today. Be brutally specific — not "post on LinkedIn" but "DM these 3 types of people with this exact message to close your first $49 customer today."

You MUST respond with valid JSON only — no markdown fences, no prose outside the JSON. Use this exact schema:
{
  "date": "YYYY-MM-DD",
  "generated_at": "HH:MM:SS",
  "todays_money_move": {
    "title": "Short title",
    "product": "Which EVA module to monetize",
    "action": "Exact action to take today",
    "target": "Exactly who to reach out to",
    "message_template": "Exact message to send",
    "expected_outcome": "What happens if you do this",
    "time_required": "X minutes",
    "revenue_potential": "$X in X days"
  },
  "pipeline_summary": {
    "active_leads": 0,
    "keyword_hits_7d": 0,
    "best_signal": "description"
  },
  "competitive_alert": "Any competitor move to be aware of",
  "weekly_pattern": "Pattern identified from last 7 days"
}"""


# ── Context Gatherers ─────────────────────────────────────────────────────────

def read_knowledge_docs(limit_chars: int = 6000) -> str:
    """Read strategy/culture docs from Knowledge OS data directory."""
    if not KNOWLEDGE_DIR.exists():
        return "[Knowledge OS data directory not found — using defaults]"

    chunks = []
    total = 0
    for ext in ("*.md", "*.txt", "*.json"):
        for f in sorted(KNOWLEDGE_DIR.glob(ext)):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                snippet = text[:1500]
                chunks.append(f"=== {f.name} ===\n{snippet}")
                total += len(snippet)
                if total >= limit_chars:
                    break
            except Exception:
                continue
        if total >= limit_chars:
            break

    return "\n\n".join(chunks) if chunks else "[No knowledge docs found]"


def read_social_signals(days: int = 7) -> str:
    """Read last N days of social signals from SQLite DB."""
    if not SOCIAL_DB.exists():
        return "[Social signals DB not found — 0 keyword hits, cold audience]"

    try:
        conn = sqlite3.connect(str(SOCIAL_DB))
        conn.row_factory = sqlite3.Row
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # Try common table shapes; gracefully degrade
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        rows_out = []
        for table in tables:
            try:
                cols = [d[0] for d in conn.execute(
                    f"PRAGMA table_info({table})").fetchall()]
                # look for a date/timestamp column
                date_col = next(
                    (c for c in cols if any(k in c.lower()
                     for k in ("date", "time", "created", "at"))), None)
                if date_col:
                    rows = conn.execute(
                        f"SELECT * FROM {table} WHERE {date_col} >= ? ORDER BY {date_col} DESC LIMIT 50",
                        (cutoff,)).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT * FROM {table} LIMIT 50").fetchall()
                rows_out.append(f"Table: {table} ({len(rows)} rows)\n" +
                                "\n".join(str(dict(r)) for r in rows[:10]))
            except Exception as e:
                rows_out.append(f"Table: {table} — error: {e}")

        conn.close()
        return "\n\n".join(rows_out) if rows_out else "[Social DB empty]"
    except Exception as e:
        return f"[Social DB error: {e}]"


def read_deals_pipeline() -> str:
    """Read current deal pipeline from deals SQLite DB."""
    if not DEALS_DB.exists():
        return "[Deals DB not found — pipeline unknown]"

    try:
        conn = sqlite3.connect(str(DEALS_DB))
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        rows_out = []
        for table in tables:
            try:
                rows = conn.execute(
                    f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 20"
                ).fetchall()
                rows_out.append(f"Table: {table} ({len(rows)} rows)\n" +
                                "\n".join(str(dict(r)) for r in rows[:10]))
            except Exception as e:
                rows_out.append(f"Table: {table} — error: {e}")

        conn.close()
        return "\n\n".join(rows_out) if rows_out else "[Deals DB empty]"
    except Exception as e:
        return f"[Deals DB error: {e}]"


def read_git_log(since_hours: int = 24) -> str:
    """Read recent git commits to know what was built."""
    repo_root = Path(__file__).parents[3]
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since_hours} hours ago",
             "--oneline", "--no-merges"],
            cwd=str(repo_root),
            capture_output=True, text=True, timeout=10
        )
        log = result.stdout.strip()
        return log if log else "[No commits in last 24h]"
    except Exception as e:
        return f"[Git log unavailable: {e}]"


def read_previous_log(days: int = 7) -> str:
    """Read last 7 days of Angel 3 log for pattern mining."""
    if not ANGEL3_LOG.exists():
        return "[No previous Angel 3 log found — first run]"

    try:
        cutoff = datetime.now() - timedelta(days=days)
        lines = []
        with open(ANGEL3_LOG, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry_date = datetime.fromisoformat(
                        entry.get("date", "1970-01-01"))
                    if entry_date >= cutoff:
                        # Only include key fields to save tokens
                        lines.append({
                            "date": entry.get("date"),
                            "title": entry.get("todays_money_move", {}).get("title"),
                            "product": entry.get("todays_money_move", {}).get("product"),
                            "best_signal": entry.get("pipeline_summary", {}).get("best_signal"),
                        })
                except Exception:
                    continue
        return json.dumps(lines, indent=2) if lines else "[No recent log entries]"
    except Exception as e:
        return f"[Log read error: {e}]"


# ── Seed Context Override ─────────────────────────────────────────────────────

def get_seed_context() -> str | None:
    """Return a seed context string if provided via env var or arg."""
    # Check for --seed-context flag
    if "--seed-context" in sys.argv:
        idx = sys.argv.index("--seed-context")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return os.environ.get("ANGEL3_SEED_CONTEXT")


# ── Main Agent ────────────────────────────────────────────────────────────────

def build_user_prompt(seed_context: str | None = None) -> str:
    now_pt = datetime.now(timezone(timedelta(hours=-7)))  # PT (no DST adjust)
    date_str = now_pt.strftime("%Y-%m-%d")
    time_str = now_pt.strftime("%H:%M:%S")

    if seed_context:
        context_block = f"[SEED CONTEXT PROVIDED]\n{seed_context}"
    else:
        context_block = f"""[KNOWLEDGE OS DOCS]
{read_knowledge_docs()}

[SOCIAL SIGNALS — LAST 7 DAYS]
{read_social_signals()}

[DEALS PIPELINE]
{read_deals_pipeline()}

[GIT LOG — LAST 24H]
{read_git_log()}

[ANGEL 3 HISTORY — LAST 7 DAYS]
{read_previous_log()}"""

    return f"""Today is {date_str} at {time_str} PT.

{context_block}

Based on all of the above, output the single best revenue opportunity for today as JSON.
Fill in date="{date_str}" and generated_at="{time_str}" exactly."""


def run_agent(seed_context: str | None = None) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set. Add it to ~/.env or export it.")

    client = OpenAI(api_key=api_key)

    user_prompt = build_user_prompt(seed_context)

    print("Angel 3: Calling OpenAI gpt-4o-mini...", flush=True)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    result = json.loads(raw)
    return result


def save_outputs(result: dict, extra_path: Path | None = None) -> None:
    # Overwrite daily file
    with open(ANGEL3_DAILY, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"Saved daily output → {ANGEL3_DAILY}")

    # Append to running log
    with open(ANGEL3_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")
    print(f"Appended to log    → {ANGEL3_LOG}")

    # Optional extra save path (e.g. workspace for testing)
    if extra_path:
        with open(extra_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Saved extra copy   → {extra_path}")


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Angel 3 — EVA Daily Monetization Agent")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Check for optional extra output path arg
    extra_out = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            extra_out = Path(sys.argv[idx + 1])

    seed = get_seed_context()
    if seed:
        print(f"Using seed context ({len(seed)} chars)")

    try:
        result = run_agent(seed_context=seed)
        save_outputs(result, extra_path=extra_out)

        print("\n" + "=" * 60)
        print("  TODAY'S MONEY MOVE")
        print("=" * 60)
        move = result.get("todays_money_move", {})
        print(f"  Title:    {move.get('title', 'N/A')}")
        print(f"  Product:  {move.get('product', 'N/A')}")
        print(f"  Time:     {move.get('time_required', 'N/A')}")
        print(f"  Revenue:  {move.get('revenue_potential', 'N/A')}")
        print("=" * 60)
        print("\nFull JSON output:")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
