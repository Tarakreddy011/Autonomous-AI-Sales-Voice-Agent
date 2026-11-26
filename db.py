# MySQL‑only database module with a connection pool
"""Database helper that connects exclusively to MySQL using a connection pool.
All previous SQLite fallback logic has been removed. The module loads the
environment variables from the project's .env file (using python‑dotenv) and
creates a single pool on import. If any required variable is missing or the
initial connection cannot be established, a clear exception is raised and
logged – there is no silent fallback.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import logging
import mysql.connector
from mysql.connector import pooling
from typing import List, Dict, Any

# Load .env explicitly (project root)
env_path = Path('C:/Users/hp/Desktop/Automated_caller_System/.env')
load_dotenv(dotenv_path=env_path)

# Verify required MySQL settings (password may be empty)
required = ['MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_DATABASE']
missing = [k for k in required if not os.getenv(k)]
if missing:
    raise RuntimeError(f"Missing required MySQL env vars: {', '.join(missing)}")

# Configure logging (debug.log in project root)
logging.basicConfig(
    filename='debug.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s'
)

# Create a connection pool (max 5 connections; adjust as needed)
try:
    pool = pooling.MySQLConnectionPool(
        pool_name="mypool",
        pool_size=15,
        host=os.getenv('MYSQL_HOST'),
        port=int(os.getenv('MYSQL_PORT') or 3306),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD') or '',  # Empty password allowed
        database=os.getenv('MYSQL_DATABASE'),
        autocommit=False,
    )
    logging.info(
        "MySQL pool created: host=%s port=%s db=%s user=%s",
        os.getenv('MYSQL_HOST'),
        os.getenv('MYSQL_PORT'),
        os.getenv('MYSQL_DATABASE'),
        os.getenv('MYSQL_USER')
    )
except Exception as e:
    logging.exception("Failed to create MySQL connection pool")
    raise

def _get_conn():
    """Fetch a connection from the pool, retrying briefly if all connections are busy."""
    import time
    for attempt in range(20):
        try:
            return pool.get_connection()
        except pooling.PoolError:
            if attempt == 19:
                logging.exception("Unable to get MySQL connection from pool after retries")
                raise
            time.sleep(0.05)
        except Exception as e:
            logging.exception("Unable to get MySQL connection from pool")
            raise

def get_db_config():
    """Return a dict with the DB connection parameters (password omitted)."""
    return {
        "backend": "MySQL",
        "host": os.getenv('MYSQL_HOST'),
        "port": os.getenv('MYSQL_PORT'),
        "database": os.getenv('MYSQL_DATABASE'),
        "user": os.getenv('MYSQL_USER'),
        "sqlite_path": None,
    }

# ---------------------------------------------------------------------------
# Unified write/read helpers (MySQL %s placeholders)
# ---------------------------------------------------------------------------

def execute_write(query: str, params: tuple = ()) -> int:
    """Execute a write query, commit, and return rowcount or lastrowid.
    Exceptions are logged with full traceback and re‑raised.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.lastrowid or cur.rowcount
    except Exception as e:
        logging.exception("Database write error: %s", e)
        conn.rollback()
        raise
    finally:
        conn.close()

def execute_read(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a read query and return a list of dict rows.
    The transaction is closed immediately to avoid stale snapshots.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    except Exception as e:
        logging.exception("Database read error: %s", e)
        raise
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Schema initialisation – create tables if they do not exist
# ---------------------------------------------------------------------------
def _init_schema():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        # MySQL does not support executescript; run each statement individually
        statements = [
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255) UNIQUE,
                name VARCHAR(255),
                phone VARCHAR(20),
                requirement TEXT,
                budget VARCHAR(255),
                lead_status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS availability_slots (
                id INT AUTO_INCREMENT PRIMARY KEY,
                slot_date DATE,
                slot_time TIME,
                is_booked TINYINT DEFAULT 0,
                UNIQUE(slot_date, slot_time)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                lead_id INT,
                slot_id INT UNIQUE,
                purpose VARCHAR(255),
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lead_id) REFERENCES leads(id),
                FOREIGN KEY (slot_id) REFERENCES availability_slots(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS call_summaries (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255) UNIQUE,
                summary TEXT,
                sentiment VARCHAR(20),
                lead_status VARCHAR(50),
                next_action TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]
        for stmt in statements:
            cur.execute(stmt)
        conn.commit()
    except Exception as e:
        logging.exception("Schema creation failed")
        conn.rollback()
        raise
    finally:
        conn.close()

# Initialise schema on import
_init_schema()

# ---------------------------------------------------------------------------
# Lead persistence (MySQL placeholders %s)
# ---------------------------------------------------------------------------

def save_or_update_lead(
    session_id: str,
    name: str = None,
    phone: str = None,
    requirement: str = None,
    budget: str = None,
    lead_status: str = None,
) -> Dict[str, Any]:
    existing = execute_read("SELECT * FROM leads WHERE session_id = %s", (session_id,))
    if not existing:
        status_val = lead_status or "Needs Follow-up"
        execute_write(
            "INSERT INTO leads (session_id, name, phone, requirement, budget, lead_status) VALUES (%s,%s,%s,%s,%s,%s)",
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
            "UPDATE leads SET name=%s, phone=%s, requirement=%s, budget=%s, lead_status=%s WHERE session_id=%s",
            (new_name, new_phone, new_req, new_budget, new_status, session_id),
        )
    refreshed = execute_read("SELECT * FROM leads WHERE session_id = %s", (session_id,))
    return refreshed[0] if refreshed else {}

# ---------------------------------------------------------------------------
# Availability retrieval
# ---------------------------------------------------------------------------

def get_free_slots_for_date(slot_date_str: str) -> List[Dict[str, Any]]:
    query = """
    SELECT id, slot_date, slot_time
    FROM availability_slots
    WHERE slot_date = %s AND is_booked = 0
    ORDER BY slot_time ASC
    """
    return execute_read(query, (slot_date_str,))

# ---------------------------------------------------------------------------
# Atomic appointment booking (MySQL version)
# ---------------------------------------------------------------------------

def book_appointment_atomic(
    session_id: str,
    slot_date_str: str,
    slot_time_str: str,
    purpose: str = "showroom visit or demo",
) -> Dict[str, Any]:
    leads = execute_read("SELECT id, name, phone FROM leads WHERE session_id = %s", (session_id,))
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
            "UPDATE availability_slots SET is_booked = 1 WHERE slot_date = %s AND slot_time = %s AND is_booked = 0",
            (slot_date_str, slot_time_str),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "error": "slot_unavailable", "message": f"The slot on {slot_date_str} at {slot_time_str} is no longer available."}
        cur.execute("SELECT id FROM availability_slots WHERE slot_date = %s AND slot_time = %s", (slot_date_str, slot_time_str))
        slot_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO appointments (lead_id, slot_id, purpose, status) VALUES (%s,%s,%s,%s)",
            (lead_id, slot_id, purpose, "confirmed"),
        )
        appt_id = cur.lastrowid
        cur.execute("UPDATE leads SET lead_status = 'Willing' WHERE id = %s", (lead_id,))
        conn.commit()
        return {"success": True, "appointment_id": appt_id, "date": slot_date_str, "time": slot_time_str, "purpose": purpose}
    except Exception as e:
        conn.rollback()
        logging.exception("Database error during book_appointment_atomic")
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
