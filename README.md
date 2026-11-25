# Comfort Chairs AI Voice Sales Agent – Project Report

## Problem & Business Value
Customer‑service teams miss after‑hours calls, losing sales and increasing SDR costs. An AI voice agent provides 24/7 qualified lead capture, appointment booking, and structured CRM data, reducing missed opportunities and labor overhead.

## What Is Implemented
| Feature | Status |
|---------|--------|
| Voice interaction (STT → LLM → TTS) | ✅ |
| Lead capture (MySQL/SQLite) | ✅ |
| Atomic appointment booking | ✅ |
| Call summarisation (JSON‑validated, idempotent) | ✅ |
| Error handling & retries (STT/LLM/TTS) | ✅ |
| UI with clean cards & width="stretch" | ✅ |
| CRM integration (MySQL tables) | ✅ |
| External CRM sync (Zoho/HubSpot) | *Design‑only* |
| Distributed deployment (Docker/K8s, Redis, Kafka) | *Design‑only* |

## Architecture Summary
See the interactive sidecar diagram **[docs/DIAGRAMS.md](docs/DIAGRAMS.md)** and the placeholder **[docs/Architecture_Diagram.pdf](docs/Architecture_Diagram.pdf)** for the system layout.

## Setup (Windows PowerShell 5.1)
```powershell
# Clone repo
git clone https://github.com/<username>/comfort-chairs-agent.git
cd comfort-chairs-agent

# Virtual env
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Dependencies
pip install -r requirements.txt

# Environment variables (copy .env.example → .env)
copy .env.example .env

# Initialise DB (SQLite fallback)
python -c "import db; db.init_db()"

# Run app
streamlit run app.py
```

## 2‑Minute Demo
1. Open `http://localhost:8501`.
2. Click **Start Call** and speak a product query.
3. Provide name, phone, requirement when asked.
4. Agree to a suggested slot → booking confirmed.
5. Click **End Call** → summary card shows **Willing**, **appointment = true**, **positive** sentiment.

## Scalability
MVP runs a single process with SQLite. Production design (see `docs/ARCHITECTURE.md`) adds stateless workers, Redis session store, Kafka queue, Docker/K8s, and sharded vector DB to handle up to 100 k daily calls.

## Security
- PII (phone) masked in logs (last 4 digits).
- Secrets stored in `.env` (git‑ignored).
- Parameterised SQL queries prevent injection.
- TLS for all external API traffic.

## Cost per Minute (illustrative)
| Component | Approx. USD / min |
|-----------|--------------------|
| Groq STT | $0.0005 |
| Groq LLM | $0.0012 |
| edge‑tts | $0.0008 |
| MySQL (RDS) | $0.0003 |
| **Total** | **≈ $0.0028 /min** |

*(Replace with current rates when budgeting.)*