"""
Tools Module: Definitions, argument validation, and execution dispatcher for LLM tool calling.
Supports:
1. search_knowledge: ChromaDB RAG
2. save_lead: MySQL lead capture (session_id injected securely)
3. check_availability: Showroom slots query
4. book_appointment: Atomic race-condition-free booking
"""

import re
import json
from datetime import datetime, date, timedelta
from typing import Tuple, List, Dict, Any, Optional
import knowledge_base
import db

# Tools specification passed to the Groq LLM
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Searches the Comfort Chairs knowledge base for chair models, categories, prices, materials, dimensions, warranty, delivery speed, showroom timings, or store policies. Call this whenever the user asks any question about chairs or store information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query keywords, e.g. 'gaming chair price', 'ergonomic mesh chair for back pain', 'showroom opening hours'."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_lead",
            "description": "Saves or updates customer details in the store database. Call this as soon as you learn the customer's name, phone number, chair requirement, or budget. All fields are optional so you can save partial information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Customer's full name, e.g. 'Parag Sharma'."
                    },
                    "phone": {
                        "type": "string",
                        "description": "10-digit Indian mobile number, e.g. '9876543210'."
                    },
                    "requirement": {
                        "type": "string",
                        "description": "What kind of chair they need, who it is for, hours of sitting, or features requested."
                    },
                    "budget": {
                        "type": "string",
                        "description": "Approximate budget, e.g. 'under 5000' or '10000 to 15000 rupees'."
                    },
                    "lead_status": {
                        "type": "string",
                        "enum": ["Willing", "Not Willing", "Needs Follow-up"],
                        "description": "'Willing' if they want a showroom demo/purchase; 'Needs Follow-up' if undecided; 'Not Willing' if they decline."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Checks available showroom appointment slots for a specific date. Always call this before suggesting visit times to the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "The date in ISO format YYYY-MM-DD, e.g. '2026-11-26'."
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Confirms and books a showroom appointment for the customer. Only call this AFTER the customer has explicitly agreed to a specific date and time slot, and after their name and phone number have been collected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "The appointment date in ISO format YYYY-MM-DD, e.g. '2026-11-26'."
                    },
                    "time": {
                        "type": "string",
                        "description": "The appointment time in HH:MM:SS format, e.g. '11:00:00' or '15:00:00'."
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Purpose of visit, e.g. 'showroom visit and chair demo'."
                    }
                },
                "required": ["date", "time"]
            }
        }
    }
]

# Validation Helpers
def normalize_indian_phone(phone_raw: Optional[str]) -> Tuple[bool, str]:
    """Validates and normalizes an Indian phone number to 10 digits."""
    if not phone_raw:
        return True, ""
    # Strip spaces, dashes, parentheses
    cleaned = re.sub(r"[\s\-\(\)]", "", str(phone_raw))
    # Remove leading +91 or 91 or 0
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
        
    if re.fullmatch(r"[6-9]\d{9}", cleaned):
        return True, cleaned
    return False, phone_raw

def validate_iso_date(date_str: str) -> Tuple[bool, str]:
    """Validates that a date is in YYYY-MM-DD format and within the allowed 7-day window."""
    try:
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return False, f"Invalid date format '{date_str}'. Please use ISO format YYYY-MM-DD."
        
    today = date.today()
    max_date = today + timedelta(days=7)
    
    if parsed_date < today:
        return False, f"Date '{date_str}' is in the past. Today is {today}. Please select a date from today onwards."
    if parsed_date > max_date:
        return False, f"Showroom appointments can only be booked up to 7 days in advance (until {max_date})."
        
    return True, parsed_date.strftime("%Y-%m-%d")

