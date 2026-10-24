-- รายละเอียดสถานที่แยกหมวด (วิธีเดินทาง / ลำดับการไหว้ / ของไหว้ / ข้อควรปฏิบัติ / เวลา)
-- backend เติมให้อัตโนมัติตอนสตาร์ท (app/main.py) ไฟล์นี้ไว้รันมือใน Supabase SQL Editor ถ้าต้องการ (รันซ้ำได้)
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS travel_info TEXT;
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS worship_steps TEXT;
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS offerings TEXT;
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS etiquette TEXT;
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS opening_hours VARCHAR(255);
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS best_time VARCHAR(255);
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS wish_tags VARCHAR(255);
ALTER TABLE sacred_places ADD COLUMN IF NOT EXISTS chants TEXT;  -- บทสวด/คาถา (JSON list)
