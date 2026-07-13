# Eva Capability Spec — Eva ↔ Computer Execution Bridge

## Purpose
Eva (the deployed agent) delegates execution-heavy or tool-rich work to **Computer** as a backend execution layer. Eva owns the orchestration, doctrine, and approval gates; Computer owns raw execution with its tools, connectors, and model fleet. This lets Eva stay lightweight and always-on while accessing capabilities she doesn't host herself (cloud speech-to-text, video processing, web research, connector actions, asset generation).

## When Eva calls Computer
Eva delegates a task to Computer when the work needs something Eva can't do inline:
- **Transcription** (cloud STT: OpenAI Whisper API / Deepgram) for Video DNA.
- **Video processing** (ffmpeg: keyframe extraction, audio normalize, trim, captions, lower-thirds).
- **OCR / on-screen text detection** on video frames.
- **Web research** (current/external facts, market data).
- **Connector actions** (Gmail, Slack, Google Drive, GitHub, GHL, Vercel, finance).
- **Asset generation** (images, audio, video, documents, charts).

## Interface contract
Eva issues a **Task** to Computer; Computer executes and returns a structured **Result**.

### Task (Eva → Computer)
```json
{
  "task_id": "string",
  "objective": "specific, self-contained instruction (Eva includes all context — Computer has no conversation history)",
  "context_refs": ["paths/urls to workspace files Eva produced"],
  "constraints": { "approval_required": true, "irreversible_actions": [], "budget_hint": "low|med|high" },
  "result_schema": { "...": "optional JSON schema Computer should return" }
}
```

### Result (Computer → Eva)
```json
{
  "task_id": "string",
  "status": "completed | failed | needs_approval",
  "artifacts": [{ "type": "transcript|keyframes|edited_video|asset", "path": "workspace path" }],
  "review_notes": [{ "check": "clarity|compliance|technical", "severity": "pass|warn|fail", "note": "string", "suggested_edit": "string" }],
  "next_actions": ["string"]
}
```

## Approval gate (mirrors Eva's doctrine)
- **Auto-execute:** internal/reversible work (probe integrity, transcribe, extract keyframes, normalize audio, draft assets).
- **Approval-gated:** anything external or irreversible (send email, post publicly, publish, delete). Eva surfaces these as approvable line items to the founder; Computer never sends/publishes without the founder's OK.
- **Compliance guardrail:** for raise content, Computer flags public-publish as blocked until `fund_formed + counsel_signoff + anchor_commitment` are true (stealth default).

## Auth & scope
- Computer runs with the user's connected accounts (connectors already wired).
- Each Eva task is scoped; Computer refuses out-of-scope or unscoped irreversible actions.
- Secrets never pass through Eva — Computer holds credentials; Eva passes intent only.

## First wired use case: Video DNA transcription
Eva's Video DNA pipeline step **transcribe** calls the bridge:
1. Eva → Computer: "Transcribe /workspace/video_review/v2/audio_ref.m4a, return word-level timestamps."
2. Computer → cloud STT (Whisper API / Deepgram).
3. Computer → Eva: transcript + timestamps as an artifact.
4. Eva continues: review checks (clarity, compliance), builds the approvable edit list, then (on approval) calls Computer back to execute ffmpeg edits.

## Open notes
- Cloud STT and a non-linear edit layer are external services wired on Computer's side; Eva only needs the bridge contract.
- This sandbox has no internet, so transcription can't run here — but Eva's deployed environment calls Computer, which does have cloud access. The bridge is what makes Eva's video-review capability real.
