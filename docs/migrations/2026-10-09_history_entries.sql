-- ตารางประวัติคำทำนาย (หน้า "ประวัติ") — ถ้าเปิดแอปด้วย create_all ตารางนี้ถูกสร้างให้เองอยู่แล้ว
-- ไฟล์นี้ไว้รันมือใน Supabase SQL Editor กรณีต้องการสร้างล่วงหน้า (รันซ้ำได้)
CREATE TABLE IF NOT EXISTS history_entries (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind VARCHAR(20) NOT NULL,          -- chat | daily | name | number
  category VARCHAR(20) NOT NULL,      -- daily | zodiac | numerology | color | general
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
