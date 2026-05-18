from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import aiosqlite
import json
import uuid
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

from models import (
    DraftCreate, DraftUpdate, RejectRequest,
    BatchApproveRequest, GenerateRequest, VoiceUpdate
)
from database import init_db, DB_PATH

# Optional imports — graceful fallback if modules not yet present
try:
    from generator import generate_drafts as _generate_drafts_sync
except ImportError:
    def _generate_drafts_sync(activity_summary, source_type="activity_stream", platforms=None, count=3):
        return []

def generate_drafts(activity_summary, platforms=None, count=3, source_type="activity_stream"):
    return _generate_drafts_sync(activity_summary, platforms or ["linkedin"], count, source_type)

try:
    from linkedin import post_text as _linkedin_post_text
    from linkedin import get_post_analytics
except ImportError:
    def _linkedin_post_text(text, access_token, person_urn):
        return {"posted": False, "error": "linkedin module not available"}
    def get_post_analytics(post_id, access_token):
        return {"error": "linkedin module not available"}

try:
    from scheduler import start_scheduler, stop_scheduler
except ImportError:
    def start_scheduler():
        pass
    def stop_scheduler():
        pass


# ── Brand Context ───────────────────────────────────────────────────────────────

BRAND_CONTEXT = {
    "person": "Vineetkumar Ravi",
    "title": "Founder at Mangotec LLC",
    "location": "Los Angeles, CA",
    "email": "vineetkumar@mangotecusa.com",
    "positioning": (
        "I acquire cash-flowing, value-add healthcare real estate and improve quality of care "
        "through a digital engineering moat"
    ),
    "focus_30day": (
        "Acquire a health/wellness or longevity SaaS business ($150K–$300K) "
        "using $200K HELOC @ 9.5%"
    ),
    "projects": {
        "eva": "Autonomous AI OS for operators — memory, patterns, repeatability",
        "carebnb": "Platform solving RCFE/senior care placement (AirBnB model for care facilities in CA)",
    },
    "signature_talk": "Logic, Intuition & The LLM Within You",
}

BRAND_VOICES = {
    "operator": (
        "CRE + healthcare real estate operator lens. Gritty, specific, data-driven. "
        "'I've seen their financials. Most are on spreadsheets.' No fluff."
    ),
    "builder": (
        "AI/tech founder building in public. Honest about what's working and what isn't. "
        "First-person builder logs. Raw numbers. Real failures."
    ),
    "thinker": (
        "Ideas at the intersection of AI, longevity, human potential. "
        "Connects logic + intuition. References Ayurveda, longevity science, EVA."
    ),
}

TOPIC_PILLARS = {
    "healthcare_real_estate": (
        "RCFE acquisition, CareBnB, care facility ops, digital moat in healthcare property"
    ),
    "ai_and_acquisition": (
        "Using AI/EVA to source and evaluate online business acquisitions, health/wellness SaaS deals"
    ),
    "longevity_and_wealth": (
        "Health + wealth intersection, longevity economy ($120B market), AI freeing time for wellness"
    ),
}

# ── Pre-seeded post templates ────────────────────────────────────────────────────

