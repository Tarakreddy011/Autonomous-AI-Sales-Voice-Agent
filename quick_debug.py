"""Quick booking debug script
Runs a minimal end‑to‑end flow:
1. Creates a test session id.
2. Saves a lead (name & phone).
3. Checks availability for tomorrow.
4. Books the first free slot.
5. Prints the tool‑call debug log and final DB rows.
"""
import os, json, datetime

from tools import execute_tool_call, DEBUG_LOG
from db import get_free_slots_for_date, get_recent_table_rows

session_id = "quick_debug_001"

# 1. Save lead
args_save = json.dumps({"name": "Test User", "phone": "9876543210"})
result_save, _ = execute_tool_call("save_lead", args_save, session_id)
print("save_lead result:", result_save)

# 2. Check availability for tomorrow
 tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
args_check = json.dumps({"date": tomorrow})
result_check, _ = execute_tool_call("check_availability", args_check, session_id)
print("check_availability result:", result_check)

# Parse free slots from result (assuming success payload)
payload = json.loads(result_check)
if payload.get("status") != "success":
    print("No free slots, abort")
    exit()
first = payload["availability"] if "availability" in payload else payload.get("slots")
# The actual implementation returns a list under "availability"? Let's fetch directly from DB for safety
free = get_free_slots_for_date(tomorrow)
if not free:
    print("No free slots in DB")
    exit()
slot = free[0]
date_str = slot["slot_date"]
time_str = slot["slot_time"]

# 3. Book appointment
args_book = json.dumps({"date": date_str, "time": time_str, "purpose": "showroom visit"})
result_book, _ = execute_tool_call("book_appointment", args_book, session_id)
print("book_appointment result:", result_book)

# Print debug log
print("\n--- TOOL CALL LOG ---")
for entry in DEBUG_LOG:
    print(json.dumps(entry, ensure_ascii=False, indent=2))

# Show recent DB rows
print("\n--- Recent DB rows ---")
for tbl in ["leads", "availability_slots", "appointments"]:
    rows = get_recent_table_rows(tbl, limit=10)
    print(f"{tbl}:", rows)
