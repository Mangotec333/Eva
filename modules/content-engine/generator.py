import uuid
import json
import random
import os
from datetime import datetime, timezone

# ── Voice DNA ─────────────────────────────────────────────────────────────────
try:
    from voice_dna import VOICE_SYSTEM_PROMPT, VOICE_EXAMPLES, check_banned_words
    VOICE_DNA_LOADED = True
except ImportError:
    VOICE_DNA_LOADED = False
    VOICE_SYSTEM_PROMPT = ""
    VOICE_EXAMPLES = []
    def check_banned_words(text): return []

# 5 template families, each with multiple hook variants
TEMPLATES = [
    {
        "key": "llm_intuition",
        "content_type": "thought_leader",
        "hooks": [
            "Your intuition is an LLM. And most men are starving it of training data.",
            "I reverse-engineered human intuition using AI principles. Here's what I found.",
            "The reason logical men make poor life decisions (it's not what you think).",
            "What if watching movies and traveling is actually optimizing your decision-making?",
        ],
        "body": "LLMs get better with more training data.\n\nYour intuition works the same way.\n\nEvery experience — sports, travel, books, deep conversations, failures, wins — is a training run for your inner model.\n\nThe problem: most high-achieving men optimize for efficiency. They cut anything without measurable ROI.\n\nResult: massive logical processing power. Undertrained intuitive model.\n\nThe fix isn't to stop being logical.\nIt's to feed your intuitive model the data it needs.\n\n{insight}\n\nLogic runs the analysis. Intuition makes the call.",
        "cta": "What experience has given your intuition the most 'training data'?",
        "hashtags": ["#AI", "#Intuition", "#DecisionMaking", "#Leadership", "#Founders"],
        "reach": "high"
    },
    {
        "key": "builder_log",
        "content_type": "builder_log",
        "hooks": [
            "What I built this week (and what broke):",
            "EVA update — here's what the AI learned about me:",
            "Real numbers. Real builds. No vanity metrics.",
            "Building in public: the unglamorous version.",
        ],
        "body": "This week: {summary}\n\nWhat I learned:\n→ The scoring framework only works if you're honest about what you're optimizing for\n→ Speed of decision matters less than quality of the decision-making system\n\nThe part nobody talks about: I spent 2 hours on analysis I could have done in 20 minutes if I trusted the first signal.\n\nEVA (my personal AI OS) is teaching me more about my own patterns than any coach ever did.",
        "cta": "What pattern are you trying to break right now?",
        "hashtags": ["#BuildingInPublic", "#AI", "#Founder", "#Automation", "#EVA"],
        "reach": "medium"
    },
    {
        "key": "human_story",
        "content_type": "human_story",
        "hooks": [
            "My wife made a decision that made no logical sense. She was completely right.",
            "I almost passed on this because the numbers said no.",
            "The moment I realized logic alone was costing me more than it saved.",
            "What my morning ritual taught me about the gap between knowing and doing.",
        ],
        "body": "My wife is deeply intuitive. I'm deeply logical.\n\nFor years I'd run the numbers on her 'illogical' decisions and prove they wouldn't work.\n\nShe'd proceed anyway. She kept being right.\n\nSo I did what any engineer would do: I tried to reverse-engineer her process.\n\nWhat I found: she wasn't being illogical. She was processing data I wasn't collecting.\n\n{insight}\n\nThat's why I'm building EVA — an AI that learns my patterns the way she learned to trust hers.",
        "cta": "Have you ever made a decision that didn't add up on paper but turned out right?",
        "hashtags": ["#Intuition", "#PersonalGrowth", "#AI", "#Leadership", "#Founder"],
        "reach": "high"
    },
    {
        "key": "deal_flow",
        "content_type": "thought_leader",
        "hooks": [
            "Real deal flow. Real numbers. No filter.",
            "I'm acquiring a cash-flowing online business with a HELOC. Here's my scorecard.",
            "How I evaluate a $200K business acquisition in under 2 hours.",
            "The metric most acquisition buyers miss: AI-proof score.",
        ],
        "body": "Acquisition update: {summary}\n\nMy scoring framework (0-100 each):\n→ Cash flow: clears debt service AND hits $10K/mo take-home?\n→ MOAT depth: how hard is this to replicate from scratch?\n→ AI-proof score: 12+ months before AI disrupts it?\n→ Buy vs Build: would building take longer than the payback period?\n→ Value-add: what can I add with EVA/AI that the current owner can't?\n\nThe one that surprised me: the 13-year-old plugin had the strongest moat but the weakest value-add upside.",
        "cta": "Would you want me to share the full scoring framework as a template?",
        "hashtags": ["#Acquisition", "#OnlineBusiness", "#CashFlow", "#Entrepreneur", "#AI"],
        "reach": "high"
    },
    {
        "key": "pattern_interrupt",
        "content_type": "builder_log",
        "hooks": [
            "EVA flagged something about my week I didn't want to see.",
            "My AI caught a pattern I'd been rationalizing for months.",
            "The hardest part of building a system that watches your behavior: it tells the truth.",
            "3 consecutive days of reactive work. EVA noticed before I did.",
        ],
        "body": "I built EVA to track my activity patterns.\n\nThis week it flagged: {summary}\n\nI was spending time on low-leverage work when my highest-value hours were available.\n\nThe insight: awareness alone changes behavior. You don't need willpower if you have visibility.\n\nThis is why the pattern engine is the most important module I'm building — not the voice interface, not the deal tracker. The thing that interrupts patterns that no longer serve you.",
        "cta": "What would you want an AI to flag about your week?",
        "hashtags": ["#AI", "#Productivity", "#Patterns", "#BuildingInPublic", "#EVA"],
        "reach": "medium"
    },
]

