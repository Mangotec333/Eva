"""
EVA Voice Module — voice_service.py
Port: 8774
Location: ~/Eva/modules/voice/voice_service.py

Always-on Mac background service providing:
  - Wake word detection ("Hey EVA") via pvporcupine or SpeechRecognition fallback
  - Audio recording with silence detection (1.5s threshold)
  - Transcription via OpenAI Whisper (local, free)
  - TTS via ElevenLabs Flash v2.5 (fallback: macOS `say`)
  - Command routing (pattern match + Claude claude-3-5-haiku fallback)
  - FastAPI REST + WebSocket for Command Center integration
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import anthropic
import requests
import uvicorn
import whisper
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EVA-VOICE] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("eva.voice")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PORT = 8774
BASE_DIR = Path.home() / "Eva" / "modules" / "voice"
PROFILE_PATH = BASE_DIR / "user_profile.json"

CONTEXT_API = "http://localhost:8765"
ORCHESTRATOR_API = "http://localhost:8768"

# Internal state (shared across threads via lock)
_state_lock = threading.Lock()
_state = {
    "listening": False,
    "wake_word_detected": False,
    "last_command": "",
    "last_response": "",
    "error": None,
}

# Connected WebSocket clients
_ws_clients: list[WebSocket] = []
_ws_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def load_profile() -> dict:
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH) as f:
            return json.load(f)
    log.warning("user_profile.json not found; using defaults")
    return {}


def get_cfg(key: str, default=None):
    return load_profile().get(key, default)


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------
async def broadcast_state():
    """Push current state to all connected WS clients."""
    with _state_lock:
        payload = json.dumps(_state)
    dead = []
    async with _ws_lock:
        for ws in _ws_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.remove(ws)


def broadcast_state_sync():
    """Thread-safe wrapper to schedule broadcast from background thread."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast_state(), loop)
    except RuntimeError:
        pass


def set_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)
    broadcast_state_sync()


# ---------------------------------------------------------------------------
# TTS — ElevenLabs / macOS say fallback
# ---------------------------------------------------------------------------
def speak(text: str):
    """Speak text. Uses ElevenLabs if configured, else macOS `say`."""
    if not text or not text.strip():
        return

    api_key = get_cfg("elevenlabs_api_key", "")
    voice_id = get_cfg("voice_id", "")

    if api_key and voice_id:
        _speak_elevenlabs(text, api_key, voice_id)
    else:
        _speak_macos(text)


def _speak_elevenlabs(text: str, api_key: str, voice_id: str):
    try:
        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=api_key)
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_flash_v2_5",
            output_format="mp3_44100_128",
        )
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            for chunk in audio:
                f.write(chunk)
            tmp_path = f.name
        subprocess.run(["afplay", tmp_path], check=True)
        os.unlink(tmp_path)
        log.info("ElevenLabs TTS: spoke %d chars", len(text))
    except Exception as e:
        log.error("ElevenLabs TTS failed: %s — falling back to say", e)
        _speak_macos(text)


def _speak_macos(text: str):
    try:
        subprocess.run(["say", text], check=True)
        log.info("macOS say: spoke %d chars", len(text))
    except Exception as e:
        log.error("macOS say failed: %s", e)


# ---------------------------------------------------------------------------
# Transcription — local Whisper
# ---------------------------------------------------------------------------
_whisper_model: Optional[object] = None
_whisper_lock = threading.Lock()


def get_whisper_model():
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            model_name = get_cfg("whisper_model", "base.en")
            log.info("Loading Whisper model: %s", model_name)
            _whisper_model = whisper.load_model(model_name)
    return _whisper_model


