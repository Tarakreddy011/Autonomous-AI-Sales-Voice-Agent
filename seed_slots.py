"""
Seed Slots Script: Populates availability_slots for the next 7 days based on FAQ store hours.
Re-running does not create duplicates.
Pre-marks 2 to 3 slots as booked to test appointment conflict handling.
"""

import os
from datetime import datetime, date, timedelta
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("MYSQL_HOST", "localhost")
PORT = int(os.getenv("MYSQL_PORT", 3306))
USER = os.getenv("MYSQL_USER", "root")
PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DATABASE = os.getenv("MYSQL_DATABASE", "comfort_chairs")

def seed_slots():
    try:
        conn = mysql.connector.connect(
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD,
            database=DATABASE
        )
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

    cursor = conn.cursor()
    today = date.today()
    
    print(f"Seeding showroom hourly slots for next 7 days starting from {today}...")

    # Weekday hours (Mon-Sat): 10:00 AM to 8:00 PM (10, 11, 12, 13, 14, 15, 16, 17, 18, 19)
    weekday_hours = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    # Sunday hours: 11:00 AM to 6:00 PM (11, 12, 13, 14, 15, 16, 17)
    sunday_hours = [11, 12, 13, 14, 15, 16, 17]

    inserted_count = 0
    
    for day_offset in range(7):
        current_date = today + timedelta(days=day_offset)
        is_sunday = (current_date.weekday() == 6)
        hours = sunday_hours if is_sunday else weekday_hours

        for h in hours:
            slot_time_str = f"{h:02d}:00:00"
            
            # Pre-mark specific slots as booked for conflict demonstration:
            # Tomorrow at 11:00 AM and Tomorrow at 3:00 PM
            is_booked = 0
            if day_offset == 1 and h in [11, 15]:
                is_booked = 1
            elif day_offset == 2 and h == 14:
                is_booked = 1

            query = """
            INSERT INTO availability_slots (slot_date, slot_time, is_booked)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE id=id
            """
            cursor.execute(query, (current_date, slot_time_str, is_booked))
            if cursor.rowcount == 1:
                inserted_count += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"SUCCESS: Seeded {inserted_count} new slots. (Pre-booked slots marked for conflict testing).")
    return True

if __name__ == "__main__":
    seed_slots()
