-- Read-only business insight queries for Comfort Chairs (MySQL)

-- 1. Total calls recorded (based on unique call summaries)
SELECT COUNT(*) AS total_calls
FROM call_summaries;

-- 2. Leads breakdown by lead_status
SELECT
    COALESCE(lead_status, 'Unknown') AS lead_status,
    COUNT(*) AS lead_count
FROM leads
GROUP BY lead_status
ORDER BY lead_count DESC;

-- 3. Customer sentiment counts across summarized calls
SELECT
    COALESCE(sentiment, 'Unknown') AS sentiment,
    COUNT(*) AS call_count
FROM call_summaries
GROUP BY sentiment
ORDER BY call_count DESC;

-- 4. Confirmed showroom bookings per slot date
SELECT
    s.slot_date,
    COUNT(a.id) AS bookings_count
FROM appointments a
JOIN availability_slots s ON a.slot_id = s.id
WHERE a.status = 'confirmed'
GROUP BY s.slot_date
ORDER BY s.slot_date ASC;
