# Interview Preparation Guide — Comfort Chairs AI Voice Agent (Aria)

## 1. What We Built & 60-Second Pitch

**What we built (3 sentences):**
We built **Aria**, an autonomous bilingual (English and Hindi) AI voice sales agent for Comfort Chairs that talks hands-free in the browser. It listens via Web Audio API voice activity detection, transcribes speech with Groq Whisper, reasons over a ChromaDB product catalog and MySQL database using LLM tool calling, and replies aloud using `edge-tts`. Every call qualifies the lead, books showroom slots atomically in MySQL, and saves a post-call summary with sentiment analysis.

**60-Second Pitch:**
> "Comfort Chairs loses leads when customers call after hours or when staff are busy. I built **Aria**, a hands-free bilingual voice sales agent in Python, FastAPI, and MySQL. When a caller speaks in English or Hindi, the browser detects speech locally using Web Audio API RMS thresholds and sends `speech.webm` to FastAPI. Groq's Whisper Large v3 transcribes it and detects the language; then a Groq-hosted LLM (`qwen/qwen3.8-27b`) runs a 4-round tool-calling loop with ChromaDB RAG for accurate catalog/policy answers and MySQL for lead capture and atomic showroom slot booking. Aria replies in the caller's language via `edge-tts` while the browser enforces half-duplex echo control so Aria never hears herself. When the call ends, the transcript is summarized with sentiment and lead status, and MySQL acts as the live CRM."

---

## 2. How We Built It (Step by Step)

