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
- `--tts-provider {console,macos-say,none}` — selects the speaker. Default
  `console` (offline-safe, prints `EVA: ...`). `macos-say` shells out to the
  built-in `/usr/bin/say` and only works on macOS. `none` suppresses speech.
- `--voice NAME` — voice name passed to the TTS provider. For `macos-say` this
  becomes `say -v NAME`. List available voices with `say -v '?'`.
- `--no-speak` — suppress all spoken/printed TTS output regardless of
  `--tts-provider`.

### Speak responses through macOS `say`

The console default works everywhere. To hear EVA on a Mac:

```bash
# One-off smoke test of the say command itself
/usr/bin/say "EVA online"

# Pick a voice (optional)
say -v '?' | head        # list voices
say -v Samantha "hello"

# Run the text loop with macOS speech output
source .venv/bin/activate
eva text --tts-provider macos-say --voice Samantha

# Same, but against a local Ollama model
eva text \
  --tts-provider macos-say --voice Samantha \
  --model-provider ollama \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-model llama3.2

# Run silently (no console echo, no speech)
eva text --no-speak
```

If `eva text --tts-provider macos-say` is run on a non-macOS host or `say`
cannot be located, the speaker raises a clear error rather than silently
dropping the response. Use `--tts-provider console` (default) or `--no-speak`
on those hosts.

To verify the loop works without Ollama running, omit the flags and use the default
heuristic provider:

```bash
eva text
```

### Voice loop on macOS (mic → STT → brain → TTS)

`eva voice` is a fixed-duration push-to-talk loop. Each turn it captures
`--duration` seconds from the default input device, transcribes the clip,
routes it through the brain, and speaks the response. **All audio stays on
the machine** — nothing is uploaded to a cloud STT.

```text
[ press Enter ] -> mic capture -> STT -> BrainOrchestrator -> TTS -> task log
                       ^                                              |
                       +------------- next turn or `q` to quit -------+
```

#### One-time setup

```bash
# install audio extras
brew install portaudio
source .venv/bin/activate
pip install -e ".[voice,dev]"

# build whisper.cpp (only if you want real transcription)
git clone https://github.com/ggerganov/whisper.cpp /tmp/whisper.cpp
make -C /tmp/whisper.cpp -j
bash /tmp/whisper.cpp/models/download-ggml-model.sh base.en
```

#### First local test command (no mic, model, or whisper required)

The fastest way to confirm the voice loop is wired up end-to-end on your
machine:

```bash
eva voice \
  --recorder fake \
  --stt-provider text \
  --mock-utterance "hello eva" \
  --tts-provider console
```

This uses the fake recorder, the text-mock STT, the heuristic brain, and the
console speaker — no audio hardware, no Ollama, no whisper.cpp. Press Enter
to "record" a turn, `q`+Enter to quit.

#### Real voice loop on macOS

```bash
# real mic + whisper.cpp + local Ollama + macOS `say`
eva voice \
  --duration 5 \
  --recorder sounddevice \
  --stt-provider whisper-cpp \
  --whisper-bin /tmp/whisper.cpp/main \
  --whisper-model /tmp/whisper.cpp/models/ggml-base.en.bin \
  --model-provider ollama \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-model llama3.2 \
  --tts-provider macos-say \
  --voice Samantha
```

#### Dictation completion: silence cutoff and manual stop

By default, `eva voice` records a fixed `--duration` window per turn (the
push-to-talk model from the first milestone). For chat-window-style mic
UX — record until the speaker stops, with an explicit stop button —
opt in with `--silence-timeout`:

```bash
# hands-free dictation: stops automatically after ~1.2s of silence
eva voice \
  --recorder sounddevice \
  --silence-timeout 1.2 \
  --max-duration 30 \
  --stt-provider whisper-cpp \
  --whisper-bin /tmp/whisper.cpp/main \
  --whisper-model /tmp/whisper.cpp/models/ggml-base.en.bin \
  --tts-provider macos-say
```

When `--silence-timeout` is set, the recorder captures audio in small
chunks and ends the turn as soon as **any** of the following is true:

1. trailing silence has lasted `--silence-timeout` seconds (the dictation
   "I'm done talking" cue),
