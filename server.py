import uuid
import base64
import os
import json as _json
import time as _time
import logging as _logging

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db import execute_write, execute_read
from voice_agent import speech_to_text as stt, respond, text_to_speech as tts
from summarize_call import summarize_call

# ── Logging setup ──────────────────────────────────────────────────────────────
_logging.basicConfig(
    level=_logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        _logging.StreamHandler(),
        _logging.FileHandler("debug.log", encoding="utf-8"),
    ],
)
_log = _logging.getLogger("voice_api")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SILENCE_PHRASES = {"", "you", "thanks for watching", "thanks for watching!"}


def generate_session_id() -> str:
    return str(uuid.uuid4())


def _audio_bytes(result):
    """tts() returns (bytes, float). Always extract the bytes."""
    if isinstance(result, (bytes, bytearray)):
        return bytes(result)
    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, (bytes, bytearray)):
                return bytes(item)
    return b""


def _safe(data):
    """Make MySQL rows JSON-safe: dates, times and timedeltas become strings."""
    return _json.loads(_json.dumps(data, default=str))


def _lang(code):
    return "hi" if str(code or "").lower().startswith("hi") else "en"


@app.post("/api/start")
def api_start():
    session_id = generate_session_id()
    greeting_text = "Hello, welcome to Comfort Chairs. How can I help you today?"
    try:
        tts_result = tts(greeting_text, language="en")
        audio_b64 = base64.b64encode(_audio_bytes(tts_result)).decode("utf-8")
        _log.info("api_start: session=%s greeting_audio_bytes=%d", session_id, len(_audio_bytes(tts_result)))
    except Exception:
        _log.exception("TTS failed for greeting")
        audio_b64 = ""
    return JSONResponse(content={
        "session_id": session_id,
        "greeting_text": greeting_text,
        "greeting_audio": audio_b64,
    })


@app.post("/api/turn")
def api_turn(session_id: str = Form(...), audio: UploadFile = File(...)):
    try:
        t0 = _time.perf_counter()

        audio_bytes = audio.file.read()
        audio_size = len(audio_bytes)
        # Use the uploaded filename so Groq picks the right decoder (webm, wav, mp3…)
        upload_filename = getattr(audio, "filename", None) or "speech.webm"
        _log.info("api_turn: session=%s upload_filename=%s audio_bytes=%d",
                  session_id, upload_filename, audio_size)

        # ── STT ───────────────────────────────────────────────────────────────
        # stt() returns a TUPLE: (transcript: str, language: str, elapsed: float)
        transcript, language, stt_elapsed = stt(audio_bytes, filename=upload_filename)
        t1 = _time.perf_counter()
        _log.info("api_turn: transcript=%r language=%s stt_elapsed=%.2fs",
                  transcript, language, stt_elapsed)

        # ── Silence guard ─────────────────────────────────────────────────────
        if transcript.lower().strip(" .!") in _SILENCE_PHRASES:
            _log.info("api_turn: IGNORED (empty/silence transcript) session=%s", session_id)
            return JSONResponse(content={"ignored": True, "reason": "empty_transcript"})

        # ── LLM ───────────────────────────────────────────────────────────────
        reply_text, llm_elapsed, _ = respond(session_id, transcript, detected_language=language)
        t2 = _time.perf_counter()
        _log.info("api_turn: reply_text_len=%d llm_elapsed=%.2fs", len(reply_text), llm_elapsed)

        # ── TTS ───────────────────────────────────────────────────────────────
        tts_result = tts(reply_text, language=language)
        reply_audio = _audio_bytes(tts_result)
        reply_audio_b64 = base64.b64encode(reply_audio).decode("utf-8")
        t3 = _time.perf_counter()
        _log.info("api_turn: reply_audio_bytes=%d tts_elapsed=%.2fs total=%.2fs",
                  len(reply_audio), t3 - t2, t3 - t0)

        timings = {
            "stt": round(t1 - t0, 2),
            "llm": round(t2 - t1, 2),
            "tts": round(t3 - t2, 2),
            "total": round(t3 - t0, 2),
        }
        _log.info("api_turn: timings=%s", timings)

        return JSONResponse(content={
            "transcript": transcript,
            "language": language,
            "reply_text": reply_text,
            "reply_audio": reply_audio_b64,
            "ignored": False,
            "timings": timings,
        })

    except Exception as e:
        _log.exception("api_turn FAILED: session=%s", session_id)
        return JSONResponse(status_code=500, content={"error": "Turn failed: " + str(e)})


@app.post("/api/end")
def api_end(session_id: str = Form(...)):
    try:
        return JSONResponse(content=_safe({"summary": summarize_call(session_id)}))
    except Exception as e:
        _log.exception("api_end failed: session=%s", session_id)
        return JSONResponse(status_code=500, content={"error": "Summary failed: " + str(e)})


@app.get("/api/db")
def api_db():
    try:
        data = {
            "leads": execute_read("SELECT * FROM leads ORDER BY id DESC LIMIT 5"),
            "appointments": execute_read("SELECT * FROM appointments ORDER BY id DESC LIMIT 5"),
            "call_summaries": execute_read("SELECT * FROM call_summaries ORDER BY id DESC LIMIT 5"),
        }
        return JSONResponse(content=_safe(data))
    except Exception as e:
        _log.exception("api_db failed")
        return JSONResponse(status_code=500, content={"error": str(e)})


# Mount static files last
app.mount("/", StaticFiles(directory="static", html=True), name="static")
