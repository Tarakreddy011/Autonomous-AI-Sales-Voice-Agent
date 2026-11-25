"""
Voice Agent: Speech-to-Text (Groq Whisper) and Text-to-Speech (edge-tts).
Handles audio byte streaming, language detection/fallback, and timing metrics.
"""

import os
import time
import asyncio
from dotenv import load_dotenv
from groq import Groq
import edge_tts

# Load environment variables (.env)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Supported voices for edge-tts
# We queried edge-tts directly and selected natural Indian voices:
VOICES = {
    "en": "en-IN-NeerjaNeural",   # Indian English (Female)
    "hi": "hi-IN-SwaraNeural"    # Hindi (Female)
}

def get_groq_client() -> Groq:
    """Returns an authenticated Groq client."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        raise ValueError("Valid GROQ_API_KEY missing from .env file!")
    return Groq(api_key=api_key)

def speech_to_text(audio_bytes: bytes) -> tuple[str, str, float]:
    """
    Sends raw audio bytes to Groq Whisper Large v3.
    
    Returns:
        tuple of (transcript: str, detected_language: str, elapsed_seconds: float)
    """
    client = get_groq_client()
    
    start_time = time.perf_counter()
    
    # Send audio bytes in-memory without creating a temporary file on disk.
    # Groq API expects a tuple: (filename, file_bytes)
    response = client.audio.transcriptions.create(
        file=("caller_audio.wav", audio_bytes),
        model="whisper-large-v3",
        response_format="verbose_json"
    )
    
    elapsed = time.perf_counter() - start_time
    
    transcript = response.text.strip() if hasattr(response, "text") else ""
    raw_lang = getattr(response, "language", "en") or "en"
    raw_lang = raw_lang.lower()
    
    # Language filtering:
    # We strictly support English ('en') and Hindi ('hi').
    # If the user speaks Hindi or Hinglish, Whisper identifies it as 'hindi' or 'hi'.
    # If any other language is detected (e.g. noise detected as German or Spanish),
    # we fall back to English because English is the primary store default.
    if "hindi" in raw_lang or raw_lang == "hi":
        language = "hi"
    else:
        language = "en"
        
    return transcript, language, round(elapsed, 2)

async def _synthesize_edge_tts(text: str, voice: str) -> bytes:
    """Internal async helper to stream TTS audio directly into memory."""
    communicate = edge_tts.Communicate(text=text, voice=voice)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)

def text_to_speech(text: str, language: str = "en") -> tuple[bytes, float]:
    """
    Synthesizes speech audio bytes from text using edge-tts.
    
    Args:
        text: The text to be spoken.
        language: 'en' for Indian English, 'hi' for Hindi.
        
    Returns:
        tuple of (audio_bytes: bytes, elapsed_seconds: float)
    """
    voice = VOICES.get(language, VOICES["en"])
    
    start_time = time.perf_counter()
    
    # Run in a clean isolated thread to prevent any conflict with Streamlit's event loop
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as executor:
        audio_bytes = executor.submit(
            lambda: asyncio.run(_synthesize_edge_tts(text, voice))
        ).result()
        
    elapsed = time.perf_counter() - start_time
    
    return audio_bytes, round(elapsed, 2)
