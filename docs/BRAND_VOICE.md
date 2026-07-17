# EVA — Brand Voice

**Voice guardrails for content-facing modules.** Any module that produces words
a human outside the company will read — `content-engine`, `postcards`,
`outreach`, `channels`, `social-publish`, `linkedin`, `email_agent`,
`brand-builder`, `waitlist` — aligns to this file. It's a companion to
`docs/MISSION.md` (why we exist) and `docs/CURRENT_GOALS.md` (what we're pushing
now). This changes rarely; treat it as a read-only alignment artifact, not a
config to edit per-post.

**Owner:** Vineetkumar Ravi · Mangotec LLC
**Last updated:** 2026-07-17

---

## The voice in one line

> **Direct, analytical, warm, contrarian.**

Vineet writes like a logical man who learned to trust intuition — precise about
the analysis, honest about the felt sense, and unafraid to say the thing the room
disagrees with. The through-line of everything he publishes is the signature
thesis: *intuition is an LLM* — it gets better with more, and more diverse,
experience (see `docs/signature-talk.md`).

**The transformation the content sells:** from *"only logic counts — gut feelings
are noise"* to *"logic is the analyst, intuition is the executive."*

---

## The four attributes, made concrete

- **Direct.** Short sentences. One idea per line. Say the conclusion first, then
  the reasoning. No hedging, no throat-clearing, no "excited to announce."
- **Analytical.** Claims are grounded — a real deal, a real metric, a real
  pattern EVA observed. Frameworks over vibes. If there's a number, use it. Show
  the reasoning, don't just assert.
- **Warm.** Written to a person, not a market. Curious and humble about what he's
  still learning (his wife's intuition outperforming his logic is a recurring,
  self-deprecating anchor). Confident without contempt.
- **Contrarian.** Starts from the uncomfortable truth others avoid ("most
  high-achieving men are data-rich and wisdom-poor"). Pattern-interrupts, not
  hot takes for their own sake — the contrarian angle always resolves into a
  useful reframe.

---

## The three voice modes (content-engine profiles)

Content-facing modules pick the mode that fits the message. These map directly to
`modules/content-engine` voice families:

| Mode | Use for | Effect |
|------|---------|--------|
| **thought_leader** (`llm_intuition`, `deal_flow`) | Frameworks, mental models, acquisition analysis | High-reach — builds authority |
| **builder_log** (`builder_log`, `pattern_interrupt`) | Raw build updates, EVA learnings, honest metrics | Medium-reach — builds trust |
| **human_story** (`human_story`) | Personal moments, relationship observations, emotional anchors | High-reach — builds connection |

Default posture: lead with a hook, deliver one idea, end with a turn or a
question. Never bury the point.

---

## Do not say

The banned list (enforced by `content-engine`'s voice_dna). These words read as
LinkedIn-hype and break the "quiet confidence over hype" rule:

> game-changer · revolutionary · excited to announce · thrilled · leverage ·
> synergy · ecosystem · empower · journey · passionate · cutting-edge · unlock ·
> thought leadership · paradigm · transformative · innovative · seamless ·
> robust · learnings · deep dive · circle back · move the needle · bandwidth

Also avoid: fake urgency, manufactured scarcity, engagement-bait ("comment YES
below"), and claiming outcomes that haven't happened yet.

---

## Formatting defaults

- Short sentences; one idea per line; generous line breaks.
- Hook in the first line — it's the only line most people read.
- Max 7 hashtags; prefer fewer or none.
- Specifics over adjectives: "the deal the spreadsheet said no to" beats "an
  exciting opportunity."
- White-label safe: personal data lives in each install's `user_profile.json`
  (see `modules/content-engine/voice_dna.py`), never hardcoded in a module.

---

## Recurring themes to draw from

Straight from the signature talk — reliable, on-brand source material:

- Intuition is an LLM; diverse experience is training data.
- Logic is the analyst, intuition is the executive.
- Follow heart → validate with mind → logic executes.
- Data-rich and wisdom-poor: the failure mode of the high-achiever.
- EVA is the product origin story — an AI built to develop judgment, not replace it.

---

## The hard rule: nothing auto-publishes

Voice guardrails do not override the approval gate. Every outbound artifact —
post, card, email, DM — is **draft → approved → posted**, with a human at the
line of irreversibility (see the Architecture Directive in
`modules/README.md`). On-brand is necessary, not sufficient; a human still
approves the send.

---

*Companion documents: `docs/MISSION.md` and `docs/CURRENT_GOALS.md`. Source of
the voice: `docs/signature-talk.md`.*
