"""
Streamlit Application: Autonomous Sales Voice Agent UI (Step 2: Agent Brain with Memory)
Integrates STT -> LLM with Contextual History -> TTS, with per-call isolation.
"""

import uuid
import hashlib
import streamlit as st
import session_store
from prompts import GREETINGS
from voice_agent import speech_to_text, text_to_speech, respond

# Page setup
st.set_page_config(
    page_title="Comfort Chairs - AI Voice Agent",
    page_icon="🪑",
    layout="centered"
)

# 1. Per-Tab Session State Initialization
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

if "call_active" not in st.session_state:
    st.session_state.call_active = False

if "last_processed_hash" not in st.session_state:
    st.session_state.last_processed_hash = None

if "latest_audio_reply" not in st.session_state:
    st.session_state.latest_audio_reply = None

if "audio_version" not in st.session_state:
    st.session_state.audio_version = 0

if "latest_timings" not in st.session_state:
    st.session_state.latest_timings = None

# Header & Session Status
st.title("🪑 Comfort Chairs - Sales Voice Agent")
st.caption("Step 2: Full Voice Loop with Conversational Memory (STT -> LLM -> TTS)")

# Display Session ID badge
col_session, col_action = st.columns([2, 1])
with col_session:
    st.info(f"**Active Caller Session:** `{st.session_state.session_id}`")
with col_action:
    if st.session_state.call_active:
        if st.button("🔴 End Call", use_container_width=True, type="secondary"):
            session_store.clear_session(st.session_state.session_id)
            st.session_state.call_active = False
            st.session_state.last_processed_hash = None
            st.session_state.latest_audio_reply = None
            st.session_state.audio_version = 0
            st.session_state.latest_timings = None
            # Generate a new session_id for the next caller
            st.session_state.session_id = str(uuid.uuid4())[:8]
            st.rerun()

st.write("---")

# 2. Call Initialization: Opening Greeting
if not st.session_state.call_active:
    st.subheader("📞 Ready to connect with Aria")
    st.write("Click below to simulate an incoming customer call. Aria will greet you first.")
    
    col_en, col_hi = st.columns(2)
    with col_en:
        if st.button("🟢 Start Call (English)", use_container_width=True, type="primary"):
            greeting = GREETINGS["en"]
            session_store.clear_session(st.session_state.session_id)
            session_store.append_message(st.session_state.session_id, "assistant", greeting)
            audio_bytes, tts_time = text_to_speech(greeting, "en")
            st.session_state.latest_audio_reply = audio_bytes
            st.session_state.audio_version += 1
            st.session_state.latest_timings = {"stt": 0.0, "llm": 0.0, "tts": tts_time, "total": tts_time}
            st.session_state.call_active = True
            st.rerun()
            
    with col_hi:
        if st.button("🟢 Start Call (हिंदी)", use_container_width=True, type="primary"):
            greeting = GREETINGS["hi"]
            session_store.clear_session(st.session_state.session_id)
            session_store.append_message(st.session_state.session_id, "assistant", greeting)
            audio_bytes, tts_time = text_to_speech(greeting, "hi")
            st.session_state.latest_audio_reply = audio_bytes
            st.session_state.audio_version += 1
            st.session_state.latest_timings = {"stt": 0.0, "llm": 0.0, "tts": tts_time, "total": tts_time}
            st.session_state.call_active = True
            st.rerun()

# 3. Active Call Interface
if st.session_state.call_active:
    # A. Display Live Agent Audio Player
    if st.session_state.latest_audio_reply:
        st.subheader("🔊 Aria Speaking")
        st.audio(
            st.session_state.latest_audio_reply,
            format="audio/mp3",
            autoplay=True
        )
    
    # B. Timing Breakdown
    if st.session_state.latest_timings:
        t = st.session_state.latest_timings
        with st.expander("⏱️ Latency Metrics", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("STT (Whisper)", f"{t['stt']}s")
            c2.metric("LLM (Groq)", f"{t['llm']}s")
            c3.metric("TTS (edge-tts)", f"{t['tts']}s")
            c4.metric("Total Latency", f"{t['total']}s")

    # C. Microphone Input with STABLE key (prevents tearing down browser MediaStreamRecorder)
    st.write("---")
    st.subheader("🎙️ Speak to Aria")
    audio_file = st.audio_input(
        "Press record, speak, and press stop:",
        key="caller_microphone_stable"
    )

    if audio_file is not None:
        audio_bytes = audio_file.getvalue() if hasattr(audio_file, "getvalue") else audio_file.read()
        
        # Guard against zero-byte empty streams
        if audio_bytes and len(audio_bytes) > 800:
            audio_hash = hashlib.md5(audio_bytes).hexdigest()

            # Process ONLY when a new recording arrives
            if audio_hash != st.session_state.last_processed_hash:
                with st.spinner("Processing voice..."):
                    try:
                        # 1. STT
                        transcript, detected_lang, stt_time = speech_to_text(audio_bytes)

                        if not transcript:
                            st.warning("⚠️ No speech detected. Please speak closer to your microphone.")
                            st.session_state.last_processed_hash = audio_hash
                        else:
                            # 2. LLM Reasoning
                            reply_text, llm_time = respond(
                                session_id=st.session_state.session_id,
                                user_text=transcript,
                                detected_language=detected_lang
                            )

                            # 3. TTS Synthesis
                            reply_audio, tts_time = text_to_speech(reply_text, detected_lang)

                            # 4. Update session state
                            total_time = round(stt_time + llm_time + tts_time, 2)
                            st.session_state.latest_audio_reply = reply_audio
                            st.session_state.audio_version += 1
                            st.session_state.latest_timings = {
                                "stt": stt_time,
                                "llm": llm_time,
                                "tts": tts_time,
                                "total": total_time
                            }
                            st.session_state.last_processed_hash = audio_hash
                            st.rerun()

                    except Exception as e:
                        st.error(f"❌ Error during call processing: {str(e)}")
                        st.session_state.last_processed_hash = audio_hash

    # D. Render Conversation History (Chat Bubbles)
    st.write("---")
    st.subheader("💬 Call Transcript")
    messages = session_store.get_messages(st.session_state.session_id)
    if not messages:
        st.write("*No messages yet in this call.*")
    else:
        for msg in messages:
            content = msg.get("content", "").strip()
            if not content:
                continue  # Never render empty bubbles
            role = msg["role"]
            avatar = "👤" if role == "user" else "🪑"
            label = "Customer" if role == "user" else "Aria (Sales Agent)"
            with st.chat_message(role, avatar=avatar):
                st.markdown(f"**{label}**: {content}")
