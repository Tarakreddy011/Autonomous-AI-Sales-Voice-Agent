# inspect_db.py
import sqlite3
import json
import db  # ensure SQLite schema is initialized

from pathlib import Path

DB_PATH = Path(__file__).parent / "local.db"

def query(sql, params=()):
    """Execute a SELECT and return a list of dict rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def pretty_print(title, rows):
    print(f"\n=== {title} ===")
    if not rows:
        print("(no rows)")
        return
    keys = rows[0].keys()
    # compute column widths
    col_widths = {k: max(len(str(k)), max(len(str(r[k])) for r in rows)) for k in keys}
    header = " | ".join(f"{k:{col_widths[k]}}" for k in keys)
    print(header)
    print("-" * len(header))
    for r in rows:
        print(" | ".join(f"{str(r[k]):{col_widths[k]}}" for k in keys))

def main():
    if not DB_PATH.is_file():
        sys.exit(f"✖️  SQLite database not found at {DB_PATH}")
    # 1. Current DB date & time
    pretty_print("Current DB date/time", query("SELECT date('now') AS today, datetime('now') AS now;"))
    # 2. Free slots per date from today onward
    pretty_print(
        "Free slots per date (future)",
        query(
            """
            SELECT slot_date, COUNT(*) AS free_slots
            FROM availability_slots
            WHERE is_booked = 0 AND slot_date >= date('now')
            GROUP BY slot_date
            ORDER BY slot_date;
            """
        ),
    )
    # 3. Leads
    pretty_print("Leads table", query("SELECT * FROM leads;"))
    # 4. Appointments
    pretty_print("Appointments table", query("SELECT * FROM appointments;"))
    # 5. Specific slot check (tomorrow 10:00)
    pretty_print(
        "Slot 2026-11-27 10:00:00",
        query(
            "SELECT * FROM availability_slots WHERE slot_date = ? AND slot_time = ?;",
            ("2026-11-27", "10:00:00"),
        ),
    )

if __name__ == "__main__":
    main()