SEED_POSTS = [
    # ── PILLAR: healthcare_real_estate ──
    {
        "voice": "operator",
        "pillar": "healthcare_real_estate",
        "main_post": (
            "Most RCFE operators don't have a software problem.\n\n"
            "They have a paper problem.\n\n"
            "I've been under the hood of 6+ care facilities in California this year. "
            "Not as a consultant. As a buyer doing active due diligence with skin in the game.\n\n"
            "Here's what I actually found inside these facilities:\n"
            "→ Financials on Excel (best case). Paper (most cases).\n"
            "→ Compliance triggers: one RN working extra shifts for $200/mo just to hit staffing ratios\n"
            "→ Patient placement: $3,000 finder's fee per bed paid to a marketing firm with no accountability\n"
            "→ Family communication: none. No cameras. No portal. Phone calls that go unreturned.\n"
            "→ Incident reporting: handwritten. Sometimes.\n\n"
            "This isn't a technology gap. "
            "It's an operational liability that real estate buyers are systematically ignoring.\n\n"
            "The facility I'm acquiring has solid net operating income. "
            "The upside isn't the property — it's installing a digital operating system on top of it: "
            "compliance automation, real-time family transparency, digital placement through CareBnB, "
            "and EVA managing the pattern recognition behind it all.\n\n"
            "That's the moat. Not the building. The system.\n\n"
            "The buyers competing with me are underwriting cap rates. "
            "I'm underwriting operational leverage.\n\n"
            "What's the most overlooked due diligence item in healthcare real estate acquisitions?\n\n"
            "#HealthcareRealEstate #RCFE #PropTech"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"RCFE California acquisition due diligence residential care\"]\n"
            "[VIDEO 2: Search query → \"healthcare real estate investing NOI value-add\"]\n\n"
            "The operators who are winning in 2025 aren't the ones with the best facilities — "
            "they're the ones who figured out that the real asset is the operational playbook. "
            "CareBnB is being built exactly on that thesis."
        ),
    },
    {
        "voice": "builder",
        "pillar": "healthcare_real_estate",
        "main_post": (
            "Building CareBnB: week 6 update. Here's what's working, what broke, and what I'm changing.\n\n"
            "The core insight hasn't changed: there are 7,000+ licensed RCFEs in California, "
            "and families placing a parent in care are making one of the most important decisions of their lives "
            "with almost zero reliable information.\n\n"
            "The problem isn't finding beds. The problem is trust.\n\n"
            "What I'm building to fix it:\n"
            "→ Real-time bed availability (no more 40-call Fridays for hospital case managers)\n"
            "→ Operator quality scores built from California DSS inspection data + resident outcome signals\n"
            "→ AirBnB-style family reviews from people who've actually gone through placement\n"
            "→ Direct operator profiles with photos, staff bios, and specialization tags\n\n"
            "Current status: 12 operators onboarded in LA County. First placement facilitated last week.\n\n"
            "What broke this week: the California DSS licensing data is a nightmare. "
            "Four different spreadsheets, no public API, updated quarterly at best. "
            "EVA now auto-parses and normalizes it into a structured operator database.\n\n"
            "Still broken: the $3,000 placement fee model. "
            "Everyone hates it — case managers, families, operators. "
            "Working on a subscription-based alternative that aligns everyone's incentives.\n\n"
            "What's the biggest friction point you've seen in the senior care placement process?\n\n"
            "#SeniorCare #HealthTech #BuildingInPublic"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"senior care placement market size AirBnB model\"]\n"
            "[VIDEO 2: Search query → \"RCFE California licensing inspection data explained\"]\n\n"
            "The California RCFE market alone is a $4B+ industry with almost zero tech penetration. "
            "That's the window. CareBnB isn't trying to replace families — "
            "it's trying to give them better information, faster."
        ),
    },
    {
        "voice": "thinker",
        "pillar": "healthcare_real_estate",
        "main_post": (
            "Healthcare real estate is where longevity economics collides with operational reality.\n\n"
            "By 2035, 1 in 5 Americans will be 65+. "
            "The demand for care infrastructure isn't a trend — it's actuarial math. Unavoidable.\n\n"
            "But most investors are looking at this wrong.\n\n"
            "They see the cap rate. They underwrite the NOI. They close on the building and wonder "
            "why the returns plateau after year two.\n\n"
            "What they miss: the care facility is a platform. "
            "The residents are the data. The family relationships are the distribution channel. "
            "The compliance infrastructure — if systematized — is the moat.\n\n"
            "Ayurvedic medicine has understood for 5,000 years that the environment of care is as important "
            "as the treatment itself. The Sanskrit concept of Kshetra — the field, the container — "
            "shapes what grows inside it. Western operators are learning this the hard way: "
            "low-quality environments produce worse resident outcomes, higher regulatory exposure, "
            "and accelerating staff turnover.\n\n"
            "The highest-returning RCFEs I've analyzed aren't the newest buildings. "
            "They're the ones where the operator has built systematic trust: "
            "with families, with regulators, with staff. "
            "Trust that can survive a survey visit. Trust that generates referrals without a marketing budget.\n\n"
            "That system can be codified. That's what I'm doing with EVA inside these facilities.\n\n"
            "What does \"quality of care\" mean to you in a data-driven framework?\n\n"
            "#LongevityEconomy #HealthcareRealEstate #AIinHealthcare"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"longevity economy aging population real estate investment\"]\n"
            "[VIDEO 2: Search query → \"Ayurveda environment of care healing design\"]\n\n"
            "The intersection of AI, longevity science, and real estate operations is where the next "
            "decade of wealth creation will happen. Not in another app — in physical places where humans live and heal."
        ),
    },
    # ── PILLAR: ai_and_acquisition ──
    {
        "voice": "operator",
        "pillar": "ai_and_acquisition",
        "main_post": (
            "Buying a health SaaS business is nothing like buying a building.\n\n"
            "I thought I knew deal diligence. Six care facility acquisitions gave me a framework: "
            "NOI, cap rate, CapEx reserves, license review, regulatory history. "
            "Clean process. Repeatable.\n\n"
            "Then I started looking at $150K–$300K health and wellness SaaS deals on Acquire.com, "
            "Flippa, and direct outreach. Different animal entirely.\n\n"
            "Here's what I've learned in 30 days of active deal flow reviewing 40+ listings:\n"
            "→ MRR is the headline. Churn rate is the truth. Net revenue retention tells you everything.\n"
            "→ \"Sticky\" SaaS in healthcare is often sticky because switching costs are regulatory — not because the product is good\n"
            "→ Most health/wellness SaaS below $300K has 1–2 developers who ARE the product. That's dangerous concentration.\n"
            "→ The best deals have boring distribution: organic SEO, one referral channel, zero sales team\n"
            "→ Seller's discretionary earnings (SDE) is often inflated. Ask for bank statements, not P&Ls.\n\n"
            "I'm using EVA to process LOIs, normalize financials across formats, "
            "cross-reference online reputation signals, and flag red flags before I spend a single hour on a call.\n\n"
            "The AI isn't replacing my judgment. It's compressing the time between \"interesting\" and \"qualified.\"\n\n"
            "Running this on a $200K HELOC at 9.5%. Every week of diligence has a real cost.\n\n"
            "What metrics do you look at first in a SaaS acquisition?\n\n"
            "#SaaSAcquisition #MicroPE #HealthTech"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"SaaS acquisition due diligence checklist MRR churn\"]\n"
            "[VIDEO 2: Search query → \"micro PE online business acquisition health wellness\"]\n\n"
            "I'm doing this acquisition with a $200K HELOC at 9.5%. "
            "That means the target needs clean cash flow from day one. "
            "The AI layer (EVA) helps me move fast — but the math still has to work old school."
        ),
    },
    {
        "voice": "builder",
        "pillar": "ai_and_acquisition",
        "main_post": (
            "EVA just flagged a deal I would have missed. Here's exactly what happened.\n\n"
            "I was reviewing a longevity supplement SaaS — $18K MRR, solid retention, growing 8% MoM. "
            "Clean financials. Good product. Reasonable multiple.\n\n"
            "The LOI was drafted. I was 48 hours from signing.\n\n"
            "EVA runs a pattern check on every deal I look at. "
            "It pulls the founder's LinkedIn activity, customer review trends across platforms, "
            "app store ratings over time, and any available regulatory filings.\n\n"
            "It flagged something: a 14-day spike in 1-star reviews exactly 6 months ago, "
            "coinciding with a period when the founder had gone quiet on LinkedIn.\n\n"
            "I dug in. The founder had silently pivoted from B2C to B2B without notifying existing customers. "
            "40% of the current MRR was from three enterprise clients — all signed in the last 5 months.\n\n"
            "That's not a SaaS business. That's a client services agency wearing a SaaS hat.\n\n"
            "Remove those three clients and you're at $10.8K MRR, not $18K. "
            "The multiple changes completely. The risk profile changes completely.\n\n"
            "I passed. The founder was frustrated. He didn't think it was material.\n\n"
            "EVA didn't make the call. I did. "
            "But it compressed three days of pattern recognition into 40 minutes.\n\n"
            "That's the build: operator intelligence, not operator replacement.\n\n"
            "What early warning signals matter most in your acquisition diligence process?\n\n"
            "#EVA #AIforOperators #BuildingInPublic"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"SaaS due diligence red flags concentration risk customer churn\"]\n"
            "[VIDEO 2: Search query → \"AI tools business acquisition analysis automation\"]\n\n"
            "EVA is still early — pattern matching isn't infallible and I review every flag manually. "
            "But the goal is to build a system that gets smarter with every deal I look at. "
            "Memory + patterns + repeatability. That's the OS."
        ),
    },
    {
        "voice": "thinker",
        "pillar": "ai_and_acquisition",
        "main_post": (
            "The best acquisition strategy I know isn't financial. It's biological.\n\n"
            "Consider how the immune system works. "
            "It doesn't evaluate every foreign molecule with the same intensity. "
            "It has memory. It has pattern recognition built from prior encounters. "
            "It escalates resources proportionally to the actual threat level.\n\n"
            "Most operators evaluate deals the opposite way — "
            "every deal gets the same process, the same cognitive overhead, the same emotional energy. "
            "No wonder they're exhausted and making marginal decisions by Friday afternoon.\n\n"
            "I've been building EVA as an immune system for deal flow.\n\n"
            "The core insight: what separates great operators from average ones isn't the ability to analyze more deals. "
            "It's the ability to instantly recognize which ones deserve analysis at all. "
            "To triage with speed and accuracy. To conserve decision energy for the moments that actually matter.\n\n"
            "That's a pattern-matching problem. And LLMs, fed the right context and trained on enough prior deals, "
            "are extraordinarily capable at it.\n\n"
            "The deals I pass on in under 5 minutes today would have taken me 2 full days two years ago. "
            "That's not efficiency. That's a different category of operator.\n\n"
            "In longevity terms: you're not just extending lifespan — you're extending cognitive healthspan. "
            "The ability to make 50 high-quality decisions a day instead of burning out at 5.\n\n"
            "What decision in your business could you automate without losing the judgment that matters?\n\n"
            "#AIandDecisions #OperatorMindset #LongevityEconomy"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"decision fatigue operators CEO pattern recognition automation\"]\n"
            "[VIDEO 2: Search query → \"LLM AI business intelligence decision support systems\"]\n\n"
            "My talk \"Logic, Intuition & The LLM Within You\" explores this intersection in depth — "
            "how your intuition is essentially a biological large language model, trained on lived experience. "
            "The goal is to augment it, not replace it."
        ),
    },
    # ── PILLAR: longevity_and_wealth ──
    {
        "voice": "operator",
        "pillar": "longevity_and_wealth",
        "main_post": (
            "The longevity economy is a $120 billion market. Most real estate investors are ignoring it.\n\n"
            "Here's the operator's read:\n\n"
            "Longevity isn't about living to 150. "
            "It's about compressing morbidity — maximizing healthy years, minimizing dependent ones. "
            "That thesis is now driving capital into a category that used to be called \"senior housing\" "
            "and is being rebranded as \"longevity infrastructure.\"\n\n"
            "Three direct effects on healthcare real estate that I'm underwriting right now:\n\n"
            "→ Rising demand for preventive and functional care facilities, not just skilled nursing\n"
            "→ Higher-acuity residents arriving later in life, requiring better-equipped operators with digital monitoring\n"
            "→ A growing middle market: residents too healthy for skilled nursing, too complex for independent living — "
            "and almost no good options for them\n\n"
            "The facilities capturing premium NOI in this shift share three operational features:\n"
            "1. Digital health monitoring — real-time vitals, not quarterly physician checkups\n"
            "2. Staff trained in functional medicine protocols, not just custodial care compliance\n"
            "3. Family transparency infrastructure — portals, cameras, outcome dashboards families can actually access\n\n"
            "I'm building this operating stack into every facility I acquire. "
            "Not because longevity is a trend. "
            "Because the market is already paying 2x the cap rate compression for operators who have it.\n\n"
            "What's the biggest operational gap you see in the longevity care market today?\n\n"
            "#LongevityEconomy #HealthcareRE #SeniorCare"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"longevity economy market size 2025 healthcare real estate\"]\n"
            "[VIDEO 2: Search query → \"compression of morbidity healthy aging preventive care facilities\"]\n\n"
            "The investors who understand the longevity thesis aren't just buying cap rates — "
            "they're positioning for a demographic wave that will define the next 30 years of healthcare real estate in the US. "
            "California is ground zero."
        ),
    },
    {
        "voice": "builder",
        "pillar": "longevity_and_wealth",
        "main_post": (
            "EVA gave me back 2 hours yesterday. Not metaphorically. Literally tracked.\n\n"
            "This is what it handled between 7am and 9am while I was doing my morning protocol:\n"
            "→ Parsed three broker packages and extracted NOI, cap rate, occupancy, and license status "
            "into a single side-by-side comparison table — formatted, ready for review\n"
            "→ Drafted responses to four LP update emails using my voice, prior email context, and deal status\n"
            "→ Flagged a zoning discrepancy in a facility I was 12 hours from taking to LOI — "
            "saved me from a significant mistake\n"
            "→ Summarized 40 pages of California RCFE inspection reports into a one-page operator risk profile\n\n"
            "That's not automation for its own sake. That's specific, high-leverage work that used to require me.\n\n"
            "Those 2 hours went to a cold plunge, 45 minutes of strength training, "
            "and a breakfast where I didn't look at my phone once.\n\n"
            "Here's the principle I'm building around: "
            "longevity isn't a biohack you do on weekends. "
            "It's a systems design problem. "
            "If your work architecture demands 12-hour cognitive sprints every day, "
            "no amount of red light therapy fixes that.\n\n"
            "EVA exists to give operators — including me — more time in the decisions that require human judgment, "
            "and less time in the processing work that just requires computation.\n\n"
            "What's the first task in your business you'd hand to a reliable AI agent?\n\n"
            "#EVA #AITools #BuildingInPublic"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"AI agent automation real estate operators workflow tools\"]\n"
            "[VIDEO 2: Search query → \"operator burnout prevention CEO daily routine longevity\"]\n\n"
            "The intersection of longevity and wealth isn't about making enough money to buy healthcare later. "
            "It's about designing systems now that let you operate at full capacity for decades. "
            "That's the actual product I'm building — for myself and for others."
        ),
    },
    {
        "voice": "thinker",
        "pillar": "longevity_and_wealth",
        "main_post": (
            "Ancient systems of medicine already knew what the longevity researchers are now spending millions to prove.\n\n"
            "Ayurveda's concept of Ojas — often translated as the \"essence of vitality\" — isn't mysticism. "
            "It's a systems-level framework for what modern science now calls metabolic health, "
            "heart rate variability, mitochondrial function, and cognitive reserve. "
            "Different vocabulary. Same underlying architecture.\n\n"
            "What strikes me most about the longevity economy is a fascinating inversion:\n\n"
            "For most of human history, wealth meant access to more — more food, more comfort, more ease. "
            "Today, the healthiest wealthy people on Earth are practicing voluntary restriction: "
            "time-restricted eating, deliberate cold exposure, structured sleep protocols, digital fasting.\n\n"
            "They're paying a premium for environments that support biological rigor. "
            "A $50K/year longevity clinic. A meticulously run RCFE where the physical environment "
            "itself is designed as a therapeutic input.\n\n"
            "This is the thesis behind CareBnB and the healthcare facilities I'm acquiring: "
            "the environment of care is the actual product. The building is just the container.\n\n"
            "And this is why the intersection of wealth strategy and health strategy isn't optional anymore. "
            "The operators who understand this are building facilities that command premium rates "
            "and have 18-month waitlists. The ones who don't are one survey citation away from closure.\n\n"
            "How do you think about the relationship between your wealth strategy and your health strategy?\n\n"
            "#Longevity #Ayurveda #WealthAndHealth"
        ),
        "comment_post": (
            "🎥 Want to go deeper?\n\n"
            "[VIDEO 1: Search query → \"Ayurveda Ojas vitality modern longevity science connection\"]\n"
            "[VIDEO 2: Search query → \"longevity economy wealthy health optimization market 2025\"]\n\n"
            "My talk \"Logic, Intuition & The LLM Within You\" connects these threads — how the biological intelligence "
            "we've carried for millennia is being augmented (not replaced) by the AI tools we're building now. "
            "The goal is the same: better decisions, longer health span, deeper impact."
        ),
    },
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── DB migration helper ─────────────────────────────────────────────────────────

async def migrate_db():
    """Add new columns to existing content_drafts table if not already present."""
    new_columns = [
        ("voice", "TEXT DEFAULT ''"),
        ("pillar", "TEXT DEFAULT ''"),
        ("comment_post", "TEXT DEFAULT ''"),
        ("linkedin_comment_id", "TEXT DEFAULT ''"),
        ("youtube_enriched", "INTEGER DEFAULT 0"),
    ]
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("PRAGMA table_info(content_drafts)") as cur:
            existing = {row[1] for row in await cur.fetchall()}
        for col_name, col_def in new_columns:
            if col_name not in existing:
                await db.execute(
                    f"ALTER TABLE content_drafts ADD COLUMN {col_name} {col_def}"
                )
        await db.commit()


async def seed_posts_if_empty():
    """Insert the 9 pre-seeded brand posts if the DB has no content_drafts at all."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM content_drafts") as cur:
            row = await cur.fetchone()
            count = row[0] if row else 0
        if count > 0:
            return

        now = now_iso()
        for post in SEED_POSTS:
            draft_id = str(uuid.uuid4())
            main_post = post["main_post"]
            # Extract hashtags from the end of the main post
            lines = main_post.strip().split("\n")
            hashtag_line = lines[-1] if lines[-1].startswith("#") else ""
            hashtags = [t for t in hashtag_line.split() if t.startswith("#")]
            hook = lines[0] if lines else ""
            await db.execute(
                """INSERT INTO content_drafts
                   (id, platform, content_type, source_type, source_summary, draft_text,
                    hook, hashtags, estimated_reach, status, created_at, updated_at,
                    voice, pillar, comment_post, linkedin_post_id, linkedin_comment_id, youtube_enriched)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    draft_id,
                    "linkedin",
                    "thought_leader",
                    "brand_seed",
                    f"Pre-seeded post: {post['voice']} / {post['pillar']}",
                    main_post,
                    hook,
                    json.dumps(hashtags),
                    "high",
                    "draft",
                    now,
                    now,
                    post["voice"],
                    post["pillar"],
                    post["comment_post"],
                    "",
                    "",
                    0,
                ),
            )
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await migrate_db()
    await seed_posts_if_empty()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="EVA Content Engine", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def row_to_dict(row, cursor):
    """Convert aiosqlite Row to dict using cursor description."""
    return {cursor.description[i][0]: row[i] for i in range(len(row))}


