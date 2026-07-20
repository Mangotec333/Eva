# EVA — Session State (end of 2026-07-13, ~9:02 PM PT)

> Canonical pick-up doc. Read this first tomorrow morning.

## Session Update — 2026-07-20 (EVA Manifestation Loop shipped)

Built and deployed the EVA Manifestation Loop video per Vineet's request: a ~70s high-energy video with epic-hype AI narration and 6 AI-generated cinematic scenes, framing the North Star ($1B / 1M lives) and personal goals as already achieved 6 months ago (present-tense affirmations, sensory language). Goal: play it incessantly to reinforce belief in already-achieved goals.

**Shipped this session:**
- Video asset committed at `eva-assets/manifestation/EVA_Manifestation_Loop.mp4`.
- Auto-play wired into the 4am morning routine: `modules/autostart/eva-manifest-morning.sh` (opens video in QuickTime, looping) + `modules/autostart/launchd/com.eva.manifest-morning.plist` (launchd `StartCalendarInterval`, fires daily 4:00 AM — NOT a persistent service, so intentionally excluded from `eva-install-services.sh`'s pid health-check loop; added to its own `SCHEDULED_TRIGGERS` array instead).
- Documented in `modules/autostart/README.md` ("Scheduled Triggers" section) and `EVA_DEVELOPMENT_BACKLOG.md` (new "🎬 EVA MODULE — Manifestation Loop" section, items #28-30).
- Backlogged v2 enhancements per Vineet's request: #29 clone his own voice for narration, #30 use his own photos/likeness instead of AI silhouettes/visuals.
- **Action needed on the Mac:** run `bash ~/Eva/modules/autostart/eva-install-services.sh` once after pulling this commit so the new `com.eva.manifest-morning` launchd job actually gets loaded (installer copies+substitutes the plist and loads it automatically — no manual plist editing needed).

**Open thread:** v2 (own voice + own photos) is backlog-only, not started — needs a voice-cloning TTS provider (current Gemini 2.5 Pro TTS stack has no cloning support) and real reference photos/footage from Vineet.

---

## PICK UP HERE — top priority
**Fix email delivery (2 root causes found) → unblocks the first-paying-customer path.**

## Email delivery — DIAGNOSIS COMPLETE
**Test contact:** vineetkumar014@gmail.com, ID `kgnD4wJVK8cIsMW8MXX0` (captured 8:44 PM PT, count 26). Zero emails across 3 tests (+1, +777, vineetkumar014).

### Root cause #1 (PRIMARY) — workflow is DRAFT, never published
- Workflow `8024cff0` shows status **"Draft"** + a blue **"Publish"** button in GHL UI. A Draft workflow cannot fire triggers or send emails.
- The earlier "published/toggled ON" claim was WRONG (unverified subagent claim — lesson: always verify workflow state in GHL UI).
- GHL warning: *"This trigger only applies to tags added after the workflow is published."*
- Trigger config itself is correct: Contact Tag → "Eva Acquisition Lead Tag Added" → tag `eva-acquisition-lead` → Added.

### Root cause #2 (SECONDARY) — contact tagged partial, not lead
- Contact `kgnD4wJVK8cIsMW8MXX0` has tag `eva-acquisition-lead-partial`, NOT `eva-acquisition-lead`.
- Contact activity tab: "No activities yet!" — never enrolled.
- User's hypothesis was correct (contact tagged partial).
- Form code (`eva-landing/app.js`: submit sends `partial:false` line 261) + ghl-agent code (`service.py`: full-capture path adds `eva-acquisition-lead` + enrolls, lines 252/266/279) are BOTH correct. So the bug is runtime, not code:
  - Likely: GHL upsert `tags` param doesn't add tags on UPDATE (contact pre-existed from autosave with PARTIAL tag), and `add_contact_tag` silently failed OR a delayed autosave (`partial:true`) re-upserted with `[PARTIAL]` and REPLACED the lead tag after submit.
  - Investigate: `ghl.add_contact_tag` error handling (does it raise on API error?) + whether autosave can fire after submit (race).

### Root cause #3 (WARNING) — shared sending domain
- Sending domain `mg.msgsndr.biz` — shared LeadConnector domain (no dedicated/verified custom domain).
- Daily limit 100, sent today 0. Works for sending but spam-prone. Add a dedicated verified domain for production deliverability later.

## Fixes needed tomorrow (in order)
1. **Publish workflow `8024cff0`** — Comet → GHL UI → open workflow → click Publish. URL: https://app.gohighlevel.com/v2/location/kyK4yAY6Hur3F4deCx2n/automation/workflow/8024cff0-1367-4f2a-84ba-dce107f7e521
2. **Fix the tag bug** — investigate why full-capture isn't persisting `eva-acquisition-lead` (ghl.add_contact_tag error handling + autosave-after-submit race). Re-add the lead tag to `kgnD4wJVK8cIsMW8MXX0` to test, or capture fresh.
3. **Re-test** with a fresh capture (fresh email + fresh phone) AFTER publishing → confirm Touch 1 email arrives in inbox (not just spam).
4. (Later) Add dedicated sending domain for deliverability.

## Postiz (social-poster) — BLOCKED on user decision
- Account created: Vineet@mangotecusa.com (Google), Standard plan selected.
- Blocked at card form: $0 today, trial ends 2026-07-20, then $29/mo. Card required to start trial.
- **Decision pending:** (1) enter card → I finish 5 channel connects + API key + build `social-poster` module; (2) defer; (3) self-host (free + platform app approvals).
- Card form URL: https://platform.postiz.com/launches?onboarding=true

## Loop architecture — SAVED
- `docs/EVA_LOOP_ARCHITECTURE.md` (commit 6f99e76) — full idea-to-revenue loop (7 phases), Postiz integration plan, moats (deal-outcome dataset), gates framework, Slack orchestration, backlog.

## Infra state (live)
- ghl-agent: port 8782 on Mac, exposed via cloudflared quick tunnel `https://handheld-press-wheat-court.trycloudflare.com` — ALIVE (offline:false, count 26). EPHEMERAL — dies on Mac sleep; restart with `caffeinate` + cloudflared quick tunnel.
- launchd plist: ghl-agent persistent (RunAtLoad + KeepAlive, token in EnvironmentVariables).
- Eva repo: github.com/Mangotec333/Eva (main, HEAD 6f99e76).
- eva-landing repo: github.com/Mangotec333/eva-landing (master, da35cb4) → Vercel at https://eva-acquisition.mangotec.ai.
- Eva Mac path: /Users/vineetravi/Eva.

## Activities this session (2026-07-13)
1. Committed 5 LinkedIn card PNGs to Eva repo (`eva-assets/linkedin-cards/eva_card_1..5.png`, HEAD 40899bf).
2. Submitted test lead `vineetkumar014+777@gmail.com` + phone `3235557777` → capture confirmed (contact `aVQ5ORY8vEe8fSBxKpV7`, count 25).
3. Enrolled `vineetkumar014@gmail.com` + phone `3235558888` in 7-touch → capture confirmed (contact `kgnD4wJVK8cIsMW8MXX0`, count 26).
4. Researched unified social-posting tools → Ayrshare ($149/mo API) vs Postiz ($29/mo cloud / free self-host, 30+ networks). Recommended Postiz cloud.
5. Saved loop architecture: `docs/EVA_LOOP_ARCHITECTURE.md` (6f99e76).
6. Drove Comet through Postiz signup → account created → blocked at card form. Decision pending.
7. Diagnosed GHL email delivery (Comet, read-only): root causes = workflow DRAFT + contact tagged partial + shared domain.

## Commits this session (Eva repo main)
- `335b732..40899bf` — LinkedIn card PNGs (`eva-assets/linkedin-cards/eva_card_1..5.png`)
- `6f99e76` — docs(loop): EVA_LOOP_ARCHITECTURE.md
- (prior session: `3125c08` 2-tag scheme, `f43cf87` playbook, `7ace61f` system-map, `40005c1` partial flag, `da35cb4` eva-landing phone+autosave)

## Test contacts (GHL location kyK4yAY6Hur3F4deCx2n)
- `kgnD4wJVK8cIsMW8MXX0` — Vineet Sequence Test / vineetkumar014@gmail.com / 3235558888 (count 26, tagged PARTIAL — should be LEAD)
- `aVQ5ORY8vEe8fSBxKpV7` — Eva Email Test / vineetkumar014+777@gmail.com / 3235557777 (count 25)
- `ayOLzpW1eDSJu88mUDEp` — Vineet GoLive Test / vineetkumar014+1@gmail.com / 7209370152 (count 24)
- `fpPkDmfI4A7g2g5aF99j` — Eva Sequence Test / eva.sequence.test.0713@mangotec.ai (count 22)

## Key IDs / URLs
- GHL location: `kyK4yAY6Hur3F4deCx2n`
- Workflow 7-touch: `8024cff0-1367-4f2a-84ba-dce107f7e521` (**DRAFT — needs Publish**)
- Pipeline "Eva Acquisition": `hODxp7jDIraP6FaNZqNU`
- Calendar "Eva Demo Call": `l9jr2HfsonQDHzg3LkC1`
- Booking link: https://api.leadconnectorhq.com/widget/booking/l9jr2HfsonQDHzg3LkC1
- GHL token: stored in credentials vault / Mac launchd plist env — DO NOT paste raw tokens into docs (see 2026-07-14 GitGuardian incident).

## Backlog (from loop architecture)
- Publish workflow + fix tag bug (TOMORROW, top priority).
- Postiz card decision → build `social-poster` module (post + dedupe).
- End-of-sequence state tracking (Booked/Replied/Cold outcomes).
- First-name personalization on 7 touches.
- Unsubscribe ground-truth verification.
- Weekly LinkedIn newsletter, blogs, white papers, LLM citation (AEO).
- Pull 40-60 prospects → outreach → capture → 7-touch → first paying customer.
