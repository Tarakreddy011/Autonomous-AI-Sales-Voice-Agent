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
from tools import TOOLS_SCHEMA, execute_tool_call

# Fix for Windows asyncio ProactorBasePipeTransport WinError 10054:
# On Windows, the default ProactorEventLoop throws an unhandled callback error
# when closing WebSockets (edge-tts). WindowsSelectorEventLoopPolicy prevents this.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load environment variables (.env)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Groq Chat Model configuration:
# Verified via API: 'qwen/qwen3.8-27b' offers ~200ms latency, fluent Hindi, and supports tool calling
# (openai/gpt-oss-20b was consuming max_tokens on internal reasoning tokens, leaving content empty)
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "qwen/qwen3.8-27b")
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
    safe_text = text.strip() if text and text.strip() else ("I am listening." if language == "en" else "मैं सुन रही हूँ।")
    
    start_time = time.perf_counter()
    
    # Run in a clean isolated thread to prevent any conflict with Streamlit's event loop
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as executor:
        audio_bytes = executor.submit(
            lambda: asyncio.run(_synthesize_edge_tts(safe_text, voice))
        ).result()
        
    elapsed = time.perf_counter() - start_time
    
    return audio_bytes, round(elapsed, 2)


def respond(session_id: str, user_text: str, detected_language: str = "en") -> tuple[str, float, list]:
    """
    Core Agent reasoning step with RAG Tool Calling:
    1. Records the user's message into the session store.
    2. Builds conversation context with recent history.
    3. Runs an agentic tool-calling loop (up to 3 rounds) using Groq and search_knowledge.
    4. Saves the final assistant reply into the session store.
    
    Returns:
        tuple of (assistant_reply_text: str, elapsed_seconds: float, retrieved_chunks: list)
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
    all_retrieved_chunks = []
    reply_text = ""
    
    # Tool-calling loop: maximum 3 rounds to prevent runaway execution
    MAX_TOOL_ROUNDS = 3
    for round_idx in range(MAX_TOOL_ROUNDS):
        try:
            completion = client.chat.completions.create(
                model=GROQ_CHAT_MODEL,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.6,
                max_tokens=300
            )
            response_msg = completion.choices[0].message
        except Exception as e:
            reply_text = ""
            break

        # Check if the model decided to call a tool
        if response_msg.tool_calls:
            # Append model's assistant message with tool call definitions to conversation working memory
            messages.append(response_msg)
            
            for tool_call in response_msg.tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments
                tool_result_json, chunks = execute_tool_call(func_name, func_args)
                all_retrieved_chunks.extend(chunks)
                
                # Append tool result back to the working conversation list
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": tool_result_json
                })
        else:
            # Model generated its final text response
            raw_content = response_msg.content or ""
            reply_text = raw_content.strip()
            break

    # Absolute fallback guardrail: NEVER let reply_text be empty
    if not reply_text:
        reply_text = (
            "I am checking our chair catalog for you. Could you tell me if you prefer a high-back chair or a medium-back chair?"
            if detected_language == "en"
            else "मैं आपके लिए कैटलॉग देख रही हूँ। क्या आप हाई-बैक या मीडियम-बैक कुर्सी पसंद करेंगे?"
        )
        
    elapsed = time.perf_counter() - start_time
    
    # 4. Save final assistant reply to session store
    if reply_text.strip():
        session_store.append_message(session_id, "assistant", reply_text)
    
    return reply_text, round(elapsed, 2), all_retrieved_chunks

