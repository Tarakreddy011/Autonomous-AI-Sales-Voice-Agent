"""
Streamlit Application: Autonomous Sales Voice Agent UI (Step 3: RAG & Tool Calling)
Integrates STT -> LLM with Contextual History & ChromaDB Tool Calling -> TTS.
"""

import uuid
import hashlib
import streamlit as st
import session_store
import db
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

if "latest_timings" not in st.session_state:
    st.session_state.latest_timings = None

if "latest_retrieved_chunks" not in st.session_state:
    st.session_state.latest_retrieved_chunks = []

# Header & Session Status
st.title("🪑 Comfort Chairs - Sales Voice Agent")
st.caption("Step 4: Lead Qualification, Showroom Booking & MySQL Persistence")

# Live Database Sidebar for Interview Demonstration
with st.sidebar:
    st.subheader("📊 Database (Live)")
    st.caption("Auto-refreshes after each turn. For demonstration.")
    
    try:
        leads_data = db.get_recent_table_rows("leads", limit=3)
        st.write("**Leads:**")
        if leads_data:
            st.dataframe(leads_data, use_container_width=True)
        else:
            st.caption("No leads recorded yet.")
            
        appts_data = db.get_recent_table_rows("appointments", limit=3)
        st.write("**Appointments:**")
        if appts_data:
            st.dataframe(appts_data, use_container_width=True)
        else:
            st.caption("No appointments booked yet.")

        slots_data = db.get_recent_table_rows("availability_slots", limit=6)
        st.write("**Showroom Slots (Upcoming):**")
        if slots_data:
            st.dataframe(slots_data, use_container_width=True)
    except Exception as e:
        st.warning(f"Database connection: {e}")
        st.caption("Ensure MySQL is running and MYSQL_PASSWORD in .env is set.")

# Display Session ID badge
with st.expander("Debug", expanded=False):
    cfg = db.get_db_config()
    st.write("**DB Backend**: " + cfg.get("backend", "unknown"))
    if cfg.get("backend") == "MySQL":
        st.write(f"Host: {cfg.get('host')}\nPort: {cfg.get('port')}\nDatabase: {cfg.get('database')}\nUser: {cfg.get('user')}")
    else:
        st.write(f"SQLite path: {cfg.get('sqlite_path')}")
    try:
        with open('debug.log', 'r') as f:
            lines = f.readlines()[-20:]
            st.code(''.join(lines))
    except Exception as e:
        st.write("No debug log available.")
# Display Session ID badge
col_session, col_action = st.columns([2, 1])
with col_session:
    st.info(f"**Active Caller Session:** `{st.session_state.session_id}`")