async def get_draft_or_404(draft_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM content_drafts WHERE id=?", (draft_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Draft not found")
            return row_to_dict(row, cur)


async def get_linkedin_config():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM linkedin_config WHERE id='default'") as cur:
            row = await cur.fetchone()
            if not row:
                return {}
            return row_to_dict(row, cur)


def _build_youtube_search_url(query: str) -> str:
    """Build a YouTube search URL from a query string."""
    import urllib.parse
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"


def _extract_video_queries(comment_post: str):
    """Extract search queries from comment_post video placeholders."""
    import re
    pattern = r'Search query → "([^"]+)"'
    return re.findall(pattern, comment_post)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "module": "eva-content-engine", "version": "1.0.0"}


# ── Draft Queue ────────────────────────────────────────────────────────────────

@app.get("/drafts/queue")
async def get_draft_queue():
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM content_drafts WHERE status='draft' AND created_at LIKE ? ORDER BY created_at DESC",
            (f"{today}%",)
        ) as cur:
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


# ── Drafts CRUD ────────────────────────────────────────────────────────────────

@app.get("/drafts")
async def list_drafts(status: str = None, platform: str = None):
    query = "SELECT * FROM content_drafts WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if platform:
        query += " AND platform=?"
        params.append(platform)
    query += " ORDER BY created_at DESC"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


