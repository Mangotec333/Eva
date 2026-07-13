# Eva Video DNA & Review/Edit

**Video DNA** is a reusable, structured profile Eva builds for every founder video it ingests. Instead of treating a video as an opaque file, Eva probes it, transcribes it, samples keyframes, OCRs on-screen text, and records the result as one manifest per video — a durable "DNA" record that downstream review, edit, and distribution steps read from.

## Pipeline

```text
ingest → review → approve → edit → distribute
```

1. **Ingest** — Integrity gate (ffprobe): reject unplayable / truncated / missing-`moov` files with a clear re-export/re-record message. Capture duration, resolution, orientation, audio. Transcribe + extract keyframes + OCR on-screen text.
2. **Review** — Eva scores the video on clarity, investor-readiness, compliance, and technical checks. Each check returns `pass | warn | fail` with a specific, actionable suggestion.
3. **Approve** — No edit, trim, or publish runs without founder approval. The review report is sent as approvable line items (brief = approval gate). Nothing executes silently.
4. **Edit** — Approved edits execute (trim, captions, lower-thirds, blur) and repurposed assets regenerate (clips, quote cards, carousels, captioned cuts).
5. **Distribute** — See stealth posture below.

## Stealth-default posture

Raise content defaults to **stealth / private-directed distribution** until the fund is formed, counsel-approved, and an anchor commitment exists.

- `published_private` — send to named, verified accredited investors via email/DM (1-on-1 terms allowed).
- `published_public` (LinkedIn feed) — **gated**. Eva blocks public publish until fund-formed + counsel sign-off + anchor-commitment flags are set.

## Layout

Each ingested video gets its own directory: `eva-video-dna/<id>/`, holding its manifest plus keyframes and repurposed assets.

## Reference

- [`SPEC.md`](SPEC.md) — the full capability spec (ingest gate, manifest fields, review checks, approval gate, distribution posture, open notes).
- [`manifest.schema.json`](manifest.schema.json) — JSON Schema for one Video DNA record.
- [`templates/sample.manifest.json`](templates/sample.manifest.json) — a concrete filled-in example record.
- [`ingest.py`](ingest.py) — scaffold stub: `probe_integrity(path)` ffprobe integrity gate.

## Status

Docs + light scaffold. Transcription and video editing require external services (speech-to-text API, a non-linear edit layer) and are noted as future work — to be wired when a valid sample video exists. The first valid uploaded video becomes Video DNA asset #1 and the reference for tuning the review checks.
