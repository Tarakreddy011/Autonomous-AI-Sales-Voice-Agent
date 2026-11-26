import db, os, json
print('DB config:', db.get_db_config())
sid = 'test123'
# Insert lead
lead = db.save_or_update_lead(session_id=sid, name='Alice', phone='9876543210')
print('Lead saved:', lead)
# Ensure a free slot for today
from datetime import date
today = date.today().isoformat()
free = db.get_free_slots_for_date(today)
if not free:
    # create a dummy slot
    db.execute_write('INSERT INTO availability_slots (slot_date, slot_time) VALUES (%s,%s)', (today, '10:00:00'))
    free = db.get_free_slots_for_date(today)
slot = free[0]
appt = db.book_appointment_atomic(session_id=sid, slot_date_str=slot['slot_date'], slot_time_str=slot['slot_time'])
print('Booking result:', appt)
# Insert call summary
summary_q = '''
INSERT INTO call_summaries (session_id, summary, sentiment, lead_status, next_action)
VALUES (%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE summary=VALUES(summary), sentiment=VALUES(sentiment), lead_status=VALUES(lead_status), next_action=VALUES(next_action)
'''
db.execute_write(summary_q, (sid, 'Test summary', 'Positive', 'Willing', 'Follow up tomorrow'))
# Show recent rows
print('Leads table:', db.get_recent_table_rows('leads'))
print('Appointments table:', db.get_recent_table_rows('appointments'))
print('Call summaries table:', db.get_recent_table_rows('call_summaries'))