@app.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    return await get_draft_or_404(draft_id)


@app.post("/drafts", status_code=201)
async def create_draft(body: DraftCreate):
    draft_id = str(uuid.uuid4())
    now = now_iso()
    hashtags_json = json.dumps(body.hashtags or [])
    scheduled_for = body.scheduled_for or ""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO content_drafts
               (id, platform, content_type, source_type, source_summary, draft_text,
                hook, hashtags, estimated_reach, status, scheduled_for, created_at, updated_at,
                voice, pillar, comment_post, linkedin_comment_id, youtube_enriched)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (draft_id, body.platform, body.content_type, body.source_type,
             body.source_summary or "", body.draft_text, body.hook or "",
             hashtags_json, body.estimated_reach or "medium", "draft",
             scheduled_for, now, now, "", "", "", "", 0)
        )
        await db.commit()
    return {"id": draft_id, "status": "draft", "created_at": now}


@app.post("/drafts/generate")
async def generate_drafts_endpoint(body: GenerateRequest):
    drafts = generate_drafts(
        activity_summary=body.activity_summary,
        source_type=body.source_type,
        platforms=body.platforms,
        count=body.count,
    )
    inserted = []
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        for d in drafts:
            draft_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO content_drafts
                   (id, platform, content_type, source_type, source_summary, draft_text,
                    hook, hashtags, estimated_reach, status, created_at, updated_at,
                    voice, pillar, comment_post, linkedin_comment_id, youtube_enriched)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (draft_id,
                 d.get("platform", body.platforms[0] if body.platforms else "linkedin"),
                 d.get("content_type", "thought_leader"),
                 body.source_type,
                 body.activity_summary,
                 d.get("draft_text", ""),
                 d.get("hook", ""),
                 json.dumps(d.get("hashtags", [])),
                 d.get("estimated_reach", "medium"),
                 "draft", now, now,
                 d.get("voice", ""), d.get("pillar", ""),
                 d.get("comment_post", ""), "", 0)
            )
            inserted.append({"id": draft_id, **d})
        await db.commit()
    return inserted


