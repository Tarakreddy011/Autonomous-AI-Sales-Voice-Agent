"""
Streamlit Application: Autonomous Sales Voice Agent UI (Step 1: Echo Voice Loop)
Provides microphone input, session isolation, latency metrics, and audio playback.
"""

import uuid
import hashlib
import streamlit as st
from voice_agent import speech_to_text, text_to_speech

# Page configuration
st.set_page_config(
    page_title="AI Chair Sales Caller",
    page_icon="🪑",
    layout="centered"
)

# 1. Session Isolation: Each browser tab gets its own unique session_id
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

# 2. State management to prevent Streamlit from reprocessing the same audio on rerun
if "last_processed_hash" not in st.session_state:
    st.session_state.last_processed_hash = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None

# Header & Session Info
st.title("🪑 Furniture Sales Voice Agent")
st.caption("Step 1: Thin End-to-End Voice Loop (Browser Mic -> STT -> TTS Playback)")

# Display Session ID badge
st.info(f"**Caller Session ID:** `{st.session_state.session_id}` (Isolated per browser tab)")

st.write("---")

# 3. Audio Input from Browser Microphone
st.subheader("🎙️ Speak into your microphone")
audio_file = st.audio_input("Record your voice (English or Hindi)")

if audio_file is not None:
    # Read the raw audio bytes
    audio_bytes = audio_file.read()
    
    # Calculate an MD5 hash of the audio bytes
    # This uniquely fingerprints this specific recording
    audio_hash = hashlib.md5(audio_bytes).hexdigest()
    
    # Check if this exact audio was already processed
    if audio_hash != st.session_state.last_processed_hash:
        with st.spinner("Transcribing with Groq Whisper..."):
            try:
                transcript, detected_lang, stt_time = speech_to_text(audio_bytes)
                
                if not transcript:
                    st.warning("⚠️ No speech detected. Please speak closer to your microphone.")
                    st.session_state.last_result = None
                else:
                    # Echo loop: synthesize the transcript back in the detected language
                    with st.spinner("Synthesizing speech with edge-tts..."):
                        tts_bytes, tts_time = text_to_speech(transcript, detected_lang)
                    
                    # Store results in session state
                    st.session_state.last_result = {
                        "transcript": transcript,
                        "language": detected_lang,
                        "stt_time": stt_time,
                        "tts_time": tts_time,
                        "audio_bytes": tts_bytes
                    }
                    st.session_state.last_processed_hash = audio_hash
            except Exception as e:
                st.error(f"❌ Error during voice processing: {str(e)}")
                st.info("Tip: Make sure your GROQ_API_KEY is properly set in the .env file.")

# 4. Display results from session state (persists across reruns cleanly)
if st.session_state.last_result:
    res = st.session_state.last_result
    
    st.write("---")
    st.subheader("📝 Live Call Transcript")
    
    col1, col2 = st.columns(2)
    with col1:
        lang_label = "Hindi (hi-IN)" if res["language"] == "hi" else "English (en-IN)"
        st.metric(label="Detected Language", value=lang_label)
    with col2:
        total_latency = round(res["stt_time"] + res["tts_time"], 2)
        st.metric(label="Total Voice Latency", value=f"{total_latency} s")
        
    st.write(f"**Caller said:** \"{res['transcript']}\"")
    
    # Latency Breakdown
    with st.expander("⏱️ Latency Breakdown", expanded=True):
        st.write(f"- **STT (Groq Whisper Large v3):** `{res['stt_time']}s`")
        st.write(f"- **TTS (edge-tts Neural):** `{res['tts_time']}s`")
        
    # Audio Player
    st.subheader("🔊 Agent Voice Echo")
    st.audio(res["audio_bytes"], format="audio/mp3")
