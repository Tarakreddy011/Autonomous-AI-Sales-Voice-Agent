import json
import logging
import os
from typing import Any, Dict

from groq import Groq

import session_store
from db import execute_read, execute_write
from prompts import SUMMARIZE_PROMPT


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _validate(data: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        "summary": None,
        "sentiment": "Neutral",
        "lead_status": "Needs Follow-up",
        "next_action": None,
    }
    allowed_sentiment = {"Positive", "Neutral", "Negative"}
    allowed_lead = {"Willing", "Not Willing", "Needs Follow-up"}
    merged = {**defaults, **(data or {})}
    if merged["sentiment"] not in allowed_sentiment:
        merged["sentiment"] = "Neutral"
    if merged["lead_status"] not in allowed_lead:
        merged["lead_status"] = "Needs Follow-up"
    return {
        "summary": merged["summary"],
        "sentiment": merged["sentiment"],
        "lead_status": merged["lead_status"],
        "next_action": merged["next_action"],
    }


def summarize_call(session_id: str) -> Dict[str, Any]:
    """Generate, validate, and persist a call summary for session_id."""
    existing = execute_read("SELECT * FROM call_summaries WHERE session_id = %s", (session_id,))
    if existing:
        row = existing[0]
        return {
            "session_id": row.get("session_id"),
            "summary": row.get("summary"),
            "sentiment": row.get("sentiment"),
            "lead_status": row.get("lead_status"),
            "next_action": row.get("next_action"),
        }

    msgs = session_store.get_messages(session_id)
    if not msgs:
        return {
            "session_id": session_id,
            "summary": "No conversation recorded.",
            "sentiment": "Neutral",
            "lead_status": "Needs Follow-up",
            "next_action": None,
        }

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    raw = ""
    try:
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
        raw = response.choices[0].message.content or ""
    except Exception as e:
        logging.exception("Failed to call LLM for summary: %s", e)

    try:
        parsed = json.loads(_strip_fences(raw)) if raw else {}
    except Exception as e:
        logging.warning("Summary JSON parse failed: %s", e)
        parsed = {}

    summary_data = _validate(parsed)

    insert_q = """
        INSERT INTO call_summaries (
            session_id, summary, sentiment, lead_status, next_action
        ) VALUES (%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            summary     = VALUES(summary),
            sentiment   = VALUES(sentiment),
            lead_status = VALUES(lead_status),
            next_action = VALUES(next_action)
    """
    execute_write(
        insert_q,
        (
            session_id,
            summary_data.get("summary"),
            summary_data.get("sentiment"),
            summary_data.get("lead_status"),
            summary_data.get("next_action"),
        ),
    )
    execute_write(
        "UPDATE leads SET lead_status = %s WHERE session_id = %s",
        (summary_data.get("lead_status"), session_id),
    )

    return {"session_id": session_id, **summary_data}
