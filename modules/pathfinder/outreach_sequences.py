"""
EVA Pathfinder — Outreach Sequences & DM Templates
Maps lead scoring sequences to DM templates and follow-up cadence.
DM templates sourced from: linkedin_dealscout_dms.md (Vineet Ravi / Storeys)
"""

# ── DM Templates ──────────────────────────────────────────────────────────────
# Keys are 1-indexed to match the source document naming (DM 1 … DM 10)

DM_TEMPLATES: dict[int, dict] = {
    1: {
        "name": "The Loneliness Angle",
        "body": (
            "Hey [Name] — genuine question, and feel free to ignore this if it's too random: "
            "what's the part of the search nobody warned you about?\n\n"
            "I've been on my own acquisition journey for a while now, and I keep noticing a gap "
            "between what people post about it publicly and what the process actually feels like "
            "at 11pm when a deal falls apart. I'm based in LA, focused on Health/Wellness SaaS, "
            "and I've found this path surprisingly quiet for how many people claim to be doing it.\n\n"
            "Not reaching out with an agenda — just curious whether your experience matches that, "
            "or if you've found a community that actually goes deep on the real stuff.\n\n"
            "What's been the most disorienting part so far?"
        ),
    },
    2: {
        "name": "The Intuition Angle",
        "body": (
            "[Name] — do you trust your gut when a deal feels off, or do you override it because "
            "the numbers look right?\n\n"
            "I ask because I've been thinking a lot lately about where intuition fits into "
            "acquisition decisions. The frameworks and filters help, but I've started to wonder "
            "if the best deals I'll pass on will be the ones where I talked myself out of a "
            "feeling rather than a fact. I'm in the middle of my own search — Health/Wellness "
            "SaaS, LA-based — and I keep running into this tension between analytical rigor "
            "and something harder to name.\n\n"
            "Curious if that's shown up for you, or if your process is more cleanly data-driven."
        ),
    },
    3: {
        "name": "The Identity Angle",
        "body": (
            "[Name] — this might be a strange opener, but: how has searching changed how you "
            "think about yourself professionally?\n\n"
            "I came from a background where my identity was pretty tied to executing within "
            "structures other people built. The acquisition path has been a different kind of "
            "mirror. I'm building toward owning a Health/Wellness or Longevity SaaS business, "
            "and somewhere along the way the search became as interesting as the destination.\n\n"
            "I'm not asking to compare notes on multiples — more curious about the interior "
            "side of it. Whether that resonates at all, or whether you've kept those two things "
            "completely separate.\n\n"
            "What's shifted for you, if anything?"
        ),
    },
    4: {
        "name": "The Collaboration Angle",
        "body": (
            "[Name] — do you think two searchers with different strengths could actually "
            "co-acquire something, or does it almost always fall apart on the ego piece?\n\n"
            "I've been sitting with this question for a while. I'm focused on Health/Wellness "
            "SaaS, and I've got a clear picture of what I'm looking for financially — but I've "
            "also started to think there's a version of this where the right partner changes "
            "what's possible, not just what's affordable. The hard part seems to be finding "
            "someone where the trust is real rather than convenient.\n\n"
            "Not pitching anything — genuinely curious how you think about the partnership "
            "question, and whether you've explored it or ruled it out."
        ),
    },
    5: {
        "name": "The Seller Psychology Angle",
        "body": (
            "[Name] — what do you think sellers are actually afraid of when they say they're "
            "not ready to sell?\n\n"
            "I've been doing a lot of listening in conversations with business owners lately, "
            "and I keep noticing that the real hesitation is almost never about price. It's "
            "something quieter — about identity, or about what happens to the people they built "
            "something with. I'm searching in the Health/Wellness SaaS space and I've started "
            "to think the best deals come from understanding that fear before you ever talk terms.\n\n"
            "Curious whether that matches what you've seen, or if you've found something else "
            "sitting underneath the \"not yet.\""
        ),
    },
    6: {
        "name": "The Off-Market Angle",
        "body": (
            "[Name] — have you found that the most interesting businesses you've looked at "
            "were never actually listed anywhere?\n\n"
            "I've been surprised by how much of what feels promising in my search comes through "
            "conversations rather than platforms — people who know someone, or owners who'd "
            "consider something if the right question got asked. I'm focused on Health/Wellness "
            "SaaS in the $1–3M ARR range, and I'm starting to think the deal I eventually do "
            "will come from a relationship that started before either party knew it was going "
            "somewhere.\n\n"
            "Curious what your sourcing experience has looked like — whether the off-market "
            "thesis has held up for you or turned out to be harder to operationalize than "
            "it sounds."
        ),
    },
    7: {
        "name": "The Search Fatigue Angle",
        "body": (
            "[Name] — do you ever hit a point in the search where you're not sure if you're "
            "being appropriately rigorous or just finding new ways to delay?\n\n"
            "I ask because I've been there more than once. There's a version of diligence "
            "that's real, and there's a version that's fear wearing the costume of standards. "
            "I'm in an active search — Health/Wellness SaaS, LA-based — and I've had to get "
            "honest with myself about which one I'm doing on a given week.\n\n"
            "Not asking for reassurance — more curious whether that distinction has shown up "
            "for you, and how you've navigated it when it has."
        ),
    },
    8: {
        "name": "The Criteria Angle",
        "body": (
            "[Name] — how much has your acquisition criteria actually changed since you started, "
            "versus how much have you just gotten better at explaining what it always was?\n\n"
            "I've been thinking about this lately because my own criteria look similar on paper "
            "to six months ago but feel meaningfully different in practice. I'm focused on "
            "Health/Wellness or Longevity SaaS — recurring revenue, strong retention, "
            "owner-operators who care about what they hand off. The numbers haven't shifted "
            "much, but my read on what makes a business actually resilient has.\n\n"
            "Curious whether your search has refined your thinking or mostly confirmed it."
        ),
    },
    9: {
        "name": "The Operator vs. Acquirer Angle",
        "body": (
            "[Name] — when you imagine yourself inside the business after close, what does "
            "a Tuesday morning actually look like?\n\n"
            "I find that question cuts through a lot of noise when I'm evaluating something. "
            "I'm searching in Health/Wellness SaaS and I've started using that mental image "
            "as a filter — if I can't picture the day-to-day with some clarity, the deal "
            "usually isn't right regardless of what the financials say. It also forces honesty "
            "about whether I want to run this thing or just own it, which are different answers.\n\n"
            "Curious what your version of that question is — the one you come back to when "
            "you're trying to get real about fit."
        ),
    },
    10: {
        "name": "The Why Angle",
        "body": (
            "[Name] — do you remember the specific moment you decided this was actually the "
            "path, rather than just an interesting idea?\n\n"
            "I ask because I've noticed there's usually a before and after for people in the "
            "ETA world — something that made it feel real and not theoretical. For me it was "
            "less a moment and more a slow realization that the alternative (someone else's "
            "structure, someone else's ceiling) had become genuinely unacceptable. I'm in the "
            "middle of a search focused on Health/Wellness SaaS, and that clarity has become "
            "its own kind of compass.\n\n"
            "Curious what yours was, and whether it still holds up the same way it did then."
        ),
    },
}


