## Business Problem & Value
The showroom receives many inbound calls after business hours. Human SDRs cannot be on‑call 24/7, leading to missed qualified leads and higher acquisition costs. An AI voice sales agent captures leads, qualifies intent, and books appointments automatically, increasing conversion rates while reducing labor expenses.

## End‑to‑End Workflow
1. **Customer speaks** – audio sent to Groq STT.
2. **LLM reasoning** – decides which tool to invoke (knowledge lookup, lead capture, slot check).
3. **Tool calls** – write lead data to MySQL, check/atomically book an `availability_slots` row.
4. **TTS reply** – `edge‑tts` returns audio.
5. **Call end** – `summarize_call` generates a validated JSON summary stored in `call_summaries`.

## Why AI Voice Helps
- **24/7 availability** – no staffing gaps.
- **Scalable parallelism** – the same model can handle many simultaneous callers.
- **Consistent qualification** – same questions, no human error.
- **Structured CRM data** – leads and appointments are stored in a relational DB for downstream sales pipelines.

## Unit‑Economics Formula
```
Cost per qualified lead = (Cost per minute × Avg call minutes) / Conversion rate
```
- **Cost per minute** – sum of STT, LLM, TTS, DB, and infrastructure (see `README.md`).
- **Avg call minutes** – typical conversation length (≈ 3 min).
- **Conversion rate** – percentage of calls that result in a booked appointment (target > 30%).

## Break‑Even Analysis (illustrative)
| Metric | Value |
|--------|-------|
| Monthly calls | 1,000 |
| Avg minutes per call | 3 |
| Cost per minute | $0.0028 |
| Total monthly cost | $8,400 |
| Desired qualified leads per month | 300 |
| Max acceptable cost per lead | $28 |

Replace placeholder numbers with your actual metrics to evaluate profitability.

## Risks & Mitigations
- **Speech errors** – ask for confirmation before saving phone numbers.
- **LLM hallucinations** – restrict tool use to verified functions; fallback to manual human handover.
- **Regulatory compliance** – store consent logs, allow opt‑out, retain recordings for required periods.

*All statements reflect the current implementation; production‑only items are marked as such.*