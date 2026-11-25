"""
SQLite‑only database module (fallback when MySQL is unavailable).
All functions use a single SQLite file (local.db) in the project directory.
The schema matches the original MySQL tables.
"""
import os
import sqlite3
import logging
import traceback
from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# SQLite connection handling
# ---------------------------------------------------------------------------
DB_FILE = os.path.join(os.path.dirname(__file__), "local.db")

def _get_conn():
    """Return a fresh SQLite connection (check_same_thread=False for Streamlit).
    The caller must close it when done.
    """
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def _init_schema():
    """Create tables if they do not exist. Called once on import.
    The schema mirrors the MySQL version used elsewhere in the project.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE,
        name TEXT,
        phone TEXT,
        requirement TEXT,
        budget TEXT,
        lead_status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS availability_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slot_date TEXT,
        slot_time TEXT,
        is_booked INTEGER DEFAULT 0,
        UNIQUE(slot_date, slot_time)
    );

    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        slot_id INTEGER UNIQUE,
        purpose TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(lead_id) REFERENCES leads(id),
        FOREIGN KEY(slot_id) REFERENCES availability_slots(id)
    );
    CREATE TABLE IF NOT EXISTS call_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE,
        summary TEXT,
        sentiment TEXT,
        lead_status TEXT,
        customer_name TEXT,
        customer_phone TEXT,
        requirement TEXT,
        budget TEXT,
        appointment_booked INTEGER,
        next_action TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()
    logging.info("SQLite schema ensured")

# Initialise on import
_init_schema()

# ---------------------------------------------------------------------------
# Unified write/read helpers (using SQLite placeholders '?')
# ---------------------------------------------------------------------------
def execute_write(query: str, params: tuple = ()) -> int:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.lastrowid or cur.rowcount
    finally:
        conn.close()

def execute_read(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Lead persistence (adapted for SQLite placeholders)
# ---------------------------------------------------------------------------
def save_or_update_lead(
    session_id: str,
    name: str = None,
    phone: str = None,
    requirement: str = None,
    budget: str = None,
    lead_status: str = None,
) -> Dict[str, Any]:
    existing = execute_read("SELECT * FROM leads WHERE session_id = ?", (session_id,))
    if not existing:
        status_val = lead_status or "Needs Follow-up"
        execute_write(
            "INSERT INTO leads (session_id, name, phone, requirement, budget, lead_status) VALUES (?,?,?,?,?,?)",
            (session_id, name, phone, requirement, budget, status_val),
        )
    else:
        cur = existing[0]
        new_name = name if name else cur.get("name")
        new_phone = phone if phone else cur.get("phone")
        new_req = requirement if requirement else cur.get("requirement")
        new_budget = budget if budget else cur.get("budget")
        new_status = lead_status if lead_status else cur.get("lead_status")
        execute_write(
            "UPDATE leads SET name = ?, phone = ?, requirement = ?, budget = ?, lead_status = ? WHERE session_id = ?",
            (new_name, new_phone, new_req, new_budget, new_status, session_id),
        )
    refreshed = execute_read("SELECT * FROM leads WHERE session_id = ?", (session_id,))
    return refreshed[0] if refreshed else {}

# ---------------------------------------------------------------------------
# Availability retrieval (SQLite placeholders)
# ---------------------------------------------------------------------------
def get_free_slots_for_date(slot_date_str: str) -> List[Dict[str, Any]]:
    query = """
    SELECT id, slot_date, slot_time
    FROM availability_slots
    WHERE slot_date = ? AND is_booked = 0
    ORDER BY slot_time ASC
    """
    return execute_read(query, (slot_date_str,))

# ---------------------------------------------------------------------------
# Atomic appointment booking (SQLite version)
# ---------------------------------------------------------------------------
def book_appointment_atomic(
    session_id: str,
    slot_date_str: str,
    slot_time_str: str,
    purpose: str = "showroom visit or demo",
) -> Dict[str, Any]:
    # Verify lead exists with name & phone
    leads = execute_read("SELECT id, name, phone FROM leads WHERE session_id = ?", (session_id,))
    if not leads or not leads[0].get("name") or not leads[0].get("phone"):
        return {
            "success": False,
            "error": "missing_contact_info",
            "message": "Customer name and phone number must be collected before confirming an appointment.",
        }
    lead_id = leads[0]["id"]
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE availability_slots SET is_booked = 1 WHERE slot_date = ? AND slot_time = ? AND is_booked = 0",
            (slot_date_str, slot_time_str),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "error": "slot_unavailable",
                    "message": f"The slot on {slot_date_str} at {slot_time_str} is no longer available."}
        cur.execute("SELECT id FROM availability_slots WHERE slot_date = ? AND slot_time = ?", (slot_date_str, slot_time_str))
        slot_record = cur.fetchone()
        slot_id = slot_record[0]
        cur.execute(
            "INSERT INTO appointments (lead_id, slot_id, purpose, status) VALUES (?,?,?,?)",
            (lead_id, slot_id, purpose, "confirmed"),
        )
        appt_id = cur.lastrowid
        cur.execute("UPDATE leads SET lead_status = 'Willing' WHERE id = ?", (lead_id,))
        conn.commit()
        return {"success": True, "appointment_id": appt_id, "date": slot_date_str, "time": slot_time_str, "purpose": purpose}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Helper for UI – recent rows
# ---------------------------------------------------------------------------
def get_recent_table_rows(table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    allowed = ["leads", "availability_slots", "appointments", "call_summaries"]
    if table_name not in allowed:
        return []
    order_col = "id DESC" if table_name != "availability_slots" else "slot_date ASC, slot_time ASC"
    query = f"SELECT * FROM {table_name} ORDER BY {order_col} LIMIT {limit}"
    return execute_read(query)