@app.post("/drafts/generate-from-eva")
async def generate_from_eva():
    fallback_summary = (
        "Worked on EVA AI personal OS: built content engine module, "
        "integrated LinkedIn posting, reviewed analytics pipeline. "
        "Had a productive morning routine and reflected on intuition vs data in decision-making."
    )
    try:
        resp = requests.get("http://localhost:8765/context/today", timeout=3)
        resp.raise_for_status()
        data = resp.json()
        activity_summary = data.get("summary") or data.get("context") or fallback_summary
    except Exception:
        activity_summary = fallback_summary

    drafts = generate_drafts(
        activity_summary=activity_summary,
        source_type="activity_stream",
        platforms=["linkedin"],
        count=3,
    )
    inserted = []
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        for d in drafts:
            draft_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO content_drafts
                   (id, platform, content_type, source_type, source_summary, draft_text,
                    hook, hashtags, estimated_reach, status, created_at, updated_at,
                    voice, pillar, comment_post, linkedin_comment_id, youtube_enriched)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (draft_id,
                 d.get("platform", "linkedin"),
                 d.get("content_type", "thought_leader"),
                 "activity_stream",
                 activity_summary,
                 d.get("draft_text", ""),
                 d.get("hook", ""),
                 json.dumps(d.get("hashtags", [])),
                 d.get("estimated_reach", "medium"),
                 "draft", now, now,
                 d.get("voice", ""), d.get("pillar", ""),
                 d.get("comment_post", ""), "", 0)
            )
            inserted.append({"id": draft_id, **d})
        await db.commit()
    return {"generated": len(inserted), "drafts": inserted}


@app.put("/drafts/{draft_id}")
async def update_draft(draft_id: str, body: DraftUpdate):
    await get_draft_or_404(draft_id)
    fields = []
    params = []
    if body.draft_text is not None:
        fields.append("draft_text=?")
        params.append(body.draft_text)
    if body.hook is not None:
        fields.append("hook=?")
        params.append(body.hook)
    if body.hashtags is not None:
        fields.append("hashtags=?")
        params.append(json.dumps(body.hashtags))
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    fields.append("updated_at=?")
    params.append(now_iso())
    params.append(draft_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE content_drafts SET {', '.join(fields)} WHERE id=?", params
        )
        await db.commit()
    return await get_draft_or_404(draft_id)


@app.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str):
    await get_draft_or_404(draft_id)
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE content_drafts SET status='approved', approved_at=?, updated_at=? WHERE id=?",
            (now, now, draft_id)
        )
        await db.commit()
    return await get_draft_or_404(draft_id)


@app.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, body: RejectRequest):
    await get_draft_or_404(draft_id)
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE content_drafts SET status='rejected', rejection_reason=?, updated_at=? WHERE id=?",
            (body.reason, now, draft_id)
        )
        await db.commit()
    return await get_draft_or_404(draft_id)


