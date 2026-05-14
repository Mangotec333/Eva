import aiosqlite
import json
import uuid
from datetime import datetime, timezone

DB_PATH = "eva-content.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS content_drafts (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL DEFAULT 'linkedin',
            content_type TEXT NOT NULL DEFAULT 'thought_leader',
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_summary TEXT DEFAULT '',
            draft_text TEXT NOT NULL,
            hook TEXT DEFAULT '',
            hashtags TEXT DEFAULT '[]',
            estimated_reach TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'draft',
            rejection_reason TEXT DEFAULT '',
            approved_at TEXT DEFAULT '',
            posted_at TEXT DEFAULT '',
            post_url TEXT DEFAULT '',
            linkedin_post_id TEXT DEFAULT '',
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            performance_fetched_at TEXT DEFAULT '',
            scheduled_for TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS brand_voice (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            voice_type TEXT NOT NULL,
            tone TEXT DEFAULT '',
            example_hooks TEXT DEFAULT '[]',
            example_posts TEXT DEFAULT '[]',
            avoid TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS linkedin_config (
            id TEXT PRIMARY KEY,
            access_token TEXT DEFAULT '',
            refresh_token TEXT DEFAULT '',
            person_urn TEXT DEFAULT '',
            token_expires_at TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS post_performance (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0
        )""")
        await db.commit()

        now = datetime.now(timezone.utc).isoformat()
        voices = [
            (str(uuid.uuid4()), "linkedin", "thought_leader",
             "direct, analytical, warm, contrarian when needed",
             json.dumps(["Logic runs the analysis. Intuition makes the call. I reverse-engineered how that works.",
                         "Most high-achieving men I know are data-rich and wisdom-poor. Here's the difference.",
                         "Your intuition is an LLM. And most men are starving it of training data.",
                         "The deal I almost didn't do because the spreadsheet said no.",
                         "I spent 3 years being the most logical person in the room. My wife kept being right anyway."]),
             json.dumps([]),
             json.dumps(["generic hustle culture", "vague inspiration without specifics", "corporate speak"]),
             now),
            (str(uuid.uuid4()), "linkedin", "builder_log",
             "transparent, technical but accessible, real-time, honest about failures",
             json.dumps(["What I built this week (and what broke):",
                         "EVA update — here's what the AI learned about me this week:",
                         "Real numbers. Real builds. No vanity metrics.",
                         "Building in public: the unglamorous version."]),
             json.dumps([]),
             json.dumps(["humblebragging", "vague tech buzzwords"]),
             now),
            (str(uuid.uuid4()), "linkedin", "human_story",
             "vulnerable, specific, relatable to logical men who feel something is missing",
             json.dumps(["My wife made a decision that made no logical sense. She was completely right.",
                         "I almost passed on this because the numbers said no. Here's what happened.",
                         "What my morning ritual taught me about the gap between knowing and doing."]),
             json.dumps([]),
             json.dumps(["generic motivation", "preachiness"]),
             now),
        ]
        for v in voices:
            await db.execute(
                "INSERT OR IGNORE INTO brand_voice (id,platform,voice_type,tone,example_hooks,example_posts,avoid,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                v
            )
        await db.execute(
            "INSERT OR IGNORE INTO linkedin_config (id,access_token,refresh_token,person_urn,token_expires_at,updated_at) VALUES ('default','','','','',?)",
            (now,)
        )
        await db.commit()
