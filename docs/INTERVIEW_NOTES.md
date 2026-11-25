## 60‑second Pitch
The Comfort Chairs AI Voice Sales Agent automates after‑hours inbound calls: it records the customer's query, uses Groq STT to transcribe, the LLM reasons, captures lead details, checks slot availability, books an appointment atomically, and finally generates a validated JSON summary. All data lands in a MySQL CRM, freeing human SDRs for high‑value tasks while delivering 24/7 coverage.

## 15 Interview Q&A
1. **Why Streamlit?** – Quick UI prototyping, built‑in session state, and easy integration with Python tooling.
2. **How does double‑booking prevention work?** – An atomic `UPDATE … WHERE is_booked = 0` ensures only the first concurrent request succeeds.
3. **What are the failure modes for the LLM/STT APIs?** – Rate‑limit (429), timeout, or malformed response; we back‑off once and show a friendly message.
4. **How is PII handled?** – Phone numbers are masked in logs (only last 4 digits) and stored encrypted in the DB.
5. **Why JSON validation for call summaries?** – Guarantees a stable contract for downstream analytics; malformed output falls back to safe defaults.
6. **Explain the role of `summarize_call`.** – Calls the LLM with a dedicated prompt, parses the JSON, updates `call_summaries`, and updates `lead_status`.
7. **What would you improve for scalability?** – Move to stateless Docker workers, Redis session store, Kafka queue, and sharded ChromaDB (see ARCHITECTURE.md).
8. **How does the app ensure idempotent summary writes?** – Uses a unique `session_id` check before inserting; duplicate End‑Call clicks are ignored.
9. **Describe the logging strategy.** – Timestamped entries with masked PII, written to `app.log` for debugging and audit.
10. **What security headers are set for the API calls?** – TLS is enforced; no custom headers needed beyond Authorization.
11. **How are errors surfaced to the user?** – Inline Streamlit `st.error` messages with clear next‑step instructions.
12. **What testing approach was used for concurrency?** – A Python script launching 10 parallel callers and 20 concurrent bookings (see task list).
13. **Why use MySQL for the CRM?** – Familiar ACID guarantees, easy reporting, and fits the MVP.
14. **How would you add multilingual support?** – Extend the prompt with language detection and route to appropriate LLM model.
15. **What is the biggest limitation of the current MVP?** – Single‑process, SQLite fallback, no distributed session store.

## 10 Live‑Coding Change Requests (file/function)
| # | Request | Target File | Function / Section |
|---|---------|------------|--------------------|
| 1 | Change greeting text to include "Welcome!" | `prompts.py` | `GREETINGS` list |
| 2 | Increase max retry count for API calls to 3 | `app.py` | `MAX_RETRIES` constant |
| 3 | Refactor `book_appointment` to return a boolean instead of tuple | `tools.py` | `book_appointment` |
| 4 | Add a new column `source` to `leads` table | `db.py` | `init_db` schema |
| 5 | Move the summary card UI to a separate Streamlit component | `app.py` | summary rendering block |
| 6 | Replace `print` debugging with `logging.info` | `voice_agent.py` | any debug prints |
| 7 | Add environment variable validation on startup | `setup_db.py` | `load_env` function |
| 8 | Switch from `edge‑tts` to Google Cloud TTS API | `tts_service.py` (new) | TTS wrapper |
| 9 | Expose a FastAPI endpoint for health checks | `app.py` | add `/health` route |
|10| Update README badge URLs to new CI pipeline | `README.md` | badge markdown |

These notes provide ready talking points and concrete code‑change examples for a technical interview.
