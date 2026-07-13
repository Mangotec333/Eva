# Eva Capability Spec — Video DNA & Review/Edit Pipeline

## Purpose
Eva ingests a founder video, builds a reusable "Video DNA" profile, reviews it for clarity + investor-readiness + compliance, flags needed edits, gets founder approval, then executes the edit and generates repurposed assets. Default posture: **stealth / private-directed distribution** for raise content until the fund is formed, counsel-approved, and an anchor commitment exists.

## 1. Ingest & integrity gate
- Probe with ffprobe: reject if `moov` atom missing, unplayable, or truncated (return a clear "re-export / re-record" message).
- Capture: duration, resolution, orientation (vertical required for LinkedIn), fps, bitrate, audio channels, loudness (mean/max dB).
- Transcribe audio (speech-to-text) with timestamps.
- Extract keyframes (e.g. at 10/25/50/75/90%); OCR any on-screen text (captions, lower-thirds, compliance cards).

## 2. Video DNA (asset manifest)
One JSON + markdown record per video, stored under `eva-video-dna/<id>/`:
- id, title, created_at, source_path, duration, resolution, orientation
- transcript (full text + word timestamps)
- keyframes (timestamp + thumbnail path)
- detected_on_screen_text[]
- thesis_tags[] (e.g. "storeys-raise", "deal-scoring", "authority")
- compliance_flags{ accredited_qualifier, not_an_offer, fund_status_accurate, no_unverified_guarantees }
- repurposed_assets[]{ type: clip|quote_card|carousel|captioned_cut, path }
- approval_state: draft → reviewed → approved → published_private → published_public
- review_notes[]

## 3. Review checks (Eva reviews the video)
**Clarity:** hook lands in first 8 sec · single clear thesis · concrete numbers · explicit CTA.
**Investor-readiness:** credible · specific · skin-in-the-game mentioned · low-friction next step (DM / reply).
**Compliance (raise content):** accredited-investors-only qualifier present · "not an offer to sell securities" language · fund-formation status stated accurately ("fund not yet formed") · no guaranteed returns · Reg D 506(c) framing.
**Technical:** vertical orientation · audio levels in range (no clipping, ~ -16 to -12 LUFS-ish) · face lit and visible · captions burned in · 15–20s head/tail silence for clean trim.

Each check returns `pass | warn | fail` with a specific, actionable suggestion (e.g. "cut 0:12–0:18 (repetition)", "add lower-third: 'Accredited investors only · Not an offer to sell securities'", "hook arrives at 0:06 — move to 0:00").

## 4. Approval gate (no silent execution)
- Eva sends the review report (in-app + Slack) with each suggested edit as an **approvable line item**.
- No edit, trim, or publish runs without founder approval — mirroring the Sunday Monetization doctrine (brief = approval gate).
- Approved edits execute (trim, captions, lower-thirds, blur) and repurposed assets regenerate.

## 5. Distribution posture (stealth default)
- `published_private`: send to named, verified accredited investors via email/DM (terms allowed 1-on-1).
- `published_public` (LinkedIn feed): **gated** — requires fund formed + counsel sign-off + anchor commitment. Eva blocks public publish until those flags are set in the Video DNA / fund state.

## 6. Open implementation notes
- Transcription + editing require external services (speech-to-text API, a non-linear edit layer) — to be wired when a valid sample video exists.
- First valid uploaded video becomes **Video DNA asset #1** and the reference for tuning the review checks.
