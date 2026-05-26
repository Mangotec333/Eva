"""
EVA Email Agent — Angel 20 (Triage)
Runs every morning at 7am
- Scans Gmail for deal flow emails
- Scans Google Calendar for today's events
- Extracts URLs, deal names, broker contacts
- Updates deals.db (no duplicates)
- Generates morning brief JSON for UI
"""

import sqlite3
import json
import os
import re
import datetime
from pathlib import Path

DB_PATH = os.path.expanduser("~/.eva/deals.db")
BRIEF_PATH = os.path.expanduser("~/.eva/morning_brief.json")
CONFIG_PATH = os.path.expanduser("~/.eva/channels_config.json")

# ── Database Setup ──────────────────────────────────────────────
def init_db():
    Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            url TEXT UNIQUE,
            asking_price TEXT,
            revenue TEXT,
            cash_flow TEXT,
            broker_name TEXT,
            broker_contact TEXT,
            notes TEXT,
            eva_score REAL,
            status TEXT DEFAULT 'new',
            discovered_at TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            title TEXT,
            start_time TEXT,
            end_time TEXT,
            attendees TEXT,
            location TEXT,
            description TEXT,
            event_date TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS email_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT UNIQUE,
            sender TEXT,
            subject TEXT,
            snippet TEXT,
            signal_type TEXT,
            extracted_urls TEXT,
            processed_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    return conn

# ── URL Extractor ────────────────────────────────────────────────
def extract_urls(text):
    pattern = r'https?://[^\s\)\]>"\']+'
    urls = re.findall(pattern, text or "")
    # Filter out tracking/redirect URLs, keep deal listing URLs
    deal_domains = ['bizbuysell', 'empireflippers', 'flippa', 'acquire.com',
                    'vestedbb', 'quietlight', 'tranworld', 'sunbeltnetwork',
                    'businessbroker', 'exitadviser', 'microacquire', 'feinternational']
    deal_urls = [u for u in urls if any(d in u.lower() for d in deal_domains)]
    return list(set(deal_urls))

# ── Deal Classifier ──────────────────────────────────────────────
def classify_email(subject, sender, body):
    subject_lower = (subject or "").lower()
    sender_lower = (sender or "").lower()
    body_lower = (body or "").lower()[:2000]

    signals = {
        'deal_flow': any(k in subject_lower or k in body_lower for k in
                        ['for sale', 'listing', 'acquisition', 'business opportunity',
                         'cash flow', 'asking price', 'revenue', 'ebitda', 'sde']),
        'broker': any(k in sender_lower for k in
                     ['empireflippers', 'flippa', 'vestedbb', 'bizbuysell',
                      'quietlight', 'acquire', 'exitadviser']),
        'newsletter': any(k in subject_lower for k in
                         ['newsletter', 'weekly', 'digest', 'issue #']),
        'calendar_invite': 'calendar' in subject_lower or 'meeting' in subject_lower,
        'follow_up': 'follow up' in subject_lower or 'following up' in subject_lower,
    }

    if signals['deal_flow'] or signals['broker']:
        return 'DEAL_FLOW'
    elif signals['newsletter']:
        return 'NEWSLETTER'
    elif signals['calendar_invite']:
        return 'CALENDAR'
    elif signals['follow_up']:
        return 'FOLLOW_UP'
    return 'OTHER'