1. **Step 1 (`03f00b8`) — Thin Voice Loop:** Built `voice_agent.py` with Groq Whisper STT, `edge-tts` (`en-IN-NeerjaNeural`, `hi-IN-SwaraNeural`), silence hallucination filtering, and Windows `WindowsSelectorEventLoopPolicy` fix.
2. **Step 2 (`5e94b29`) — LLM Brain & Memory:** Added `session_store.py` (per-session message history, trimmed to `MAX_HISTORY_MESSAGES = 12`), `prompts.py` (Aria's persona, English/Hindi mirroring, phone read-back rule), and `respond()`.
3. **Step 3 (`b3dbf99`) — Multilingual RAG:** Added `data/catalog.json`, `data/faqs.json`, `build_index.py`, and `knowledge_base.py` using ChromaDB + `paraphrase-multilingual-MiniLM-L12-v2` so `search_knowledge` retrieves exact prices and specs.
4. **Step 4 (`45130d3`) — MySQL CRM & Atomic Booking:** Built `db.py` with `MySQLConnectionPool`, `setup_db.py`, `seed_slots.py`, and `tools.py` (`save_lead`, `check_availability`, `book_appointment` using `UPDATE ... WHERE is_booked = 0`).
5. **FastAPI Hands-Free UI (`server.py`, `static/index.html`, `summarize_call.py`):** Replaced push-to-talk Streamlit reruns with a FastAPI backend and a hands-free browser UI using Web Audio API VAD and half-duplex playback, keeping `app.py` as the fallback UI.
6. **Hardening & Verification:** Fixed `speech_to_text` `.webm` filename forwarding, `/api/turn` tuple unpacking, duplicate LLM call in `respond()`, `summarize_call.py` persistence, MySQL pool sizing (`pool_size=15`), and `"Did not catch that"` feedback in `static/index.html`.

---

## 3. Tech Stack Table

| Component | Technology (Real) | Why We Chose It | Production Alternative |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python 3.13 | Fast prototyping, rich AI/DB ecosystem | Python 3.12/3.13 on Linux containers |
| **Primary Web API** | FastAPI `0.165.0` + Uvicorn `0.54.0` | Async-ready, clean multipart upload, serves static UI | FastAPI behind Nginx / Envoy + Gunicorn/Uvicorn workers |
| **Fallback UI** | Streamlit `>=1.37.0` (`app.py`) | Rapid prototyping & live DB sidebar | Internal ops dashboard (React/Next.js) |
| **Browser Audio / VAD** | Web Audio API + `MediaRecorder` (`static/index.html`) | Zero-dependency hands-free speech detection & half-duplex | WebRTC / LiveKit / Daily.co |
| **STT** | Groq `whisper-large-v3` (`groq==1.7.0`) | Sub-second multilingual (EN/HI) transcription | Streaming Deepgram Nova-2 or self-hosted Whisper |
| **LLM** | Groq `qwen/qwen3.8-27b` (`GROQ_CHAT_MODEL`) | Fast latency, Hindi fluency, reliable tool calling | Multi-provider LLM gateway with fallback |
| **TTS** | `edge-tts==7.3.1` (`en-IN-NeerjaNeural`, `hi-IN-SwaraNeural`) | Natural Indian English & Hindi voices, free for MVP | ElevenLabs / Cartesia / Azure Neural TTS (streaming) |
| **RAG / Vector DB** | ChromaDB `1.5.9` + `sentence-transformers==6.3.0` (`paraphrase-multilingual-MiniLM-L12-v2`) | Local persistent vector store with multilingual embeddings | Qdrant / Milvus / pgvector + dedicated embedding service |
| **Database / CRM** | MySQL 8.0 (`mysql-connector-python==26.10.0`) | ACID transactions for atomic slot booking | Managed MySQL primary + read replicas + ProxySQL |
| **Config** | `python-dotenv==1.2.4` | Keeps secrets out of code | AWS Secrets Manager / Vault |

---

## 4. System Architecture & How One Voice Turn Flows

1. **Browser (`static/index.html`):** `loop()` reads RMS mic level via `analyser.getFloatTimeDomainData(buf)`. When `lv > thr` for `speechStartMs` (120 ms), `startRec()` records `audio/webm`. After `endSilenceMs` (1000 ms) of quiet, `onRecStop()` POSTs `session_id` and `speech.webm` to `/api/turn`.
2. **API (`server.py` -> `api_turn`):** Reads `audio_bytes` and `upload_filename`, calls `speech_to_text(audio_bytes, filename=upload_filename)`.
3. **STT (`voice_agent.py` -> `speech_to_text`):** Sends `(filename, audio_bytes)` to Groq `whisper-large-v3`, filters `no_speech_prob > 0.6` and `SILENCE_HALLUCINATIONS`, maps language to `"hi"` or `"en"`. If empty, `/api/turn` returns `{"ignored": true}` and the UI shows *"Did not catch that, please try again"* for 2 seconds.
4. **Agent (`voice_agent.py` -> `respond`):** Appends user text to `session_store`, builds system prompt + last 12 messages, and runs up to 4 tool-calling rounds via `execute_tool_call()` in `tools.py` (`search_knowledge`, `save_lead`, `check_availability`, `book_appointment`).
5. **TTS (`voice_agent.py` -> `text_to_speech`):** Calls `_synthesize_edge_tts(reply_text, voice)` in a `ThreadPoolExecutor` and returns MP3 bytes.
6. **Playback (`static/index.html`):** `playB64()` plays the base64 MP3 while mic recording is paused (half-duplex), then waits `afterSpeakMs` (350 ms) before `beginListening(false)`.

---

## 5. Five Core Concepts (Simple Explanations + Analogies)

1. **STT & TTS:** Speech-to-Text converts spoken audio waves into text; Text-to-Speech converts the AI's reply text back into natural speech. *Analogy:* A court stenographer typing what you say (STT) and a newsreader reading the reply script aloud (TTS).
2. **RAG (Chunking, Embeddings, Retrieval):** Instead of stuffing the whole catalog into the prompt, we split it into small chunks, convert each chunk's meaning into a numeric vector (embedding), and retrieve only the top-4 closest chunks per question. *Analogy:* Looking up the exact page in a product binder using an index instead of memorizing the whole binder.
3. **Tool / Function Calling:** The LLM outputs a structured JSON request to run a Python function (like `check_availability` or `book_appointment`) instead of guessing facts or writing SQL itself. *Analogy:* A receptionist asking the back-office clerk to check the appointment ledger before promising a time.
4. **Conversation Memory with Session IDs:** Each caller gets a UUID `session_id` that keys their message list in `session_store.py` (trimmed to the last 12 messages) and links their `leads` and `call_summaries` rows in MySQL. *Analogy:* A customer's call folder on the desk so you remember what they asked two minutes ago without mixing them up with another caller.
5. **VAD & Half-Duplex Echo Control:** Voice Activity Detection measures mic volume against calibrated room noise to auto-start and auto-stop recording; half-duplex ignores the mic while Aria is speaking so she doesn't transcribe her own voice. *Analogy:* A walkie-talkie that automatically keys the mic when you speak and mutes the mic while the other person's speaker is playing.

---

## 6. Challenges We Faced & How We Solved Them (Verified)

1. **Silent SQLite fallback (`db.py`):**
   - *Symptom:* Data went into `local.db` while MySQL stayed empty.
   - *Root Cause:* Earlier fallback logic silently fell back to SQLite.
   - *Fix:* Made `db.py` MySQL-only with `MySQLConnectionPool` and loud errors on missing env vars or connection failure.
   - *Learned:* Never hide database connection failures behind silent fallbacks.
2. **Summary column mismatch & placeholder count (`app.py`, `summarize_call.py`, `test_db.py`):**
   - *Symptom:* `ProgrammingError: Unknown column` / `Not all parameters were used`.
   - *Root Cause:* `call_summaries` in MySQL has `(session_id, summary, sentiment, lead_status, next_action)`, while an older script used `?` placeholders and non-existent columns (`appointment_booked`, `customer_name`).
   - *Fix:* Aligned `summarize_call.py`, `db.py`, and `test_db.py` to the real MySQL schema and `%s` placeholders.
   - *Learned:* Always `DESCRIBE` the live table and test every SQL statement.
3. **Broken `/api/turn` tuple unpacking & `.wav` hardcoding (`server.py`, `voice_agent.py`):**
   - *Symptom:* Browser orb went `Hearing you` -> `Thinking` -> `Listening` silently.
   - *Root Cause:* `speech_to_text()` returned a 3-tuple `(transcript, lang, elapsed)` while `server.py` called `.get("text")`, yielding `""` and `ignored: true`; `speech_to_text()` also hardcoded `"caller_audio.wav"` for `.webm` audio.
   - *Fix:* Unpacked the tuple in `server.py`, added `filename` param to `speech_to_text()`, and added a 2s *"Did not catch that"* toast in `static/index.html`.
   - *Learned:* Test the exact return types across module boundaries and surface ignored states in the UI.
4. **Duplicate LLM call in `respond()` (`voice_agent.py`):**
   - *Symptom:* Double token usage and 429 rate-limit timeouts during multi-turn calls.
   - *Root Cause:* A second `client.chat.completions.create()` block remained inside the `MAX_TOOL_ROUNDS` loop.
   - *Fix:* Removed the duplicate call and logged exceptions instead of swallowing them.
   - *Learned:* Inspect loops after automated patches and log every exception.
5. **MySQL Pool Exhaustion under Concurrency (`db.py`):**
   - *Symptom:* 10 simultaneous booking attempts threw `PoolError: Failed getting connection; pool exhausted`.
   - *Root Cause:* `pool_size=5` with non-blocking `get_connection()`.
   - *Fix:* Increased `pool_size=15` and added a brief retry loop in `_get_conn()`.
   - *Learned:* Always load-test connection pools with concurrent threads.
6. **MySQL JSON serialization & `tts()` tuple (`server.py`):**
   - *Symptom:* `/api/db` failed on `datetime`/`timedelta` objects and `tts()` returned `(bytes, float)`.
   - *Root Cause:* `mysql-connector` returns `date`/`timedelta` objects; `tts()` returns a tuple.
   - *Fix:* Added `_safe()` (`json.dumps(..., default=str)`) and `_audio_bytes()` in `server.py`.
   - *Learned:* Normalize boundary types at the API layer.
7. **Half-duplex & AudioContext calibration (`static/index.html`):**
   - *Symptom:* Suspended `AudioContext` reads silence; Aria's greeting could pollute noise calibration or trigger self-echo.
   - *Root Cause:* Browsers suspend `AudioContext` until gesture, and speaker playback bleeds into mic.
   - *Fix:* Explicit `ctx.resume()`, 450 ms `calibrateDelayMs`, `afterSpeakMs` pause, and `state !== "listening"` gate in `loop()`.
   - *Learned:* Voice UIs need explicit state gating around playback.

---

## 7. Requirements Traceability & Endpoints

See the Requirements Traceability Table and Endpoints Table in the project's Final Report (and `docs/ARCHITECTURE.md`). Every requirement is mapped directly to `server.py`, `voice_agent.py`, `tools.py`, `knowledge_base.py`, `db.py`, `summarize_call.py`, `static/index.html`, and `app.py`.

---

## 8. Business Case, Unit Economics & Risks

- **Problem:** Slow lead response, missed after-hours inquiries, and high SDR cost per qualified showroom visit.
- **Workflow:** Greet -> Understand needs (RAG) -> Capture lead (`save_lead`) -> Check slots (`check_availability`) -> Book visit (`book_appointment`) -> Summarize (`summarize_call`).
- **Unit Economics Formula:**
  - $\text{Cost/min} = \text{STT/min} + \text{LLM/min} + \text{TTS/min} + \text{Telephony/min} + \frac{\text{Monthly Infra}}{\text{Total Monthly Minutes}}$
  - **Break-even vs. Human SDR:** $\text{Break-even Calls} = \frac{\text{Fixed Monthly AI Infra}}{\text{Human SDR Cost per Call} - \text{Variable AI Cost per Call}}$
- **Risks:** STT mishearing digits (mitigated by spaced digit read-back in `prompts.py` + `normalize_indian_phone()` in `tools.py`), price hallucination (mitigated by `search_knowledge` RAG), code-switching EN/HI (mitigated by multilingual embeddings + Whisper auto-detect), and call recording consent (must add upfront disclosure in production).

---

## 9. Scalability for 1,00,000 Users

- **Sizing:** $\text{Peak Concurrent Calls} = \frac{\text{Calls/day} \times \text{Avg Minutes}}{1440} \times \text{Peak Factor}$.
- **Target Architecture:** Stateless FastAPI/WebSocket workers behind a load balancer, Redis for `session_store`, Kafka/Celery for async DB writes/summaries, sharded Vector DB + separate embedding service, MySQL primary + read replicas, Twilio/SIP, Kubernetes HPA.
- **What already follows these rules in our code:** `session_store.py` is isolated behind `get_messages`/`append_message` (swap to Redis cleanly); `db.py` centralizes all writes in `execute_write` and uses a connection pool; `voice_agent.py` and `tools.py` are completely decoupled from `server.py` and `app.py`.

---

## 10. Security

- **Implemented:** Parameterized SQL (`%s`) everywhere in `db.py`; secrets in `.env` (gitignored); `session_id` injected by `server.py`/`tools.py` (never by the LLM); phone regex validation (`[6-9]\d{9}`) and 7-day date window validation in `tools.py`.
- **Production-Only:** TLS/SRTP encryption, API rate limiting (per-IP/session), cloud Secrets Manager, explicit call-recording consent banner/prompt, PII retention TTL, least-privilege MySQL user (no `root`).

---

## 11. 30 Likely Interview Questions & Short Answers

**Voice**
1. *Why FastAPI instead of Streamlit for hands-free?* Streamlit reruns the whole script on every interaction and lacks continuous Web Audio VAD; FastAPI serves a persistent JS audio loop over REST.
2. *How does your VAD work?* `AnalyserNode` computes RMS loudness; speech starts when `lv > max(0.008, min(0.05, noise * 2.0))` for 120 ms and stops after 1000 ms of quiet.
3. *Why half-duplex?* Ignoring the mic while Aria speaks (`afterSpeakMs = 350`) prevents speaker echo from triggering self-transcription.
4. *How do you handle silence hallucinations?* `speech_to_text` checks Whisper's `no_speech_prob > 0.6` and filters phrases like `"thank you for watching"`, returning `""`.
5. *How would you cut latency below 1 second?* Switch from REST upload-per-turn to streaming WebSockets + streaming STT + sentence-level streaming TTS.

**LLM & Agents**
6. *Why tool calling instead of hardcoded if/else rules?* Natural conversations jump between catalog questions, objections, and booking; tool calling lets the LLM decide when to query RAG or write to DB.
7. *How do you prevent infinite tool loops?* `MAX_TOOL_ROUNDS = 4` caps iterations in `respond()`.
8. *How do you handle empty LLM responses?* A guard checks `not content and not tool_calls` and retries, with a non-empty bilingual fallback at the end of `respond()`.
9. *Why `qwen/qwen3.8-27b`?* Fast inference on Groq, strong Hindi Devanagari output, and reliable OpenAI-compatible tool calling.
10. *How do you add a third language (e.g., Tamil)?* Add `"ta"` to `VOICES` in `voice_agent.py`, update language mapping in `speech_to_text()`, and add a Tamil directive in `respond()`.

**RAG**
11. *How are hallucinated prices prevented?* `prompts.py` instructs Aria to answer product/price questions strictly via `search_knowledge` (ChromaDB).
12. *Why `paraphrase-multilingual-MiniLM-L12-v2`?* It embeds English and Hindi queries into the same vector space so Hindi callers retrieve English catalog items.
13. *What is chunking here?* `build_index.py` indexes each chair model and FAQ as a discrete document with metadata (`name`, `category`, `price`).
14. *How many chunks are retrieved?* `top_k = 4` in `knowledge_base.py`.
15. *What breaks in RAG at scale?* Loading `SentenceTransformer` per worker wastes RAM; move embeddings to a shared inference service and ChromaDB to Qdrant/Milvus.

**Database**
16. *How is double booking prevented?* `book_appointment_atomic` runs `UPDATE availability_slots SET is_booked = 1 WHERE slot_date = %s AND slot_time = %s AND is_booked = 0` and checks `cur.rowcount == 0` inside a transaction.
17. *Why did we remove SQLite fallback?* Silent fallback hid MySQL misconfigurations and caused split-brain data.
18. *Why `pool_size=15` + retry in `_get_conn()`?* Prevents `PoolError` when concurrent requests hit MySQL simultaneously.
19. *What happens if STT mishears a phone number?* Aria reads it back in spaced digits; `normalize_indian_phone()` rejects invalid numbers so the LLM asks again.
20. *How does `save_lead` avoid overwriting earlier fields?* It reads the existing row for `session_id` and only overwrites non-empty fields.

**System Design**
21. *What breaks first at 1,00,000 users?* Groq rate limits (429), local `session_store` dict (lost across workers), MySQL connections, and per-pod embedding RAM.
22. *Why move `session_store` to Redis?* Stateless FastAPI workers cannot share an in-memory Python dict across pods.
23. *Why use a queue (Kafka/Celery) for summaries?* Call summarization is non-blocking post-call work and shouldn't tie up voice worker threads.
24. *How do you size workers?* `(calls/day * avg_minutes / 1440) * peak_factor`.
25. *How would you connect real phone calls?* Add a Twilio Media Streams / SIP WebSocket gateway that streams 8 kHz mulaw audio to/from the FastAPI worker.

**Business**
26. *What is the core ROI?* Instant 24/7 response and automated showroom booking without scaling human SDR headcount.
27. *How is lead qualification tracked?* `lead_status` (`Willing`, `Needs Follow-up`, `Not Willing`) updated by `save_lead`, `book_appointment_atomic`, and `summarize_call`.
28. *How are business insights generated?* `call_summaries` + `leads` + `appointments` queried via `sql/insights.sql`.
29. *What if a user declines?* Aria sets `lead_status='Not Willing'` and closes politely.
30. *What is the biggest operational risk?* Voice recognition errors on numbers/names and regulatory call-recording consent.

---

## 12. 12 Likely Live Coding Change Requests (Exact File & Function)

1. **Add a field to `leads` (e.g., `city`):** `db.py` (`_init_schema`, `save_or_update_lead`) + `tools.py` (`TOOLS_SCHEMA` for `save_lead`, `execute_tool_call`).
2. **Change showroom slot hours:** `seed_slots.py` (slot time list) -> re-run `python seed_slots.py`.
3. **Add a 3rd language:** `voice_agent.py` (`VOICES`, `speech_to_text`, `respond`).
4. **Switch the LLM model:** `.env` (`GROQ_CHAT_MODEL`) or `voice_agent.py` (`GROQ_CHAT_MODEL`) + `summarize_call.py`.
5. **Add a new tool (e.g., `cancel_appointment`):** `tools.py` (`TOOLS_SCHEMA` + `execute_tool_call`) + `db.py` (atomic cancel helper).
6. **Change the greeting:** `server.py` (`api_start` -> `greeting_text`) and `prompts.py` (`GREETINGS`).
7. **Adjust VAD sensitivity / silence timeout:** `static/index.html` (`CFG` object: `marginX`, `minThreshold`, `endSilenceMs`).
8. **Add a product & re-index:** `data/catalog.json` -> run `python build_index.py`.
9. **Change Aria's persona/rules:** `prompts.py` (`get_system_prompt`).
10. **Change summary fields:** `prompts.py` (`SUMMARIZE_PROMPT`) + `summarize_call.py` (`_validate`, `summarize_call`).
11. **Add a new API endpoint (e.g., `/api/health`):** `server.py` (above `app.mount("/", ...)`).
12. **Change silence hallucination filter:** `voice_agent.py` (`SILENCE_HALLUCINATIONS`) and `server.py` (`_SILENCE_PHRASES`).

---

## 13. Known Limitations (State Honestly)

- **In-memory `session_store`:** Stored in a Python dict; restarting `uvicorn` clears active conversation history (only persisted `leads`/`appointments`/`call_summaries` survive in MySQL).
- **LLM tool-call non-determinism:** Occasionally the LLM may acknowledge a booking in text without emitting the `book_appointment` tool call unless the user confirms clearly.
- **Groq free-tier TPM limits:** Rapid parallel requests can hit Groq's 8,000 TPM limit on `qwen/qwen3.8-27b`.
- **Half-duplex only:** Caller cannot barge in while Aria is speaking.
- **No external CRM webhook or telephony:** MySQL acts as the CRM; browser mic only.

---

## 14. Demo Day Checklist

- **Documents & Items (from email):** Laptop + charger, GitHub repository link, printed Architecture Diagram, 2 copies of resume, 2 passport photographs, college ID, academic transcripts + government ID (original + photocopy), formal attire.
- **Backups:** Mobile hotspot ready as internet backup; pre-recorded backup demo video in case of venue Wi-Fi or Groq API outage.
- **Start App in Under 1 Minute:**
  ```powershell
  cd C:\Users\hp\Desktop\Automated_caller_System
  .venv\Scripts\activate
  uvicorn server:app --port 8000
  ```
  Open `http://127.0.0.1:8000` in Chrome/Edge and allow microphone access.