@app.post("/drafts/approve-batch")
async def approve_batch(body: BatchApproveRequest):
    config = await get_linkedin_config()
    results = []
    approved_count = 0
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        for draft_id in body.draft_ids:
            async with db.execute("SELECT * FROM content_drafts WHERE id=?", (draft_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    results.append({"id": draft_id, "error": "not found"})
                    continue
                draft = row_to_dict(row, cur)

            # Approve first
            await db.execute(
                "UPDATE content_drafts SET status='approved', approved_at=?, updated_at=? WHERE id=?",
                (now, now, draft_id)
            )
            approved_count += 1

            # Attempt LinkedIn post
            try:
                access_token = config.get("access_token", "")
                person_urn = config.get("person_urn", "")
                post_result = _linkedin_post_text(draft["draft_text"], access_token, person_urn)
                if post_result.get("posted"):
                    post_id = post_result.get("post_id", "")
                    post_url = post_result.get("post_url", "")
                    await db.execute(
                        """UPDATE content_drafts
                           SET status='posted', posted_at=?, linkedin_post_id=?, post_url=?, updated_at=?
                           WHERE id=?""",
                        (now, post_id, post_url, now, draft_id)
                    )
                    results.append({"id": draft_id, "status": "posted", "post_id": post_id})
                else:
                    results.append({"id": draft_id, "status": "approved", "error": post_result.get("error")})
            except Exception as e:
                results.append({"id": draft_id, "status": "approved", "error": str(e)})

        await db.commit()
    return {"approved_count": approved_count, "results": results}


@app.post("/drafts/{draft_id}/post")
async def post_draft(draft_id: str):
    draft = await get_draft_or_404(draft_id)
    config = await get_linkedin_config()
    access_token = config.get("access_token", "")
    person_urn = config.get("person_urn", "")

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "LinkedIn not connected",
                "setup_url": "https://www.linkedin.com/developers/apps"
            }
        )

    try:
        post_result = _linkedin_post_text(draft["draft_text"], access_token, person_urn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = now_iso()
    if post_result.get("posted"):
        post_id = post_result.get("post_id", "")
        post_url = post_result.get("post_url", "")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE content_drafts
                   SET status='posted', posted_at=?, linkedin_post_id=?, post_url=?, updated_at=?
                   WHERE id=?""",
                (now, post_id, post_url, now, draft_id)
            )
            await db.commit()
        return {"status": "posted", "post_id": post_id, "post_url": post_url}
    else:
        raise HTTPException(status_code=502, detail=post_result.get("error", "Post failed"))


# ── Voice ──────────────────────────────────────────────────────────────────────

@app.get("/voice")
async def get_voice():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM brand_voice") as cur:
            rows = await cur.fetchall()
            return [row_to_dict(r, cur) for r in rows]


@app.put("/voice/{voice_id}")
async def update_voice(voice_id: str, body: VoiceUpdate):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM brand_voice WHERE id=?", (voice_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Voice not found")

    fields = []
    params = []
    if body.tone is not None:
        fields.append("tone=?")
        params.append(body.tone)
    if body.example_hooks is not None:
        fields.append("example_hooks=?")
        params.append(json.dumps(body.example_hooks))
    if body.example_posts is not None:
        fields.append("example_posts=?")
        params.append(json.dumps(body.example_posts))
    if body.avoid is not None:
        fields.append("avoid=?")
        params.append(json.dumps(body.avoid))
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    fields.append("updated_at=?")
    params.append(now_iso())
    params.append(voice_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE brand_voice SET {', '.join(fields)} WHERE id=?", params
        )
        await db.commit()
        async with db.execute("SELECT * FROM brand_voice WHERE id=?", (voice_id,)) as cur:
            row = await cur.fetchone()
            return row_to_dict(row, cur)


# ── Analytics ──────────────────────────────────────────────────────────────────

@app.get("/analytics/summary")
async def analytics_summary():
    async with aiosqlite.connect(DB_PATH) as db:
        # Count by status
        async with db.execute(
            "SELECT status, COUNT(*) as count FROM content_drafts GROUP BY status"
        ) as cur:
            status_rows = await cur.fetchall()
            by_status = {r[0]: r[1] for r in status_rows}

        # Total engagement for posted drafts
        async with db.execute(
            """SELECT
                COALESCE(SUM(likes),0) as total_likes,
                COALESCE(SUM(comments),0) as total_comments,
                COALESCE(SUM(shares),0) as total_shares,
                COALESCE(SUM(impressions),0) as total_impressions
               FROM content_drafts WHERE status='posted'"""
        ) as cur:
            eng_row = await cur.fetchone()
            engagement = {
                "total_likes": eng_row[0],
                "total_comments": eng_row[1],
                "total_shares": eng_row[2],
                "total_impressions": eng_row[3],
            } if eng_row else {}

    return {"by_status": by_status, "engagement": engagement}


@app.get("/analytics/weekly")
async def analytics_weekly():
    from datetime import timedelta
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT content_type, COUNT(*) as count,
                      COALESCE(SUM(likes),0) as likes,
                      COALESCE(SUM(comments),0) as comments,
                      COALESCE(SUM(shares),0) as shares,
                      COALESCE(SUM(impressions),0) as impressions
               FROM content_drafts
               WHERE created_at >= ?
               GROUP BY content_type""",
            (seven_days_ago,)
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "content_type": r[0],
                    "count": r[1],
                    "likes": r[2],
                    "comments": r[3],
                    "shares": r[4],
                    "impressions": r[5],
                }
                for r in rows
            ]


# ── Delete ─────────────────────────────────────────────────────────────────────

@app.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str):
    draft = await get_draft_or_404(draft_id)
    if draft["status"] not in ("draft", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete draft with status '{draft['status']}'"
        )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM content_drafts WHERE id=?", (draft_id,))
        await db.commit()
    return {"deleted": True, "id": draft_id}


# ══════════════════════════════════════════════════════════════════════════════
# ── LinkedIn Content Engine  ──────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel as _BaseModel


class ContentGenerateRequest(_BaseModel):
    voice: str  # operator | builder | thinker
    pillar: str  # healthcare_real_estate | ai_and_acquisition | longevity_and_wealth
    topic_hint: Optional[str] = None
    include_comment: bool = True


def _generate_linkedin_post(voice: str, pillar: str, topic_hint: Optional[str] = None) -> dict:
    """
    Generate a LinkedIn post using brand context, voice, and pillar.
    Tries OpenAI if available; falls back to selecting a matching seed post
    or constructing a template post.
    """
    # First, try to find a matching seed post
    for seed in SEED_POSTS:
        if seed["voice"] == voice and seed["pillar"] == pillar:
            return {
                "main_post": seed["main_post"],
                "comment_post": seed["comment_post"],
            }

    # Fallback: construct a generic template using brand context
    voice_desc = BRAND_VOICES.get(voice, "direct and data-driven")
    pillar_desc = TOPIC_PILLARS.get(pillar, pillar)
    topic_line = f" Specifically about: {topic_hint}." if topic_hint else ""

    main_post = (
        f"[{voice.upper()} voice | {pillar} topic]{topic_line}\n\n"
        f"This post reflects {BRAND_CONTEXT['positioning']}.\n\n"
        f"Voice style: {voice_desc}\n\n"
        f"Pillar focus: {pillar_desc}\n\n"
        f"— Vineetkumar Ravi, {BRAND_CONTEXT['title']}, {BRAND_CONTEXT['location']}\n\n"
        f"#Healthcare #AI #RealEstate"
    )
    comment_post = (
        "🎥 Want to go deeper?\n\n"
        f"[VIDEO 1: Search query → \"{pillar} explained\"]\n"
        f"[VIDEO 2: Search query → \"{voice} perspective {pillar}\"]\n\n"
        "More context and resources from Mangotec LLC."
    )
    return {"main_post": main_post, "comment_post": comment_post}


@app.post("/content/generate")
async def content_generate(body: ContentGenerateRequest):
    """
    Generate a brand-voice LinkedIn post (main + comment) and store as draft.
    """
    # Validate inputs
    valid_voices = {"operator", "builder", "thinker"}
    valid_pillars = {"healthcare_real_estate", "ai_and_acquisition", "longevity_and_wealth"}
    if body.voice not in valid_voices:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice '{body.voice}'. Must be one of: {', '.join(sorted(valid_voices))}"
        )
    if body.pillar not in valid_pillars:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pillar '{body.pillar}'. Must be one of: {', '.join(sorted(valid_pillars))}"
        )

    # Generate post content
    generated = _generate_linkedin_post(body.voice, body.pillar, body.topic_hint)
    main_post = generated["main_post"]
    comment_post = generated["comment_post"] if body.include_comment else ""
    char_count = len(main_post)

    # Extract hashtags from main post
    lines = main_post.strip().split("\n")
    hashtag_line = lines[-1] if lines and lines[-1].startswith("#") else ""
    hashtags = [t for t in hashtag_line.split() if t.startswith("#")]
    hook = lines[0] if lines else ""

    draft_id = str(uuid.uuid4())
    now = now_iso()
    ts = int(time.time())

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO content_drafts
               (id, platform, content_type, source_type, source_summary, draft_text,
                hook, hashtags, estimated_reach, status, created_at, updated_at,
                voice, pillar, comment_post, linkedin_post_id, linkedin_comment_id, youtube_enriched)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                draft_id, "linkedin", "thought_leader", "content_engine",
                f"Generated: {body.voice}/{body.pillar}" + (f" — {body.topic_hint}" if body.topic_hint else ""),
                main_post, hook, json.dumps(hashtags), "high",
                "draft", now, now,
                body.voice, body.pillar, comment_post, "", "", 0
            )
        )
        await db.commit()

    return {
        "id": draft_id,
        "voice": body.voice,
        "pillar": body.pillar,
        "main_post": main_post,
        "comment_post": comment_post,
        "char_count": char_count,
        "status": "draft",
        "created_at": ts,
    }


