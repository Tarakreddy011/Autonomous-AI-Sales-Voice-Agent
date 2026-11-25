"""
Voice Agent: Speech-to-Text (Groq Whisper) and Text-to-Speech (edge-tts).
Handles audio byte streaming, language detection/fallback, and timing metrics.
"""

import os
import sys
import time
import asyncio
from dotenv import load_dotenv
from groq import Groq
import edge_tts

import session_store
from prompts import SYSTEM_PROMPT

# Fix for Windows asyncio ProactorBasePipeTransport WinError 10054:
# On Windows, the default ProactorEventLoop throws an unhandled callback error
# when closing WebSockets (edge-tts). WindowsSelectorEventLoopPolicy prevents this.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load environment variables (.env)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Groq Chat Model configuration:
# Verified via API: 'openai/gpt-oss-20b' offers sub-second latency and supports tool calling
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
MAX_HISTORY_MESSAGES = 12

# Supported voices for edge-tts
# We queried edge-tts directly and selected natural Indian voices:
VOICES = {
    "en": "en-IN-NeerjaNeural",   # Indian English (Female)
    "hi": "hi-IN-SwaraNeural"    # Hindi (Female)
}

# Known Whisper hallucinations triggered by microphone silence or faint background hiss
SILENCE_HALLUCINATIONS = {
    "thank you", "thank you.", "thank you very much.",
    "thanks for watching", "thanks for watching.",
    "thank you for watching", "thank you for watching.",
    "thanks", "thanks.", "you", "subtitles by", "bye", "bye."
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
    
    # Check for silence or low-confidence hallucination:
    # 1. Check Whisper's internal no_speech_prob metadata across segments
    is_silence = False
    segments = getattr(response, "segments", []) or []
    if segments:
        no_speech_probs = [
            s.get("no_speech_prob", 0) if isinstance(s, dict) else getattr(s, "no_speech_prob", 0)
            for s in segments
        ]
        if no_speech_probs and (sum(no_speech_probs) / len(no_speech_probs) > 0.6):
            is_silence = True

    # 2. Check if the transcript matches typical silence hallucination phrases
    clean_text = transcript.lower().strip(" .!?,")
    hallucination_set = {h.strip(" .!?,") for h in SILENCE_HALLUCINATIONS}
    if clean_text in hallucination_set:
        is_silence = True

    if is_silence:
        transcript = ""
    
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


def respond(session_id: str, user_text: str, detected_language: str = "en") -> tuple[str, float]:
    """
    Core Agent reasoning step:
    1. Records the user's message into the session store.
    2. Retrieves up to MAX_HISTORY_MESSAGES for conversational context.
    3. Prompts the Groq LLM with system constraints and language matching.
    4. Saves the assistant reply into the session store.
    
    Returns:
        tuple of (assistant_reply_text: str, elapsed_seconds: float)
    """
    client = get_groq_client()
    
    # 1. Save user turn to session history
    session_store.append_message(session_id, "user", user_text)
    
    # 2. Retrieve history and trim to last N messages (prevents context blowout and lowers latency)
    full_history = session_store.get_messages(session_id)
    recent_history = full_history[-MAX_HISTORY_MESSAGES:]
    
    # 3. Dynamic language directive to strictly mirror caller language
    lang_directive = (
        "The customer just spoke Hindi. You must reply strictly in Hindi using Devanagari script."
        if detected_language == "hi"
        else "The customer just spoke English. You must reply strictly in English."
    )
    
    system_message = {
        "role": "system",
        "content": f"{SYSTEM_PROMPT}\n\n[Active Call Rule]: {lang_directive}"
    }
    
    messages = [system_message] + recent_history
    
    start_time = time.perf_counter()
    
    try:
        completion = client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=150
        )
        reply_text = completion.choices[0].message.content.strip()
    except Exception as e:
        reply_text = (
            "I apologize, I am experiencing a brief connection delay. Could you please repeat that?"
            if detected_language == "en"
            else "माफ़ कीजियेगा, कॉल में थोड़ी रुकावट आ गई थी। क्या आप कृपया दोबारा कह सकते हैं?"
        )
        
    elapsed = time.perf_counter() - start_time
    
    # 4. Save assistant reply to session store
    session_store.append_message(session_id, "assistant", reply_text)
    
    return reply_text, round(elapsed, 2)

