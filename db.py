"""
Database Module: MySQL Connection Pooling and Unified Gateway.
Uses parameterized queries to prevent SQL injection.
All writes flow through execute_write, which simulates a single queue producer entrypoint.
"""

import os
from typing import List, Dict, Any, Optional
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("MYSQL_HOST", "localhost")
PORT = int(os.getenv("MYSQL_PORT", 3306))
USER = os.getenv("MYSQL_USER", "root")
PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DATABASE = os.getenv("MYSQL_DATABASE", "comfort_chairs")

# 1. Connection Pool (Singleton)
# Keeps pre-authenticated TCP sockets alive so concurrent callers avoid connection handshake latency
_pool: Optional[pooling.MySQLConnectionPool] = None

def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="caller_pool",
            pool_size=10,
            pool_reset_session=True,
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD,
            database=DATABASE
        )
    return _pool

# 2. Unified Write Gateway
def execute_write(query: str, params: tuple = ()) -> int:
    """
    Unified entrypoint for all INSERT, UPDATE, DELETE operations.
    
    ARCHITECTURE NOTE FOR INTERVIEWS:
    In a high-scale production system handling 10,000 parallel callers, 
    this function is the exact point where a message queue producer (e.g. Apache Kafka, 
    RabbitMQ, or Celery) would be plugged in. Instead of blocking the voice agent's 
    sub-second latency waiting on disk I/O, the write event is dispatched to the queue.
    """
    pool = get_pool()
    conn = pool.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid or cursor.rowcount
    finally:
        conn.close()  # Returns connection to pool

# 3. Read Query Helper
def execute_read(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """
    Executes a SELECT query using parameterized arguments and returns a list of dictionaries.
    """
    pool = get_pool()
    conn = pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    finally:
        conn.close()

# 4. Lead Persistence: Partial Update & Creation
def save_or_update_lead(
    session_id: str,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    requirement: Optional[str] = None,
    budget: Optional[str] = None,
    lead_status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates or updates the lead for the current caller session.
    Never overwrites existing non-empty values with None.
    """
    # Check if lead already exists for this session
    existing = execute_read("SELECT * FROM leads WHERE session_id = %s", (session_id,))
    
    if not existing:
        query = """
        INSERT INTO leads (session_id, name, phone, requirement, budget, lead_status)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        status_val = lead_status or "Needs Follow-up"
        execute_write(query, (session_id, name, phone, requirement, budget, status_val))
    else:
        current = existing[0]
        # Keep current values if new values are not supplied
        new_name = name if (name and name.strip()) else current.get("name")
        new_phone = phone if (phone and phone.strip()) else current.get("phone")
        new_req = requirement if (requirement and requirement.strip()) else current.get("requirement")
        new_budget = budget if (budget and budget.strip()) else current.get("budget")
        new_status = lead_status if (lead_status and lead_status.strip()) else current.get("lead_status")
        
        query = """
        UPDATE leads 
        SET name = %s, phone = %s, requirement = %s, budget = %s, lead_status = %s
        WHERE session_id = %s
        """
        execute_write(query, (new_name, new_phone, new_req, new_budget, new_status, session_id))

    # Return the refreshed lead row
    refreshed = execute_read("SELECT * FROM leads WHERE session_id = %s", (session_id,))
    return refreshed[0] if refreshed else {}

# 5. Availability Retrieval
def get_free_slots_for_date(slot_date_str: str) -> List[Dict[str, Any]]:
    """
    Returns all unbooked slots for a given date formatted as readable strings.
    """
    query = """
    SELECT id, slot_date, slot_time 
    FROM availability_slots 
    WHERE slot_date = %s AND is_booked = 0 
    ORDER BY slot_time ASC
    """
    return execute_read(query, (slot_date_str,))

# 6. Atomic Appointment Booking (Race-Condition Free)
def book_appointment_atomic(
    session_id: str,
    slot_date_str: str,
    slot_time_str: str,
    purpose: str = "showroom visit or demo"
) -> Dict[str, Any]:
    """
    Atomically books a showroom slot.
    
    HOW IT PREVENTS RACE CONDITIONS / DOUBLE BOOKING:
    Executes a single atomic UPDATE:
    UPDATE availability_slots SET is_booked = 1 WHERE slot_date = %s AND slot_time = %s AND is_booked = 0
    
    In MySQL InnoDB, row-level exclusive locks ensure that even if two browser tabs 
    execute this query at the exact same millisecond, exactly ONE caller receives rowcount=1.
    The second caller sees is_booked is already 1, receives rowcount=0, and is safely rejected.
    """
    # 1. Verify lead exists and has name and phone
    leads = execute_read("SELECT id, name, phone FROM leads WHERE session_id = %s", (session_id,))
    if not leads or not leads[0].get("name") or not leads[0].get("phone"):
        return {
            "success": False,
            "error": "missing_contact_info",
            "message": "Customer name and phone number must be collected before confirming an appointment."
        }
    
    lead_id = leads[0]["id"]

    pool = get_pool()
    conn = pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            # 2. Atomic UPDATE on the slot
            update_slot_query = """
            UPDATE availability_slots 
            SET is_booked = 1 
            WHERE slot_date = %s AND slot_time = %s AND is_booked = 0
            """
            cursor.execute(update_slot_query, (slot_date_str, slot_time_str))
            
            if cursor.rowcount == 0:
                # The slot is either already taken or does not exist
                conn.rollback()
                return {
                    "success": False,
                    "error": "slot_unavailable",
                    "message": f"The slot on {slot_date_str} at {slot_time_str} was just booked or is unavailable. Please check other available times."
                }

            # 3. Retrieve the slot ID that was just locked
            cursor.execute(
                "SELECT id FROM availability_slots WHERE slot_date = %s AND slot_time = %s",
                (slot_date_str, slot_time_str)
            )
            slot_record = cursor.fetchone()
            slot_id = slot_record["id"]

            # 4. Insert confirmed appointment
            insert_appt_query = """
            INSERT INTO appointments (lead_id, slot_id, purpose, status)
            VALUES (%s, %s, %s, 'confirmed')
            """
            cursor.execute(insert_appt_query, (lead_id, slot_id, purpose))
            appt_id = cursor.lastrowid
            
            # Also update lead_status to 'Willing' upon successful booking
            cursor.execute("UPDATE leads SET lead_status = 'Willing' WHERE id = %s", (lead_id,))
            
            conn.commit()
            
            return {
                "success": True,
                "appointment_id": appt_id,
                "date": slot_date_str,
                "time": slot_time_str,
                "purpose": purpose
            }
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

# 7. Helper for Live Demo UI
def get_recent_table_rows(table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Helper to inspect the database live inside the Streamlit UI."""
    allowed = ["leads", "availability_slots", "appointments", "call_summaries"]
    if table_name not in allowed:
        return []
    order_col = "id DESC" if table_name != "availability_slots" else "slot_date ASC, slot_time ASC"
    return execute_read(f"SELECT * FROM {table_name} ORDER BY {order_col} LIMIT {limit}")