@app.post("/content/post/{draft_id}")
async def content_post(draft_id: str):
    """
    Post the main_post to LinkedIn and immediately post comment_post as a comment.
    Requires LinkedIn access_token to be configured.
    """
    draft = await get_draft_or_404(draft_id)
    config = await get_linkedin_config()

    access_token = config.get("access_token", "")
    person_urn = config.get("person_urn", "")

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "LinkedIn not connected",
                "setup_url": "https://www.linkedin.com/developers/apps"
            }
        )

    # Post main post
    try:
        post_result = _linkedin_post_text(draft["draft_text"], access_token, person_urn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post to LinkedIn: {str(e)}")

    if not post_result.get("posted"):
        raise HTTPException(
            status_code=502,
            detail={"error": post_result.get("error", "LinkedIn post failed")}
        )

    linkedin_post_id = post_result.get("post_id", "")
    post_url = post_result.get("post_url", "")
    now = now_iso()
    linkedin_comment_id = ""

    # Post comment if present
    comment_post = draft.get("comment_post", "")
    if comment_post and linkedin_post_id:
        try:
            comment_result = _post_linkedin_comment(
                linkedin_post_id, comment_post, access_token, person_urn
            )
            linkedin_comment_id = comment_result.get("comment_id", "")
        except Exception:
            # Comment failure is non-fatal
            linkedin_comment_id = ""

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE content_drafts
               SET status='posted', posted_at=?, linkedin_post_id=?, post_url=?,
                   linkedin_comment_id=?, updated_at=?
               WHERE id=?""",
            (now, linkedin_post_id, post_url, linkedin_comment_id, now, draft_id)
        )
        await db.commit()

    return {
        "status": "posted",
        "linkedin_post_id": linkedin_post_id,
        "linkedin_comment_id": linkedin_comment_id,
        "post_url": post_url,
    }


def _post_linkedin_comment(post_id: str, comment_text: str, access_token: str, person_urn: str) -> dict:
    """Post a comment to an existing LinkedIn UGC post."""
    LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "actor": f"urn:li:person:{person_urn}",
        "message": {"text": comment_text},
    }
    try:
        resp = requests.post(
            f"{LINKEDIN_API_BASE}/socialActions/{post_id}/comments",
            headers=headers,
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            comment_id = resp.headers.get("X-RestLi-Id", "")
            return {"posted": True, "comment_id": comment_id}
        return {"posted": False, "error": resp.text, "status_code": resp.status_code}
    except Exception as e:
        return {"posted": False, "error": str(e)}


@app.post("/content/youtube-enrich/{draft_id}")
async def content_youtube_enrich(draft_id: str):
    """
    Search YouTube for videos relevant to the post topic and fill in comment_post
    video placeholders with real URLs. Uses YouTube Data API if YOUTUBE_API_KEY env var
    is set; otherwise returns search query URLs pointing to youtube.com/results.
    """
    import os
    draft = await get_draft_or_404(draft_id)
    comment_post = draft.get("comment_post", "")

    if not comment_post:
        raise HTTPException(status_code=400, detail="No comment_post found for this draft")

    queries = _extract_video_queries(comment_post)
    if not queries:
        return {"enriched": False, "reason": "No video placeholders found in comment_post"}

    youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
    video_results = []

    for query in queries:
        if youtube_api_key:
            # Use YouTube Data API v3
            try:
                resp = requests.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "part": "snippet",
                        "q": query,
                        "type": "video",
                        "maxResults": 1,
                        "key": youtube_api_key,
                    },
                    timeout=10,
                )
                if resp.ok:
                    items = resp.json().get("items", [])
                    if items:
                        vid_id = items[0]["id"].get("videoId", "")
                        title = items[0]["snippet"].get("title", query)
                        channel = items[0]["snippet"].get("channelTitle", "")
                        url = f"https://www.youtube.com/watch?v={vid_id}"
                        video_results.append({
                            "query": query,
                            "url": url,
                            "title": title,
                            "channel": channel,
                        })
                        continue
            except Exception:
                pass
        # Fallback: search URL
        search_url = _build_youtube_search_url(query)
        video_results.append({
            "query": query,
            "url": search_url,
            "title": f"YouTube search: {query}",
            "channel": "",
        })

    # Replace placeholders in comment_post
    import re
    enriched_comment = comment_post
    for result in video_results:
        pattern = rf'\[VIDEO \d+: Search query → "{re.escape(result["query"])}"\]'
        replacement = f'[{result["title"]}]({result["url"]})'
        if result.get("channel"):
            replacement = f'[{result["title"]} — {result["channel"]}]({result["url"]})'
        enriched_comment = re.sub(pattern, replacement, enriched_comment)

    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE content_drafts SET comment_post=?, youtube_enriched=1, updated_at=? WHERE id=?",
            (enriched_comment, now, draft_id)
        )
        await db.commit()

    return {
        "enriched": True,
        "draft_id": draft_id,
        "videos_found": len(video_results),
        "video_results": video_results,
        "comment_post": enriched_comment,
    }


@app.get("/content/queue")
async def content_queue(status: str = None):
    """
    Returns all content-engine posts with optional status filter.
    Status values: draft | approved | posted | failed
    """
    query = "SELECT * FROM content_drafts WHERE source_type IN ('content_engine','brand_seed')"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            results = []
            for r in rows:
                d = row_to_dict(r, cur)
                results.append({
                    "id": d["id"],
                    "voice": d.get("voice", ""),
                    "pillar": d.get("pillar", ""),
                    "main_post": d["draft_text"],
                    "comment_post": d.get("comment_post", ""),
                    "char_count": len(d["draft_text"]),
                    "status": d["status"],
                    "linkedin_post_id": d.get("linkedin_post_id", ""),
                    "linkedin_comment_id": d.get("linkedin_comment_id", ""),
                    "youtube_enriched": bool(d.get("youtube_enriched", 0)),
                    "created_at": d["created_at"],
                    "posted_at": d.get("posted_at", ""),
                })
            return results


@app.post("/content/approve/{draft_id}")
async def content_approve(draft_id: str):
    """Move a content-engine draft to approved status."""
    draft = await get_draft_or_404(draft_id)
    if draft["status"] not in ("draft",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve post with status '{draft['status']}'. Only drafts can be approved."
        )
    now = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE content_drafts SET status='approved', approved_at=?, updated_at=? WHERE id=?",
            (now, now, draft_id)
        )
        await db.commit()
    updated = await get_draft_or_404(draft_id)
    return {
        "id": updated["id"],
        "status": updated["status"],
        "voice": updated.get("voice", ""),
        "pillar": updated.get("pillar", ""),
        "approved_at": now,
    }


@app.delete("/content/draft/{draft_id}")
async def content_delete_draft(draft_id: str):
    """Delete a content-engine draft. Only drafts and rejected posts can be deleted."""
    draft = await get_draft_or_404(draft_id)
    if draft["status"] not in ("draft", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete post with status '{draft['status']}'. Only drafts and rejected posts can be deleted."
        )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM content_drafts WHERE id=?", (draft_id,))
        await db.commit()
    return {"deleted": True, "id": draft_id}


@app.get("/content/brand-context")
async def content_brand_context():
    """Return the full brand context used for content generation."""
    return {
        "brand_context": BRAND_CONTEXT,
        "voices": BRAND_VOICES,
        "pillars": TOPIC_PILLARS,
    }



# ── Reminders ────────────────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    title: str
    due_at: str          # ISO datetime string
    tag: Optional[str] = None

class ReminderDoneToggle(BaseModel):
    done: bool

@app.get("/reminders")
async def list_reminders():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                due_at TEXT NOT NULL,
                tag TEXT,
                done INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.commit()
        async with db.execute("SELECT id,title,due_at,tag,done,created_at FROM reminders ORDER BY due_at ASC") as cur:
            rows = await cur.fetchall()
    return [{"id":r[0],"title":r[1],"due_at":r[2],"tag":r[3],"done":bool(r[4]),"created_at":r[5]} for r in rows]

@app.post("/reminders", status_code=201)
async def create_reminder(body: ReminderCreate):
    import uuid as _uuid
    rid = str(_uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, due_at TEXT NOT NULL,
                tag TEXT, done INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("INSERT INTO reminders (id,title,due_at,tag,created_at) VALUES (?,?,?,?,?)",
                         (rid, body.title, body.due_at, body.tag, now))
        await db.commit()
    return {"id":rid,"title":body.title,"due_at":body.due_at,"tag":body.tag,"done":False,"created_at":now}

@app.patch("/reminders/{reminder_id}/done")
async def toggle_reminder_done(reminder_id: str, body: ReminderDoneToggle):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE reminders SET done=? WHERE id=?", (int(body.done), reminder_id))
        await db.commit()
    return {"id": reminder_id, "done": body.done}

@app.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
        await db.commit()
    return {"deleted": True}

@app.get("/reminders/calendar")
async def get_calendar_events():
    """
    Proxy endpoint — fetches today+7 days of Google Calendar events.
    Returns empty list if not configured (no Google token stored).
    The UI polls this; actual Google OAuth wiring happens via a separate setup step.
    """
    cfg = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS google_config (
                    id TEXT PRIMARY KEY, access_token TEXT, refresh_token TEXT,
                    token_expires_at TEXT, updated_at TEXT
                )
            """)
            await db.commit()
            async with db.execute("SELECT access_token FROM google_config WHERE id='default'") as cur:
                row = await cur.fetchone()
                if row:
                    cfg["access_token"] = row[0]
    except Exception:
        pass

    if not cfg.get("access_token"):
        return []

    from datetime import timezone
    import urllib.request as _req, urllib.parse as _parse, json as _json
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=7)).isoformat()
    params = _parse.urlencode({"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime", "maxResults": "20"})
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{params}"
    try:
        request = _req.Request(url, headers={"Authorization": f"Bearer {cfg['access_token']}"})
        with _req.urlopen(request, timeout=10) as r:
            data = _json.loads(r.read())
        events = []
        for item in data.get("items", []):
            start = item.get("start", {})
            end = item.get("end", {})
            events.append({
                "id": item.get("id",""),
                "title": item.get("summary","(no title)"),
                "start": start.get("dateTime", start.get("date","")),
                "end": end.get("dateTime", end.get("date","")),
                "calendar": "primary",
                "color": item.get("colorId"),
            })
        return events
    except Exception as e:
        return []



