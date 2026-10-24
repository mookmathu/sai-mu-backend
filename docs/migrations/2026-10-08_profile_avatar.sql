-- รูปโปรไฟล์ผู้ใช้ — รันครั้งเดียวบน Supabase (SQL Editor)
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_path VARCHAR(255);
