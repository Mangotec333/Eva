# EVA Loop Architecture & Social-Poster Integration

> Source of truth for the idea-to-revenue loop + Postiz social integration.
> Status: 2026-07-13. Owner: Vineet. Canonical messaging: deal-outcome dataset moat.

## The loop (phases + status)

1. **Ideation + research** — idea → competitor + market research → find wedge / fill gap. [EVA research agent — BUILD]
2. **Interest capture** — landing page captures leads (name/email/phone) → ghl-agent → GHL contact + tag. [DONE — eva-acquisition.mangotec.ai + ghl-agent + 2-tag scheme]
3. **Nurture + booking** — 7-touch 21-day sequence (5 email + 2 SMS) → book meeting. [DONE — GHL workflow `8024cff0`]
4. **Outbound social** — post to LinkedIn, YouTube, Reddit, Instagram, X (text/cards/video). [Postiz cloud — IN PROGRESS]
5. **Content engine** — weekly LinkedIn newsletter, blogs, white papers. [BACKLOG]
6. **LLM visibility** — get cited in LLM queries (ChatGPT/Perplexity/Google AI Overviews). [BACKLOG — separate AEO strategy]
7. **Gated orchestration** — all content/triggers gated by interest signals; EVA presents options; Slack comms. [BACKLOG — gates TBD at impl]

**Verdict:** Postiz completes phase 4 (outbound social). The core revenue loop (idea → interest → nurture → booked meeting) is mostly built; phases 5, 6, 7 are unbuilt. Social/content is the top-of-funnel demand-gen that feeds the capture+nurture engine.

## Postiz integration plan

- **Signup:** Postiz cloud Standard ($29/mo, 5 channels, 400 posts/mo, API + webhooks). Needs account + payment (Comet browser).
- **Connect 5 channels:** LinkedIn, YouTube, Reddit, Instagram, X — OAuth each (Comet, logged in).
- **Eva `social-poster` module:**
  - `post(content_variants, media, platforms[], schedule)` → Postiz API.
  - Per-platform format adaptation: LLM reformats one message → platform variants before calling Postiz.
  - Dedupe: Postiz History API + Eva ledger (`content_hash`, `card_id`, `platform`, `post_id`, `timestamp`). Before posting → `ledger.has(hash)` → skip/flag.
  - Multi-format: text, image cards, video. (Podcast = separate RSS pipeline, not Postiz.)
- **Agent-native:** Postiz ships API + webhooks + MCP — EVA drives it in plain language.

## Moats

- **Core moat: deal-outcome dataset** — proprietary, no generic AI can match. Every post/white paper should leak anonymized deal-outcome insight → content becomes a moat amplifier, not noise.
- **LLM citation** is itself a moat play (durable distribution = the new SEO). Prioritize high-authority white papers on eva-acquisition.mangotec.ai + schema markup + citations on high-DR sites.
- Operational leverage (GHL + landing + social + Slack wired) compounds but isn't itself a moat.

## Gates framework (decide at impl)

- Interest signals available: capture (tag), email open (GHL webhook `email_opened` → `EVENT_LEAD_ENGAGED`), click, reply, booking.
- Proposed gates (TBD):
  - Captured → 7-touch nurture.
  - Engaged (open/click) → escalate CTA / unlock white paper.
  - 50 captures → landing CTA flips to "book a meeting."
  - Booked → stop nurture, move pipeline Lead → Booked.
  - Cold (21-day complete, no book) → Nurture Complete stage.
- Eva ledger tracks each prospect's state; gates fire on state transitions.

## Slack orchestration

- EVA runs research/ideation → posts ranked options to Slack (`slack_direct` connected) → user picks → EVA executes.
- Options UI: interactive buttons or numbered list (decide at impl).

## Backlog

- Weekly LinkedIn newsletter (native LinkedIn Newsletter product — set up once, then Postiz/LinkedIn API publishes articles).
- Blogs + white papers (content engine).
- LLM citation strategy (AEO).
- End-of-sequence state tracking (Booked/Replied/Cold outcomes).
- First-name personalization on 7 touches.
- Unsubscribe ground-truth verification.
- Podcast distribution (separate RSS → Spotify/Apple/YouTube).
