"""timeutil.py — เวลา UTC แบบ "ไม่มี timezone" (naive) เหมือน datetime.utcnow() ทุกประการ

Python 3.12 ประกาศเลิกใช้ datetime.utcnow() แต่คอลัมน์ DateTime ในฐานข้อมูลของเราเก็บเวลา UTC แบบ naive
อยู่แล้ว จึงใช้ฟังก์ชันนี้แทนเพื่อให้ผลลัพธ์/ข้อมูลเดิมเข้ากันได้ทุกอย่าง (เปรียบเทียบกับค่าเก่าได้ตรงๆ)
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