with col_action:
    if st.session_state.call_active:
        if st.button("🔴 End Call", use_container_width=True, type="secondary"):
            # Summarize the conversation before ending
            session_id = st.session_state.session_id
            msgs = session_store.get_messages(session_id)
            summary_data = None

            # Edge case: no messages or only greeting
            if not msgs or len(msgs) <= 1:
                st.info("No conversation to summarise (only greeting).")
            else:
                # Build transcript for LLM
                transcript = "\n".join([f"{m['role']}: {m['content']}" for m in msgs])
                try:
                    from groq import Groq
                    import json, os, logging
                    from prompts import SUMMARIZE_PROMPT
                    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                    response = client.chat.completions.create(
                        model=os.getenv("GROQ_CHAT_MODEL", "qwen/qwen3.8-27b"),
                        messages=[
                            {"role": "system", "content": SUMMARIZE_PROMPT},
                            {"role": "user", "content": transcript},
                        ],
                        temperature=0.0,
                        max_tokens=300,
                    )
                    raw = response.choices[0].message.content
                except Exception as e:
                    st.error(f"Failed to call LLM for summary: {e}")
                    raw = ""

                # Strip possible markdown fences
                def _strip_fences(text: str) -> str:
                    if text.startswith("```"):
                        lines = text.splitlines()
                        if lines and lines[0].strip().startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].strip().startswith("```"):
                            lines = lines[:-1]
                        return "\n".join(lines).strip()
                    return text.strip()

                cleaned = _strip_fences(raw)
                try:
                    parsed = json.loads(cleaned)
                except Exception as e:
                    logging.warning(f"Summary JSON parse failed: {e}")
                    parsed = {}

                # Validation with defaults
                def _validate(data: dict) -> dict:
                    defaults = {
                        "summary": None,
                        "sentiment": "Neutral",
                        "lead_status": "Needs Follow-up",
                        "customer_name": None,
                        "customer_phone": None,
                        "requirement": None,
                        "budget": None,
                        "appointment_booked": False,
                        "next_action": None,
                    }
                    allowed_sentiment = {"Positive", "Neutral", "Negative"}
                    allowed_lead = {"Willing", "Not Willing", "Needs Follow-up"}
                    merged = {**defaults, **data}
                    if merged["sentiment"] not in allowed_sentiment:
                        merged["sentiment"] = "Neutral"
                    if merged["lead_status"] not in allowed_lead:
                        merged["lead_status"] = "Needs Follow-up"
                    merged["appointment_booked"] = bool(merged["appointment_booked"]) 
                    return merged

                summary_data = _validate(parsed)

                # Save to DB idempotently
                from db import execute_read, execute_write
                existing = execute_read(
                    "SELECT id FROM call_summaries WHERE session_id = %s", (session_id,)
                )
                if not existing:
                    insert_q = """
                        INSERT INTO call_summaries (
                            session_id, summary, sentiment, lead_status, next_action
                        ) VALUES (%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                            summary      = VALUES(summary),
                            sentiment    = VALUES(sentiment),
                            lead_status  = VALUES(lead_status),
                            next_action  = VALUES(next_action)

                        """
                    execute_write(
                        insert_q,
                        (
                            session_id,
                            summary_data.get("summary"),
                            summary_data.get("sentiment"),
                            summary_data.get("lead_status"),
                            summary_data.get("customer_name"),
                            summary_data.get("customer_phone"),
                            summary_data.get("requirement"),
                            summary_data.get("budget"),
                            int(summary_data.get("appointment_booked")),
                            summary_data.get("next_action"),
                        ),
                    )
                # Update lead status if lead exists
                execute_write(
                    "UPDATE leads SET lead_status = %s WHERE session_id = %s",
                    (summary_data.get("lead_status"), session_id),
                )

            # Show summary card if we have data
            if summary_data:
                st.subheader("📄 Call Summary")
                st.write(f"**Summary:** {summary_data.get('summary') or '—'}")
                st.write(f"**Sentiment:** {summary_data.get('sentiment')}")
                st.write(f"**Lead status:** {summary_data.get('lead_status')}")
                st.write(f"**Next action:** {summary_data.get('next_action') or '—'}")
                booked = summary_data.get('appointment_booked')
                st.write(f"**Appointment booked:** {'Yes' if booked else 'No'}")

            # Clear session and reset UI
            session_store.clear_session(session_id)
            st.session_state.call_active = False
            st.session_state.last_processed_hash = None
            st.session_state.latest_audio_reply = None
            st.session_state.latest_timings = None
            st.session_state.latest_retrieved_chunks = []
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
            st.session_state.latest_retrieved_chunks = []
            st.session_state.latest_timings = {
                "stt": 0.0,
                "llm": 0.0,
                "tts": tts_time,
                "total": tts_time,
                "is_greeting": True
            }
            st.session_state.call_active = True
            st.rerun()
            
    with col_hi:
        if st.button("🟢 Start Call (हिंदी)", use_container_width=True, type="primary"):
            greeting = GREETINGS["hi"]
            session_store.clear_session(st.session_state.session_id)
            session_store.append_message(st.session_state.session_id, "assistant", greeting)
            audio_bytes, tts_time = text_to_speech(greeting, "hi")
            st.session_state.latest_audio_reply = audio_bytes
            st.session_state.latest_retrieved_chunks = []
            st.session_state.latest_timings = {
                "stt": 0.0,
                "llm": 0.0,
                "tts": tts_time,
                "total": tts_time,
                "is_greeting": True
            }
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
            if t.get("is_greeting"):
                st.caption("ℹ️ *Initial greeting is pre-scripted. Real-time STT & LLM timings will appear on your first spoken turn.*")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("STT (Whisper)", f"{t['stt']}s")
            c2.metric("LLM + RAG (Groq)", f"{t['llm']}s")
            c3.metric("TTS (edge-tts)", f"{t['tts']}s")
            c4.metric("Total Latency", f"{t['total']}s")

    # B2. Retrieved Knowledge (RAG Proof)
    with st.expander("🔍 Retrieved Knowledge (RAG Proof)", expanded=False):
        chunks = st.session_state.get("latest_retrieved_chunks", [])
        if chunks:
            st.write(f"**Found {len(chunks)} relevant chunks in ChromaDB for this turn:**")
            for idx, c in enumerate(chunks, 1):
                name = c.get("metadata", {}).get("name", "Item")
                category = c.get("metadata", {}).get("category", "")
                score = c.get("score", 0.0)
                st.markdown(f"**{idx}. {name}** `[{category}]` *(Similarity: `{score}`)*")
                st.text(c.get("content", ""))
        else:
            st.caption("No catalog lookup was required for the last turn.")

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
                            # 2. LLM Reasoning + RAG Tool Calling
                            reply_text, llm_time, retrieved_chunks = respond(
                                session_id=st.session_state.session_id,
                                user_text=transcript,
                                detected_language=detected_lang
                            )

                            # 3. TTS Synthesis
                            reply_audio, tts_time = text_to_speech(reply_text, detected_lang)

                            # 4. Update session state with real metrics
                            total_time = round(stt_time + llm_time + tts_time, 2)
                            st.session_state.latest_audio_reply = reply_audio
                            st.session_state.latest_retrieved_chunks = retrieved_chunks
                            st.session_state.latest_timings = {
                                "stt": stt_time,
                                "llm": llm_time,
                                "tts": tts_time,
                                "total": total_time,
                                "is_greeting": False
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
