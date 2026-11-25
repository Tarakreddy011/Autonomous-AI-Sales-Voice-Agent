-- Schema for Comfort Chairs Voice Caller System

CREATE DATABASE IF NOT EXISTS comfort_chairs;
USE comfort_chairs;

-- 1. Leads Table: Captures customer identity, budget, and qualification status per session
CREATE TABLE IF NOT EXISTS leads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    requirement TEXT DEFAULT NULL,
    budget VARCHAR(64) DEFAULT NULL,
    lead_status ENUM('Willing', 'Not Willing', 'Needs Follow-up') DEFAULT 'Needs Follow-up',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_phone (phone)
) ENGINE=InnoDB;

-- 2. Availability Slots Table: Pre-seeded showroom appointment slots
CREATE TABLE IF NOT EXISTS availability_slots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slot_date DATE NOT NULL,
    slot_time TIME NOT NULL,
    is_booked TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_slot (slot_date, slot_time),
    INDEX idx_date_booked (slot_date, is_booked)
) ENGINE=InnoDB;

-- 3. Appointments Table: Maps a confirmed slot to a qualified lead
CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lead_id INT NOT NULL,
    slot_id INT NOT NULL UNIQUE,
    purpose VARCHAR(64) DEFAULT 'showroom visit or demo',
    status VARCHAR(32) DEFAULT 'confirmed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES availability_slots(id) ON DELETE CASCADE,
    INDEX idx_lead (lead_id)
) ENGINE=InnoDB;

-- 4. Call Summaries Table: Generated post-call analysis (populated in Step 5)
CREATE TABLE IF NOT EXISTS call_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    summary TEXT,
    sentiment VARCHAR(32),
    lead_status VARCHAR(32),
    next_action TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_summary_session (session_id)
) ENGINE=InnoDB;
