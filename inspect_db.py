"""inspect_db.py — Inspect MySQL tables for Comfort Chairs."""
from db import execute_read


def pretty_print(title: str, rows):
    print(f"\n=== {title} ===")
    if not rows:
        print("(no rows)")
        return
    keys = list(rows[0].keys())
    col_widths = {k: max(len(str(k)), max(len(str(r[k])) for r in rows)) for k in keys}
    header = " | ".join(f"{k:{col_widths[k]}}" for k in keys)
    print(header)
    print("-" * len(header))
    for r in rows:
        print(" | ".join(f"{str(r[k]):{col_widths[k]}}" for k in keys))


def main():
    pretty_print("Current DB date/time", execute_read("SELECT CURDATE() AS today, NOW() AS now"))
    pretty_print(
        "Free slots per date (future)",
        execute_read(
            """
            SELECT slot_date, COUNT(*) AS free_slots
            FROM availability_slots
            WHERE is_booked = 0 AND slot_date >= CURDATE()
            GROUP BY slot_date
            ORDER BY slot_date
            """
        ),
    )
    pretty_print("Leads table", execute_read("SELECT * FROM leads ORDER BY id DESC LIMIT 10"))
    pretty_print("Appointments table", execute_read("SELECT * FROM appointments ORDER BY id DESC LIMIT 10"))
    pretty_print("Call summaries table", execute_read("SELECT * FROM call_summaries ORDER BY id DESC LIMIT 10"))


if __name__ == "__main__":
    main()