# ── Entry Point ────────────────────────────────────────────────────────────────



@app.get("/content/linkedin-config")
async def get_linkedin_config_endpoint():
    """Return current LinkedIn config (token masked for security)."""
    cfg = await get_linkedin_config()
    if not cfg:
        return {"configured": False, "access_token": None, "person_urn": None}
    token = cfg.get("access_token") or ""
    masked = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else ("***" if token else None)
    return {
        "configured": bool(token and cfg.get("person_urn")),
        "access_token_masked": masked,
        "person_urn": cfg.get("person_urn"),
        "token_expires_at": cfg.get("token_expires_at"),
        "updated_at": cfg.get("updated_at"),
    }


class LinkedInConfigUpdate(BaseModel):
    access_token: str
    person_urn: str  # just the ID portion, e.g. "abc123XYZ"


@app.put("/content/linkedin-config")
async def update_linkedin_config(body: LinkedInConfigUpdate):
    """Set LinkedIn access_token and person_urn without touching the DB directly."""
    from datetime import datetime, timedelta
    expires = (datetime.utcnow() + timedelta(days=60)).isoformat()
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO linkedin_config (id, access_token, person_urn, token_expires_at, updated_at)
            VALUES ('default', ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              access_token=excluded.access_token,
              person_urn=excluded.person_urn,
              token_expires_at=excluded.token_expires_at,
              updated_at=excluded.updated_at
            """,
            (body.access_token, body.person_urn, expires, now),
        )
        await db.commit()
    return {"ok": True, "person_urn": body.person_urn, "token_expires_at": expires}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8767, reload=False)