# Execution Dispatcher
def execute_tool_call(name: str, arguments_json: str, session_id: str) -> Tuple[str, List[Dict]]:
    """
    Executes a requested tool call.
    SECURITY NOTE:
    session_id is injected directly by our backend runtime and is never provided or manipulated by the LLM.
    """
    try:
        args = json.loads(arguments_json) if isinstance(arguments_json, str) else arguments_json
    except Exception:
        args = {}

    # Tool 1: search_knowledge
    if name == "search_knowledge":
        query = args.get("query", "")
        chunks = knowledge_base.search_knowledge(query=query, top_k=4)
        if not chunks:
            payload = {"status": "no_results_found", "message": "No matching chairs or store policies found."}
        else:
            payload = {
                "status": "success",
                "results_count": len(chunks),
                "knowledge_items": [
                    {
                        "name": c["metadata"].get("name", "Item"),
                        "category": c["metadata"].get("category", ""),
                        "price_inr": c["metadata"].get("price", 0),
                        "details": c["content"]
                    }
                    for c in chunks
                ]
            }
        return json.dumps(payload, ensure_ascii=False), chunks

    # Tool 2: save_lead
    elif name == "save_lead":
        name_val = args.get("name")
        phone_val = args.get("phone")
        req_val = args.get("requirement")
        budget_val = args.get("budget")
        status_val = args.get("lead_status")

        # Validate phone
        if phone_val:
            is_valid, norm_phone = normalize_indian_phone(phone_val)
            if not is_valid:
                return json.dumps({
                    "status": "error",
                    "error": "invalid_phone",
                    "message": f"'{phone_val}' is not a valid 10-digit Indian phone number. Please ask the customer to repeat their 10-digit mobile number."
                }), []
            phone_val = norm_phone

        # Validate lead_status
        allowed_statuses = ["Willing", "Not Willing", "Needs Follow-up"]
        if status_val and status_val not in allowed_statuses:
            status_val = "Needs Follow-up"

        try:
            lead = db.save_or_update_lead(
                session_id=session_id,
                name=name_val,
                phone=phone_val,
                requirement=req_val,
                budget=budget_val,
                lead_status=status_val
            )
            return json.dumps({
                "status": "success",
                "message": "Lead details recorded in database.",
                "current_lead": {
                    "name": lead.get("name"),
                    "phone": lead.get("phone"),
                    "lead_status": lead.get("lead_status")
                }
            }), []
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}), []

    # Tool 3: check_availability
    elif name == "check_availability":
        date_raw = args.get("date", "")
        valid, result = validate_iso_date(date_raw)
        if not valid:
            return json.dumps({"status": "error", "message": result}), []

        target_date = result
        try:
            free_slots = db.get_free_slots_for_date(target_date)
            if not free_slots:
                return json.dumps({
                    "status": "no_slots",
                    "date": target_date,
                    "message": f"All slots on {target_date} are fully booked. Please ask if another day suits them."
                }), []
            
            # Format times as human-readable (e.g. 10:00 AM, 02:00 PM)
            formatted_times = []
            for s in free_slots:
                # slot_time can be a timedelta or time object from MySQL
                s_time = str(s["slot_time"])
                formatted_times.append(s_time)

            return json.dumps({
                "status": "available_slots",
                "date": target_date,
                "available_times": formatted_times[:5],  # Offer up to 5 slots
                "instruction": "Offer at most 2 or 3 of these times naturally to the caller."
            }), []
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}), []

    # Tool 4: book_appointment
    elif name == "book_appointment":
        date_raw = args.get("date", "")
        time_raw = args.get("time", "")
        purpose_val = args.get("purpose", "showroom visit or demo")

        valid, target_date = validate_iso_date(date_raw)
        if not valid:
            return json.dumps({"status": "error", "message": target_date}), []

        # Normalize time format to HH:MM:00
        time_clean = time_raw.strip()
        if len(time_clean) == 5:
            time_clean += ":00"

        try:
            booking_res = db.book_appointment_atomic(
                session_id=session_id,
                slot_date_str=target_date,
                slot_time_str=time_clean,
                purpose=purpose_val
            )
            return json.dumps(booking_res), []
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}), []

    return json.dumps({"error": f"Unknown tool: {name}"}), []