def _pick_insight(activity_summary: str) -> str:
    insights = [
        f"Applied this directly this week: {activity_summary[:80]}",
        "The data backed the intuition up. It usually does — if you collect the right data.",
        "This showed up in my acquisition analysis this week in an unexpected way.",
        "Building EVA made this concrete. Watching my own patterns is humbling.",
    ]
    return random.choice(insights)

def generate_with_llm(activity_summary: str, content_type: str, platform: str) -> str | None:
    """
    Use Claude/Anthropic to generate a post in Vineet's voice DNA.
    Falls back to template if API key not available.
    """
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)

        # Build few-shot examples string
        examples_str = ""
        for ex in VOICE_EXAMPLES:
            examples_str += f"\n\nContext: {ex['context']}\nPost:\n{ex['post']}\n---"

        user_prompt = (
            f"Write a {platform} post for Vineet in his exact voice DNA.\n\n"
            f"Content type: {content_type}\n"
            f"Based on this week's activity: {activity_summary[:400]}\n\n"
            f"Voice examples to match:{examples_str}\n\n"
            f"Write only the post text. No explanations. No meta-commentary."
        )

        msg = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=600,
            system=VOICE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = msg.content[0].text.strip()

        # Check for banned words — regenerate once if found
        banned = check_banned_words(text)
        if banned:
            user_prompt += f"\n\nIMPORTANT: Remove these words — they are NOT in Vineet's voice: {', '.join(banned)}"
            msg2 = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=600,
                system=VOICE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = msg2.content[0].text.strip()

        return text

    except Exception as e:
        print(f"[voice_dna] LLM generation failed: {e} — falling back to template")
        return None


def generate_drafts(activity_summary: str, platforms: list, count: int, source_type: str) -> list:
    now = datetime.now(timezone.utc).isoformat()
    pool = TEMPLATES.copy()
    random.shuffle(pool)
    selected = pool[:min(count, len(pool))]
    drafts = []
    for tmpl in selected:
        platform = platforms[0] if platforms else "linkedin"

        # Try Voice DNA LLM generation first
        llm_text = None
        if VOICE_DNA_LOADED:
            llm_text = generate_with_llm(activity_summary, tmpl["content_type"], platform)

        if llm_text:
            full_text = llm_text
            hook = llm_text.split("\n")[0]  # first line as hook for logging
        else:
            # Template fallback
            hook = random.choice(tmpl["hooks"])
            insight = _pick_insight(activity_summary)
            summary_short = activity_summary[:120] if activity_summary else "EVA system active"
            try:
                body = tmpl["body"].format(insight=insight, summary=summary_short)
            except KeyError:
                body = tmpl["body"].replace("{insight}", insight).replace("{summary}", summary_short)
            full_text = f"{hook}\n\n{body}\n\n{tmpl['cta']}"
        drafts.append({
            "id": str(uuid.uuid4()),
            "platform": platforms[0] if platforms else "linkedin",
            "content_type": tmpl["content_type"],
            "source_type": source_type,
            "source_summary": activity_summary[:300],
            "draft_text": full_text,
            "hook": hook,
            "hashtags": json.dumps(tmpl["hashtags"]),
            "estimated_reach": tmpl["reach"],
            "status": "draft",
            "rejection_reason": "",
            "approved_at": "", "posted_at": "", "post_url": "",
            "linkedin_post_id": "",
            "likes": 0, "comments": 0, "shares": 0, "impressions": 0,
            "performance_fetched_at": "", "scheduled_for": "",
            "created_at": now, "updated_at": now,
        })
    return drafts
