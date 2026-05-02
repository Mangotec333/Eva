# Phase 1: macOS Voice Q&A

## Objective

Build the first working EVA/EVE loop on macOS:

```text
Wake phrase -> capture request -> transcribe -> answer locally -> speak response -> log task
```

## Milestones

1. **Text loop**: Working CLI loop with task schema, policy routing, response generation, and task log.
2. **Local model**: Replace heuristic provider with Ollama provider. Wired via
   `eva text --model-provider ollama --ollama-base-url <url> --ollama-model <name>`;
   `heuristic` remains the default for offline and test use.
3. **TTS**: Add macOS `say` adapter, then Piper adapter.
4. **STT**: Add whisper.cpp adapter for recorded audio files, then streaming audio.
5. **Wake word**: Add openWakeWord listener for “EVA” and “EVE.”
6. **Self-start**: Add macOS launchd plist and health check.
7. **Dashboard sync**: Update hosted dashboard with current progress and status.

## Acceptance criteria

- EVA responds to at least five spoken or typed questions.
- EVA logs each task with task ID, source, utterance, timestamp, and response.
- EVA asks for approval before high-impact actions.
- EVA can start automatically on macOS login or boot.
- The project dashboard reflects current status.

