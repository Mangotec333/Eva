# EVA/EVE

EVA, also called EVE, is a local-first voice assistant designed around a brain-hands modular architecture. Phase 1 targets macOS and implements the first working loop:

```text
wake phrase or push-to-talk -> speech/text input -> brain router -> local model response -> spoken/text output -> task log
```

This repository is Git-ready and intentionally starts with a safe text-mode loop so it can be tested anywhere. macOS microphone, wake-word, STT, and TTS adapters are defined as swappable modules.

## Phase 1 goal

Build a working macOS Voice Q&A prototype with:

- Wake phrase support for “EVA” and “EVE”
- Local speech-to-text path using `whisper.cpp`
- Local response generation through Ollama or another OpenAI-compatible local endpoint
- Local text-to-speech through Piper or macOS `say`
- Durable task logs
- Economy-first runtime that keeps only lightweight services hot

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
eva text
```

Run tests:

```bash
pytest
```

## macOS runtime plan

Development starts in text mode. On the target Mac, install the optional native tools:

```bash
brew install portaudio ffmpeg
curl -fsSL https://ollama.com/install.sh | sh
```

Then install or build:

- `openWakeWord` for wake phrase detection
- `whisper.cpp` for local transcription
- `Piper` or macOS `say` for speech output
- `Ollama` for local model serving

## Project structure

```text
services/
  voice/      voice shell and user I/O adapters
  brain/      task routing and answer generation
  stt/        speech-to-text adapters
  tts/        text-to-speech adapters
  model/      model provider adapters
config/       assistant configuration
docs/         roadmap, decisions, and design notes
ops/          launchd/systemd/docker service files
scripts/      helper scripts
tests/        automated tests
```

## Safety contract

EVA should never silently drop a request. It should complete it, clarify it, safely transform it, request credentials, request approval, sandbox it, schedule it, or explain the closest achievable substitute.

