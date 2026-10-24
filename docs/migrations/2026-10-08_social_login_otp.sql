-- Migration: เพิ่ม Google/Facebook login + OTP (รันบนฐานข้อมูล Postgres/Supabase ที่มีตาราง users อยู่แล้ว)
-- ตาราง otp_codes ไม่ต้องรันเอง — backend สร้างให้อัตโนมัติตอนสตาร์ท (Base.metadata.create_all)
-- แต่ create_all "ไม่แก้ตารางเดิม" จึงต้องรันส่วนล่างนี้เองหนึ่งครั้ง:

ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS facebook_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_id ON users(google_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_facebook_id ON users(facebook_id);
