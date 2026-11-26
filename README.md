# Comfort Chairs — Autonomous AI Sales Voice Agent (Aria)

## Problem & Business Value
Showroom inquiries often arrive after hours or during peak periods, causing slow lead response, missed bookings, and high SDR overhead. **Aria** is a 24/7 bilingual (English & Hindi) AI voice sales agent that qualifies leads, answers catalog/policy questions, and books showroom visits directly into MySQL (acting as the CRM).

## What Is Implemented
- **Voice I/O:** Groq `whisper-large-v3` STT (with `.webm`/`.wav` support and silence filtering) and `edge-tts` (`en-IN-NeerjaNeural` / `hi-IN-SwaraNeural`) TTS.
- **Agent & RAG:** `qwen/qwen3.8-27b` via Groq with 4-round tool calling (`search_knowledge`, `save_lead`, `check_availability`, `book_appointment`) backed by ChromaDB (`paraphrase-multilingual-MiniLM-L12-v2`).
- **CRM & Summaries:** MySQL connection pool (`db.py`) with atomic slot booking (`UPDATE ... WHERE is_booked=0`), post-call LLM summarization (`summarize_call.py`), and session memory (`session_store.py`). MySQL acts as the CRM.

## What Is Designed (Not Built)
- External CRM webhooks (HubSpot/Salesforce), Twilio/SIP telephony bridge, Redis session store, Kafka/Celery async write queue, and Kubernetes autoscaling.

## Architecture Summary
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/Architecture_Diagram.pdf](docs/Architecture_Diagram.pdf).

## Hands-Free Mode & Fallback UI
- **Primary (Hands-Free Web UI):** `uvicorn server:app --port 8000` (open `http://127.0.0.1:8000` — uses Web Audio API VAD + half-duplex echo control).
- **Fallback UI:** `streamlit run app.py` (push-to-talk).

## Setup (Tested)
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # add GROQ_API_KEY and MYSQL_PASSWORD
python setup_db.py
python seed_slots.py
python build_index.py
uvicorn server:app --port 8000
```

## 2-Minute Demo Script
1. Click **Start call**; Aria greets you in English.
2. Ask in English: *"I need an ergonomic office chair for 8 hours under 15,000 rupees."* (RAG retrieval).
3. Switch to Hindi: *"कल के लिए कौन-से स्लॉट खाली हैं?"* (multilingual memory + `check_availability`).
4. Give name and 10-digit phone, confirm the read-back, and pick a slot (`save_lead` + `book_appointment`).
5. Click **End call**; view summary, sentiment, and live MySQL rows.

## Scalability & Security
- **Scalability:** Stateless FastAPI workers behind a load balancer, Redis for shared session state, async queue for DB/summaries, and MySQL read replicas (design only).
- **Security:** Parameterized SQL (`%s`), `.env` secrets (untracked), backend-injected `session_id`, phone/date validation; TLS/SRTP, rate limiting, and consent prompts are production-only.

## Unit Economics (Formula)
$$\text{Cost per minute} = \text{STT}_{\text{min}} + \text{LLM}_{\text{min}} + \text{TTS}_{\text{min}} + \text{Telephony}_{\text{min}} + \frac{\text{Infra}_{\text{month}}}{\text{Total Minutes}_{\text{month}}}$$
