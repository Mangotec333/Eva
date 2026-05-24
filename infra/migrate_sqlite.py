"""
EVA SQLite → PostgreSQL Migration
Moves existing deals.db data into the new Postgres Layer 1.
Run once: python infra/migrate_sqlite.py
"""

import sqlite3
import os
import json
from db_client import pg

SQLITE_PATH = os.path.expanduser("~/.eva/deals.db")

def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"[migrate] No SQLite DB found at {SQLITE_PATH} — skipping.")
        return

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sc = sqlite_conn.cursor()

    pg_conn = pg()
    pc = pg_conn.cursor()

    # ── Migrate deals ──────────────────────────
    try:
        sc.execute("SELECT * FROM deals")
        rows = sc.fetchall()
        migrated = 0
        for row in rows:
            pc.execute("""
                INSERT INTO deals (title, source, asking_price, monthly_revenue, monthly_profit, status, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
            """, (
                row["title"] if "title" in row.keys() else None,
                row["source"] if "source" in row.keys() else "sqlite_import",
                row["asking_price"] if "asking_price" in row.keys() else None,
                row["monthly_revenue"] if "monthly_revenue" in row.keys() else None,
                row["monthly_profit"] if "monthly_profit" in row.keys() else None,
                row["status"] if "status" in row.keys() else "new",
                json.dumps(dict(row)),
            ))
            migrated += 1
        pg_conn.commit()
        print(f"[migrate] Deals: {migrated} rows migrated ✓")
    except Exception as e:
        print(f"[migrate] Deals table: {e}")

    # ── Migrate calendar_events ────────────────
    try:
        sc.execute("SELECT * FROM calendar_events")
        rows = sc.fetchall()
        migrated = 0
        for row in rows:
            pc.execute("""
                INSERT INTO calendar_events (gcal_id, title, start_time, end_time, notes)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (gcal_id) DO NOTHING
            """, (
                row["gcal_id"] if "gcal_id" in row.keys() else None,
                row["title"] if "title" in row.keys() else None,
                row["start_time"] if "start_time" in row.keys() else None,
                row["end_time"] if "end_time" in row.keys() else None,
                json.dumps(dict(row)),
            ))
            migrated += 1
        pg_conn.commit()
        print(f"[migrate] Calendar events: {migrated} rows migrated ✓")
    except Exception as e:
        print(f"[migrate] Calendar table: {e}")

    # ── Migrate email_signals ──────────────────
    try:
        sc.execute("SELECT * FROM email_signals")
        rows = sc.fetchall()
        migrated = 0
        for row in rows:
            pc.execute("""
                INSERT INTO email_signals (gmail_id, subject, sender, signal_type, summary)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (gmail_id) DO NOTHING
            """, (
                row["gmail_id"] if "gmail_id" in row.keys() else None,
                row["subject"] if "subject" in row.keys() else None,
                row["sender"] if "sender" in row.keys() else None,
                row["signal_type"] if "signal_type" in row.keys() else "newsletter",
                row["summary"] if "summary" in row.keys() else None,
            ))
            migrated += 1
        pg_conn.commit()
        print(f"[migrate] Email signals: {migrated} rows migrated ✓")
    except Exception as e:
        print(f"[migrate] Email signals table: {e}")

    sqlite_conn.close()
    pc.close()
    pg_conn.close()
    print("\n[migrate] Migration complete. SQLite preserved at:", SQLITE_PATH)

if __name__ == "__main__":
    migrate()
