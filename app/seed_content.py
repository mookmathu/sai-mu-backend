"""
seed_content.py
----------------
ตาราง daily_color_charts (สีมงคลประจำวันตามหลักจีน) ผูกกับปี/เดือน/วันที่จริง
และต้นทางข้อมูลอัปเดตใหม่ทุกเดือน (เช่นตารางที่มีเครดิตต่อท้ายว่า "cr. PasutAstro")
จึงไม่มีชุดข้อมูลกลางที่ถูกต้องให้ auto-seed ได้ — ต้องกรอกข้อมูลจริงของแต่ละเดือน
เองผ่านหน้าเว็บแอดมิน (/admin/)

ฟังก์ชัน seed_example() ด้านล่างนี้ใส่ไว้แค่ 1 แถวตัวอย่าง (ค่าสมมติ ไม่ใช่ข้อมูล
จริงจากแหล่งไหน) เผื่ออยากดูรูปแบบข้อมูลก่อนเริ่มกรอกเอง ไม่ auto-run ตอน backend
สตาร์ท ต้องรันเอง:

    python -m app.seed_content
"""

from dotenv import load_dotenv

load_dotenv()

from . import models
from .database import Base, SessionLocal, engine

EXAMPLE_ROW = {
    "year": 2026,
    "month": 1,
    "day_of_month": 1,
    "element_name": "ดิน หยาง",
    "help_colors": "ทอง, สีเงิน",
    "love_colors": "น้ำตาล, ครีม",
    "luck_colors": "ดำ, น้ำเงินเข้ม",
    "problem_colors": "เขียวเข้ม",
    "zodiac_note": None,
    "source_note": "ตัวอย่างข้อมูล (ค่าสมมติ) — แก้ไข/ลบได้เลย แล้วกรอกข้อมูลจริงของคุณผ่านหน้าเว็บแอดมิน (/admin/)",
}


def seed_example() -> None:
    Base.metadata.create_all(bind=engine)  # เผื่อรันสคริปต์นี้ก่อน backend เคยสตาร์ทเลย
    db = SessionLocal()
    try:
        existing = db.query(models.DailyColorChart).count()
        if existing > 0:
            print(f"daily_color_charts มีข้อมูลอยู่แล้ว ({existing} แถว) — ข้ามการใส่ตัวอย่าง")
            return
        db.add(models.DailyColorChart(**EXAMPLE_ROW))
        db.commit()
        print("ใส่ข้อมูลตัวอย่าง 1 แถวแล้ว (1 ม.ค. 2026, ค่าสมมติ) — ไปกรอกข้อมูลจริงต่อที่ /admin/")
    finally:
        db.close()


if __name__ == "__main__":
    seed_example()
