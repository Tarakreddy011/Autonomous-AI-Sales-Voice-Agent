-- Insight Queries for Comfort Chairs AI Voice Sales Agent

-- 1. Total number of leads (calls)
SELECT COUNT(*) AS total_calls FROM leads;

-- 2. Leads by status (Willing / Not Willing / Needs Follow‑up)
SELECT lead_status, COUNT(*) AS count FROM leads GROUP BY lead_status;

-- 3. Sentiment distribution from call summaries
SELECT sentiment, COUNT(*) AS count FROM call_summaries GROUP BY sentiment;

-- 4. Number of bookings per day
SELECT slot_date, COUNT(*) AS bookings FROM appointments GROUP BY slot_date ORDER BY slot_date;