2. the hard cap `--max-duration` is hit (a stuck VAD can never record
   forever — same role as the auto-stop on a chat-window mic button),
3. a `StopSignal` handed to the loop is flipped from another thread (the
   manual-stop control surfaced for UIs and the local bridge).

Without `--silence-timeout`, the legacy `--duration` behavior is
unchanged. Existing scripts keep working.

##### Manual-stop API

The voice loop accepts a `services.audio.StopSignal` you can flip from a
GUI button, an HTTP route, or a signal handler. The clip captured up to
that moment is transcribed and answered as a normal turn. Sketch:

```python
from services.audio import StopSignal, build_recorder
from services.audio.vad import SilenceConfig
from services.voice.loop import run_voice_loop_sync
# ...build brain, transcriber, speaker as usual...

stop = StopSignal()
# Hand `stop` to your UI; call stop.stop() when the user clicks the mic
# button. The loop clears it at the start of each turn.

run_voice_loop_sync(
    recorder=build_recorder("sounddevice"),
    transcriber=transcriber,
    brain=brain,
    speaker=speaker,
    duration_seconds=5.0,  # ignored when silence_config is set
    silence_config=SilenceConfig(silence_timeout_seconds=1.2),
    stop_signal=stop,
)
```

#### Voice flags

- `--duration FLOAT` — seconds captured per turn in the legacy fixed-window
  mode (default `5.0`). Ignored when `--silence-timeout` is set.
- `--silence-timeout FLOAT` — opt into hands-free dictation. Trailing
  silence (in seconds) that ends a turn. Default: off. Typical: `1.0`-`1.5`.
- `--max-duration FLOAT` — hard cap per turn when silence completion is on
  (default `30`). Acts as the chat-mic auto-stop.
- `--silence-threshold FLOAT` — int16 RMS amplitude below which a chunk is
  treated as silent (default `350`). Lower = more sensitive.
- `--silence-chunk-seconds FLOAT` — polling chunk size for silence
  detection and manual-stop responsiveness (default `0.1`).
- `--recorder {sounddevice,fake}` — audio backend. `sounddevice` requires
  the `[voice]` extra and a working input device; if either is missing the
  CLI exits with a clear error rather than producing silent audio. `fake`
  emits silence and is intended for tests/CI.
- `--sample-rate INT` — capture sample rate (default `16000`, what
  whisper.cpp expects).
- `--stt-provider {text,whisper-cpp}` — `text` is the offline mock used by
  tests. `whisper-cpp` shells out to a user-built whisper.cpp binary; both
  `--whisper-bin` and `--whisper-model` are required.
- `--whisper-bin PATH`, `--whisper-model PATH` — paths to the whisper.cpp
  `main` executable and a ggml model file. Verified at startup so a typo
  fails immediately.
- `--mock-utterance TEXT` — when `--stt-provider=text`, override the fixed
  transcription so you can drive the brain end-to-end without a mic.
- `--model-provider`, `--ollama-base-url`, `--ollama-model` — same as
  `eva text`.
- `--tts-provider`, `--voice`, `--no-speak` — same as `eva text`.

The voice loop appends one JSONL line per turn to `data/voice_tasks.jsonl`
(override with `--log-path`). `Recorder` errors and `Transcriber` errors
are reported per-turn and the loop continues, so a flaky mic does not
crash the session.

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
- `--tts-provider {console,macos-say,none}`, `--voice`, `--no-speak` — accepted
  for parity with `eva text`. The bridge **does not speak server-side**; clients
  render speech locally. The selected provider is advertised over `/health`
  (`notes`) and `/capabilities` (`tts.client_side`) so a CLI/GUI client can
  decide how to render the response.

## Safety contract

EVA should never silently drop a request. It should complete it, clarify it, safely transform it, request credentials, request approval, sandbox it, schedule it, or explain the closest achievable substitute.

The bridge enforces this at the protocol boundary: every response is wrapped in
a `BrainResponseEnvelope` with an explicit `requires_approval` flag, and the
heuristic policy routes high-impact verbs (`delete`, `send`, `purchase`, …) to
`status=needs_approval` instead of executing.
