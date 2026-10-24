-- init.sql (PostgreSQL)
-- อ้างอิง schema เดียวกับที่ SQLAlchemy สร้างให้อัตโนมัติตอน dev (ดู app/models.py)
-- ใช้ไฟล์นี้เวลาต้องการสร้างตารางบน Postgres โดยตรง เช่นตอน deploy จริง
-- (แนะนำให้ทีมย้ายไปใช้ alembic migration ในระยะยาวแทนการรัน SQL มือ)

-- สร้าง database ก่อน (รันแยกนอกไฟล์นี้ เพราะ Postgres ไม่อนุญาตให้
-- CREATE DATABASE อยู่ในสคริปต์เดียวกับคำสั่งอื่นถ้าเชื่อมต่อไปที่ database
-- นั้นอยู่แล้ว):
--   CREATE DATABASE sai_mu_db;
-- แล้วค่อย \c sai_mu_db ก่อนรันส่วนที่เหลือของไฟล์นี้

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255),       -- NULL = สมัครด้วย Google/Facebook และยังไม่ตั้งรหัสผ่าน
  google_id VARCHAR(64) UNIQUE,
  facebook_id VARCHAR(64) UNIQUE,
  avatar_path VARCHAR(255),
  birth_date DATE NOT NULL,
  birth_time TIME,                  -- NULL = ไม่ทราบเวลาเกิด (fallback เที่ยงวันตอนคำนวณราศี)
  hide_birth_year BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_astro_profiles (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  zodiac_sign VARCHAR(20) NOT NULL,
  zodiac_animal VARCHAR(20) NOT NULL,
  calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS otp_codes (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  purpose VARCHAR(20) NOT NULL,     -- 'signup' หรือ 'reset'
  code_hash VARCHAR(64) NOT NULL,   -- HMAC-SHA256 ของรหัส (ไม่เก็บรหัสจริง)
  expires_at TIMESTAMP NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  used BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_otp_codes_email ON otp_codes(email);

CREATE TABLE IF NOT EXISTS chat_messages (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL,       -- 'user' หรือ 'assistant'
  content TEXT NOT NULL,
  sources TEXT,                     -- JSON string ของ [{id, title, score}, ...] (NULL ฝั่ง user)
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created ON chat_messages(user_id, created_at);

-- Postgres ไม่มี "ON UPDATE CURRENT_TIMESTAMP" แบบ MySQL ในตัว ต้องใช้ trigger
-- ถ้าจะให้ updated_at อัปเดตอัตโนมัติเวลามีการ UPDATE แถวด้วย SQL ดิบ
-- (ฝั่ง SQLAlchemy ORM มี onupdate= ในตัวอยู่แล้ว จึงจำเป็นเฉพาะกรณีมีคน
-- แก้ข้อมูลด้วย SQL ตรงๆ นอกแอปด้วย)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

-- ประวัติคำทำนาย (หน้า "ประวัติ") ดู docs/migrations/2026-10-09_history_entries.sql
CREATE TABLE IF NOT EXISTS history_entries (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind VARCHAR(20) NOT NULL,
  category VARCHAR(20) NOT NULL,
  title VARCHAR(200) NOT NULL,
  summary VARCHAR(300) NOT NULL,
  content TEXT NOT NULL,
  is_saved BOOLEAN NOT NULL DEFAULT FALSE,
  ref_key VARCHAR(100),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_history_user_ref UNIQUE (user_id, ref_key)
);
CREATE INDEX IF NOT EXISTS ix_history_entries_user_id ON history_entries(user_id);
CREATE INDEX IF NOT EXISTS ix_history_entries_category ON history_entries(category);
CREATE INDEX IF NOT EXISTS ix_history_entries_created_at ON history_entries(created_at);
