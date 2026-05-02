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

`eva text` defaults to the offline `heuristic` model provider so it runs anywhere without
external services. To use a local Ollama server instead, pass `--model-provider ollama`
(see the macOS section below).

Run tests:

```bash
pytest
```

Lint:

```bash
ruff check .
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

### Run the text loop against a local Ollama model on macOS

After installing Ollama, start the server and pull a model in one terminal:

```bash
# Starts the Ollama HTTP server on http://127.0.0.1:11434
ollama serve

# In a second terminal, pull a small local model (one time)
ollama pull llama3.2
```

Then run EVA against that model:

```bash
source .venv/bin/activate
eva text \
  --model-provider ollama \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-model llama3.2
```

Flags:

- `--model-provider {heuristic,ollama}` — selects the answer backend. Default: `heuristic`
  (offline; used by tests). Use `ollama` to call a local Ollama server.
- `--ollama-base-url URL` — base URL for the Ollama HTTP API. Default
  `http://127.0.0.1:11434`.
- `--ollama-model NAME` — model tag to ask Ollama to run, e.g. `llama3.2`, `qwen2.5`,
  `mistral`. Default `llama3.2`.

To verify the loop works without Ollama running, omit the flags and use the default
heuristic provider:

```bash
eva text
```

## Project structure

```text
services/
  voice/      voice shell and user I/O adapters
  brain/      task routing and answer generation
  bridge/     local FastAPI bridge / HTTP API skeleton
  protocols/  typed Pydantic protocol contracts (envelopes, events, status)
  stt/        speech-to-text adapters
  tts/        text-to-speech adapters
  model/      model provider adapters
config/       assistant configuration
docs/         roadmap, decisions, and design notes
ops/          launchd/systemd/docker service files
scripts/      helper scripts
tests/        automated tests
```

## Communication protocol

EVA exposes a small typed protocol so a voice shell, a CLI, or a future GUI can
all talk to the same brain. The contracts live in `services/protocols/` and are
plain Pydantic models — anything that speaks JSON can use them.

```text
                +-----------------------+
                |    voice / text CLI   |
                +-----------+-----------+
                            | TaskRequestEnvelope
                            v
+-------------+    +--------+--------+    +------------------+
|  HTTP/SSE   |--->|   eva bridge    |--->| BrainOrchestrator|
| (curl, GUI) |    | FastAPI 127.0.0.1|    +--------+---------+
+-------------+    +--------+--------+             |
                            |                       v
                            | BrainResponseEnvelope  +-------------------+
                            |   + ApprovalEvent      | model provider     |
                            v                        | (heuristic|ollama) |
                +-----------+-----------+            +-------------------+
                |  client (CLI / GUI)   |
                +-----------------------+
```

Endpoints exposed by `eva bridge`:

- `GET /health` — `ProtocolStatus` with version, uptime, model provider
- `GET /protocols` — list of advertised transports (`task.http`, `health.http`,
  `capabilities.http`, `events.sse`)
- `GET /capabilities` — declared capability surface, including which ones
  require approval
- `POST /task` — accepts a `TaskRequestEnvelope`, returns a
  `BrainResponseEnvelope`; `requires_approval=true` is set explicitly when the
  brain routes to the approval policy
- `GET /events` — minimal SSE skeleton (ready + heartbeat). Streaming task
  events are documented as the next step.

### Run the bridge for local testing

The bridge binds to `127.0.0.1` by default. **Do not expose it on a non-loopback
address without an authentication layer** — there is none today.

```bash
# Terminal 1: optional — start Ollama if you want a real local model
ollama serve
ollama pull llama3.2

# Terminal 2: run the bridge against the offline heuristic provider (no Ollama needed)
source .venv/bin/activate
eva bridge

# Or wire the bridge to a local Ollama:
eva bridge \
  --model-provider ollama \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-model llama3.2
```

Send a safe task:

```bash
curl -s http://127.0.0.1:8765/task \
  -H 'content-type: application/json' \
  -d '{"channel":"bridge_http","request":{"utterance":"hello eva"}}' | jq
```

Trigger an approval-required path:

```bash
curl -s http://127.0.0.1:8765/task \
  -H 'content-type: application/json' \
  -d '{"channel":"bridge_http","request":{"utterance":"delete the old files"}}' | jq
```

Inspect the bridge surface:

```bash
curl -s http://127.0.0.1:8765/health       | jq
curl -s http://127.0.0.1:8765/protocols    | jq
curl -s http://127.0.0.1:8765/capabilities | jq
```

The CLI text mode keeps working alongside the bridge:

```bash
eva text                           # offline heuristic
eva text --model-provider ollama   # against local Ollama
```

### Bridge flags

- `--host` — bind address (default `127.0.0.1`). The CLI prints a warning if you
  pick a non-loopback host.
- `--port` — TCP port (default `8765`).
- `--model-provider {heuristic,ollama}` — same provider plumbing as `eva text`.
- `--ollama-base-url`, `--ollama-model` — forwarded to the Ollama provider when
  selected.

## Safety contract

EVA should never silently drop a request. It should complete it, clarify it, safely transform it, request credentials, request approval, sandbox it, schedule it, or explain the closest achievable substitute.

The bridge enforces this at the protocol boundary: every response is wrapped in
a `BrainResponseEnvelope` with an explicit `requires_approval` flag, and the
heuristic policy routes high-impact verbs (`delete`, `send`, `purchase`, …) to
`status=needs_approval` instead of executing.