def transcribe_audio(audio_path: str) -> str:
    try:
        model = get_whisper_model()
        result = model.transcribe(audio_path, language="en", fp16=False)
        return result["text"].strip()
    except Exception as e:
        log.error("Whisper transcription failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Audio recording with silence detection
# ---------------------------------------------------------------------------
def record_until_silence(
    silence_threshold: float = 1.5,
    max_duration: float = 30.0,
    sample_rate: int = 16000,
) -> Optional[str]:
    """
    Record from default mic until 1.5s of silence or max_duration.
    Returns path to WAV temp file, or None on failure.
    Uses PyAudio directly for fine-grained silence detection.
    """
    try:
        import math

        import pyaudio

        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = sample_rate
        SILENCE_THRESHOLD_RMS = 300  # adjust for environment

        p = pyaudio.PyAudio()
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

        log.info("Recording… (silence stops at %.1fs)", silence_threshold)
        frames = []
        silent_chunks = 0
        total_chunks = 0
        max_chunks = int(RATE / CHUNK * max_duration)
        silence_chunks_needed = int(RATE / CHUNK * silence_threshold)

        while total_chunks < max_chunks:
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
            total_chunks += 1

            # compute RMS
            import struct

            shorts = struct.unpack(f"{len(data)//2}h", data)
            rms = math.sqrt(sum(s * s for s in shorts) / len(shorts))

            if rms < SILENCE_THRESHOLD_RMS:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= silence_chunks_needed and total_chunks > int(
                RATE / CHUNK * 0.5
            ):
                break  # stop after minimum 0.5s of audio

        stream.stop_stream()
        stream.close()
        p.terminate()

        if not frames:
            return None

        import wave

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wf = wave.open(tmp.name, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
        wf.close()
        log.info("Recorded %d chunks → %s", total_chunks, tmp.name)
        return tmp.name
    except Exception as e:
        log.error("Audio recording failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Wake word detection
# ---------------------------------------------------------------------------
def _listen_with_pvporcupine(access_key: str, keyword_path: Optional[str]):
    """Primary wake word engine: Picovoice Porcupine."""
    import pvporcupine
    import pyaudio

    keywords = ["hey eva"] if not keyword_path else None
    if keyword_path:
        porcupine = pvporcupine.create(
            access_key=access_key, keyword_paths=[keyword_path]
        )
    else:
        # Use built-in 'hey siri' as closest proxy or 'computer'
        # For a custom "hey eva" keyword, a keyword_path (.ppn file) from
        # console.picovoice.ai is required. Fallback to SpeechRecognition below.
        porcupine = pvporcupine.create(
            access_key=access_key, keywords=["computer"]
        )
        log.warning(
            "No custom keyword_path for 'Hey EVA'. Using 'computer' as proxy. "
            "Generate a .ppn file at console.picovoice.ai for exact wake word."
        )

    pa = pyaudio.PyAudio()
    audio_stream = pa.open(
        rate=porcupine.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=porcupine.frame_length,
    )

    set_state(listening=True)
    log.info("Porcupine wake word detector active")

    try:
        while True:
            pcm = audio_stream.read(porcupine.frame_length, exception_on_overflow=False)
            import struct

            pcm = struct.unpack_from(f"{porcupine.frame_length}h", pcm)
            result = porcupine.process(pcm)
            if result >= 0:
                log.info("Wake word detected!")
                _on_wake_word()
    finally:
        audio_stream.close()
        pa.terminate()
        porcupine.delete()


def _listen_with_speech_recognition():
    """Fallback wake word using SpeechRecognition + keyword match."""
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    mic = sr.Microphone(sample_rate=16000)

    set_state(listening=True)
    log.info("SpeechRecognition wake word listener active (fallback mode)")

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)

    while True:
        try:
            with mic as source:
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=4)
            try:
                text = recognizer.recognize_google(audio).lower()
            except sr.UnknownValueError:
                continue
            except sr.RequestError:
                # Offline fallback — just listen for energy spikes
                continue

            if any(kw in text for kw in ["hey eva", "hey ava", "hey java"]):
                log.info("Wake phrase detected: '%s'", text)
                _on_wake_word()
        except Exception as e:
            log.debug("SR loop error: %s", e)
            time.sleep(0.1)


def _on_wake_word():
    """Called when wake word detected. Records, transcribes, routes."""
    set_state(wake_word_detected=True)
    speak("Yes?")
    time.sleep(0.3)  # brief pause after ack tone

    audio_path = record_until_silence()
    set_state(wake_word_detected=False)

    if not audio_path:
        log.warning("No audio captured after wake word")
        return

    text = transcribe_audio(audio_path)
    os.unlink(audio_path)

    if not text:
        speak("I didn't catch that.")
        return

    log.info("Transcribed: '%s'", text)
    set_state(last_command=text)
    response = route_command(text)
    set_state(last_response=response)
    speak(response)


def start_wake_word_listener():
    """Start the appropriate wake word engine in a daemon thread."""
    profile = load_profile()
    pv_key = profile.get("picovoice_access_key", "")
    keyword_path = profile.get("keyword_path", "")

    def run():
        if pv_key:
            try:
                _listen_with_pvporcupine(pv_key, keyword_path or None)
            except Exception as e:
                log.error("Porcupine failed (%s); switching to SR fallback", e)
                _listen_with_speech_recognition()
        else:
            log.info("No picovoice_access_key set — using SpeechRecognition fallback")
            _listen_with_speech_recognition()

    t = threading.Thread(target=run, daemon=True, name="wake-word-listener")
    t.start()
    return t


# ---------------------------------------------------------------------------
# Command Router
# ---------------------------------------------------------------------------
def route_command(text: str) -> str:
    """Pattern-match common commands; fall through to Claude for anything else."""
    t = text.lower().strip()

    # Calendar / Morning brief
    if re.search(r"calendar.*(today|now)|what.*(on my|today.*calendar)", t):
        return _cmd_morning_brief()

    if re.search(r"(read|tell me|give me).*(morning brief|brief)", t):
        return _cmd_morning_brief()

    # Navigation — Command Center
    if re.search(r"show.*(deal scout|acquire|pipeline)", t):
        _cmd_navigate("acquire")
        return "Opening Deal Scout for you."

    if re.search(r"show.*(dashboard|home|overview)", t):
        _cmd_navigate("dashboard")
        return "Navigating to Dashboard."

    # Start a service
    m = re.search(r"start\s+(.+)", t)
    if m:
        svc = m.group(1).strip()
        return _cmd_start_service(svc)

    # Status
    if re.search(r"^status$|how many.*services|services.*running", t):
        return _cmd_status()

    # LLM fallback
    return _cmd_llm(text)


def _cmd_morning_brief() -> str:
    try:
        resp = requests.get(f"{ORCHESTRATOR_API}/morning_brief", timeout=10)
        data = resp.json()
        # Extract plain text from brief
        brief = data.get("brief", data.get("summary", str(data)))
        if len(brief) > 600:
            brief = brief[:600] + "… that's your morning brief."
        return brief
    except Exception as e:
        log.error("Morning brief fetch failed: %s", e)
        return "I couldn't reach the morning brief service right now."


def _cmd_navigate(tab: str):
    """Tell Command Center to navigate to a tab via its WebSocket or REST."""
    try:
        requests.post(
            "http://localhost:3000/api/navigate",
            json={"tab": tab},
            timeout=3,
        )
    except Exception:
        pass  # best-effort; Command Center may not have this endpoint yet


def _cmd_start_service(service_name: str) -> str:
    try:
        resp = requests.post(
            f"{ORCHESTRATOR_API}/start/{service_name}", timeout=10
        )
        if resp.ok:
            return f"Starting {service_name}."
        return f"Couldn't start {service_name}. Status: {resp.status_code}."
    except Exception as e:
        return f"Failed to reach orchestrator: {e}"


def _cmd_status() -> str:
    try:
        resp = requests.get(f"{ORCHESTRATOR_API}/status", timeout=5)
        data = resp.json()
        online = data.get("online_count", "unknown")
        return f"Currently {online} EVA services are online."
    except Exception:
        return "I couldn't reach the orchestrator to check service status."


def _cmd_llm(text: str) -> str:
    """Send command to Claude claude-3-5-haiku for a response."""
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY", get_cfg("anthropic_api_key", ""))
        if not api_key:
            return "I don't know how to handle that, and no LLM key is configured."

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=300,
            system=(
                "You are EVA, a concise AI assistant running on the user's Mac. "
                "Answer in 1-3 short sentences suitable for speaking aloud. "
                "No markdown, no bullet points — plain speech only."
            ),
            messages=[{"role": "user", "content": text}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        log.error("Claude API error: %s", e)
        return "I encountered an error processing that request."


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("EVA Voice Module starting on port %d", PORT)
    # Load Whisper eagerly in background to warm it up
    threading.Thread(target=get_whisper_model, daemon=True, name="whisper-warmup").start()
    # Start wake word listener
    start_wake_word_listener()
    yield
    log.info("EVA Voice Module shutting down")


app = FastAPI(
    title="EVA Voice Module",
    version="1.0.0",
    description="Always-on voice interface for EVA",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class SpeakRequest(BaseModel):
    text: str


class CommandRequest(BaseModel):
    text: str


class CommandResponse(BaseModel):
    command: str
    response: str
    spoken: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "module": "voice", "port": PORT}


@app.get("/status")
async def status():
    with _state_lock:
        return dict(_state)


@app.post("/speak")
async def speak_endpoint(req: SpeakRequest):
    """Command Center can POST here to make EVA speak any text."""
    threading.Thread(target=speak, args=(req.text,), daemon=True).start()
    return {"status": "speaking", "text": req.text}


@app.post("/voice/command", response_model=CommandResponse)
async def voice_command(req: CommandRequest):
    """Process a text command programmatically (text in → response + spoken)."""
    text = req.text.strip()
    if not text:
        return CommandResponse(command="", response="Empty command.", spoken=False)

    set_state(last_command=text)

    # Route in thread to avoid blocking event loop
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, route_command, text)

    set_state(last_response=response)
    threading.Thread(target=speak, args=(response,), daemon=True).start()

    return CommandResponse(command=text, response=response, spoken=True)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Real-time state stream for Command Center."""
    await ws.accept()
    async with _ws_lock:
        _ws_clients.append(ws)

    # Send current state immediately on connect
    with _state_lock:
        await ws.send_text(json.dumps(_state))

    try:
        while True:
            # Keep connection alive; state is pushed from set_state()
            await asyncio.sleep(5)
            await ws.send_text(json.dumps({"ping": True}))
    except WebSocketDisconnect:
        async with _ws_lock:
            if ws in _ws_clients:
                _ws_clients.remove(ws)
    except Exception:
        async with _ws_lock:
            if ws in _ws_clients:
                _ws_clients.remove(ws)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "voice_service:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