# ── Morning Brief Generator ──────────────────────────────────────
def generate_brief(conn, emails_processed, calendar_events, new_deals):
    today = datetime.datetime.now().strftime("%A, %B %d, %Y")
    now_ts = datetime.datetime.now().isoformat()

    # Pull today's events
    c = conn.cursor()
    today_date = datetime.date.today().isoformat()
    c.execute("SELECT title, start_time, location, description FROM calendar_events WHERE event_date = ? ORDER BY start_time", (today_date,))
    today_events = [{"title": r[0], "time": r[1], "location": r[2], "description": r[3]} for r in c.fetchall()]

    # Pull all new deals
    c.execute("SELECT title, url, asking_price, cash_flow, source, status FROM deals WHERE status = 'new' ORDER BY discovered_at DESC LIMIT 10")
    pending_deals = [{"title": r[0], "url": r[1], "asking": r[2], "cf": r[3], "source": r[4]} for r in c.fetchall()]

    # Pull deal stats
    c.execute("SELECT COUNT(*) FROM deals")
    total_deals = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM deals WHERE status = 'new'")
    new_count = c.fetchone()[0]

    brief = {
        "generated_at": now_ts,
        "date": today,
        "summary": {
            "emails_scanned": emails_processed,
            "new_deals_found": new_deals,
            "calendar_events_today": len(today_events),
            "total_deals_in_db": total_deals,
            "deals_pending_review": new_count,
        },
        "calendar": today_events,
        "new_deals": pending_deals,
        "actions": []
    }

    # Auto-generate action items
    if today_events:
        brief["actions"].append(f"📅 {len(today_events)} meeting(s) today — review prep notes")
    if new_deals > 0:
        brief["actions"].append(f"🔍 {new_deals} new deal(s) found — score and triage")
    if new_count > 3:
        brief["actions"].append(f"⚡ {new_count} deals pending EVA scoring")

    # Save brief
    Path(os.path.dirname(BRIEF_PATH)).mkdir(parents=True, exist_ok=True)
    with open(BRIEF_PATH, 'w') as f:
        json.dump(brief, f, indent=2)

    return brief

# ── Main Runner ──────────────────────────────────────────────────
def run_email_agent(emails=None, calendar_events=None):
    """
    Called by the cron scheduler with pre-fetched Gmail + Calendar data
    from the EVA connector (since API calls happen in the main agent)
    """
    conn = init_db()
    c = conn.cursor()

    emails_processed = 0
    new_deals = 0

    # Process emails
    if emails:
        for email in emails:
            email_id = email.get('email_id', '')
            sender = email.get('from_', '')
            subject = email.get('subject', '')
            body = email.get('body', '')
            snippet = email.get('snippet', '')

            signal_type = classify_email(subject, sender, body)
            urls = extract_urls(body)

            # Store email signal
            try:
                c.execute("""
                    INSERT OR IGNORE INTO email_signals
                    (email_id, sender, subject, snippet, signal_type, extracted_urls)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (email_id, sender, subject, snippet[:500],
                      signal_type, json.dumps(urls)))
                emails_processed += 1
            except Exception as e:
                pass

            # Store deal URLs
            for url in urls:
                title = subject or "Untitled Deal"
                try:
                    c.execute("""
                        INSERT OR IGNORE INTO deals (source, title, url, notes)
                        VALUES (?, ?, ?, ?)
                    """, (sender, title, url, snippet[:200]))
                    if c.rowcount > 0:
                        new_deals += 1
                except Exception:
                    pass

    # Process calendar events
    if calendar_events:
        for event in calendar_events:
            event_id = event.get('event_id', '')
            start = event.get('start', '')
            event_date = start[:10] if start else ''
            attendees = json.dumps([a.get('email','') for a in event.get('attendees', [])])
            try:
                c.execute("""
                    INSERT OR IGNORE INTO calendar_events
                    (event_id, title, start_time, end_time, attendees, location, description, event_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id,
                    event.get('title', ''),
                    event.get('start', ''),
                    event.get('end', ''),
                    attendees,
                    event.get('location', ''),
                    event.get('description', '')[:500],
                    event_date
                ))
            except Exception:
                pass

    conn.commit()
    brief = generate_brief(conn, emails_processed, calendar_events or [], new_deals)
    conn.close()

    print(f"✅ Email Agent complete")
    print(f"   Emails processed: {emails_processed}")
    print(f"   New deals found: {new_deals}")
    print(f"   Calendar events: {len(calendar_events or [])}")
    print(f"   Brief saved to: {BRIEF_PATH}")
    return brief

if __name__ == "__main__":
    # Test run with empty data
    brief = run_email_agent(emails=[], calendar_events=[])
    print(json.dumps(brief, indent=2))
