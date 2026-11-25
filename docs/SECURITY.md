## Implemented Security Measures
- **TLS** for all external API calls (Groq STT/LLM, edge‑tts).
- **PII masking** in logs – phone numbers stored only with last 4 digits visible.
- **Secrets management** – API keys placed in `.env`, which is listed in `.gitignore`.
- **Parameterized SQL** – all DB queries use placeholders to prevent injection.
- **Input validation** – JSON summary schema validated before DB insert.

## Production‑Only Security (Design)
- **SRTP** for telephony streams (Twilio/SIP) to encrypt voice in‑flight.
- **Database least‑privilege** – separate MySQL user with only `SELECT/INSERT/UPDATE` on required tables.
- **Rate‑limiting & quota enforcement** on LLM/STT calls.
- **Audit logging** – immutable log storage (e.g., CloudWatch) for compliance.
- **Data retention policy** – automatic purge of call recordings after 90 days.
- **Secrets vault** – HashiCorp Vault or GCP Secret Manager for production deployments.

All implemented measures are active in the current codebase; the production‑only items are planned for future scaling.