# ── Sequence Definitions ───────────────────────────────────────────────────────
# Each sequence defines:
#   first_dm     — DM template index to send first
#   cadence      — list of {day, action, dm} steps
#   description  — human-readable summary

SEQUENCES: dict[str, dict] = {
    "high-touch": {
        "description": "Enterprise leads — white-glove outreach with same-day DM and call",
        "first_dm": 1,
        "cadence": [
            {"day": 0, "action": "send_dm", "dm": 1,   "label": "DM 1 same day"},
            {"day": 3, "action": "send_dm", "dm": 2,   "label": "Follow-up DM 2 on day 3"},
            {"day": 7, "action": "call",    "dm": None, "label": "Phone/video call on day 7"},
        ],
    },
    "standard": {
        "description": "Operator leads — thoughtful DM outreach with mid-week follow-up",
        "first_dm": 3,
        "cadence": [
            {"day": 1, "action": "send_dm", "dm": 3, "label": "DM 3 on day 1"},
            {"day": 5, "action": "send_dm", "dm": 7, "label": "DM 7 on day 5"},
        ],
    },
    "discovery": {
        "description": "Unsure/exploring leads — light touch to understand their situation",
        "first_dm": 5,
        "cadence": [
            {"day": 1, "action": "send_dm", "dm": 5, "label": "DM 5 on day 1"},
        ],
    },
    "nurture": {
        "description": "Starter/cold leads — long-game relationship building",
        "first_dm": 10,
        "cadence": [
            {"day": 2, "action": "send_dm", "dm": 10, "label": "DM 10 on day 2"},
        ],
    },
}


def get_sequence(name: str) -> dict | None:
    """Return the full sequence definition by name, or None."""
    return SEQUENCES.get(name)


def get_first_dm(sequence_name: str) -> dict | None:
    """
    Return the first DM template dict for a given sequence, or None.
    Includes dm_number, name, and body.
    """
    seq = SEQUENCES.get(sequence_name)
    if not seq:
        return None
    dm_num = seq["first_dm"]
    template = DM_TEMPLATES.get(dm_num)
    if not template:
        return None
    return {"dm_number": dm_num, **template}


def get_next_action(sequence_name: str, days_since_entry: int) -> dict | None:
    """
    Return the next cadence action due on or before days_since_entry, or None.
    Useful for scheduling follow-ups.
    """
    seq = SEQUENCES.get(sequence_name)
    if not seq:
        return None

    due_actions = [
        step for step in seq["cadence"]
        if step["day"] <= days_since_entry
    ]
    if not due_actions:
        return None

    # Return the latest due action
    latest = max(due_actions, key=lambda s: s["day"])
    result = dict(latest)
    if latest.get("dm") and latest["dm"] in DM_TEMPLATES:
        result["template"] = DM_TEMPLATES[latest["dm"]]
    return result
