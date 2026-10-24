"""
avatars.py
----------
เก็บรูปโปรไฟล์ผู้ใช้เป็นไฟล์ในโฟลเดอร์ uploads/avatars/ แล้วเสิร์ฟผ่าน /uploads/avatars/<ชื่อไฟล์>
(mount ใน main.py) — ชื่อไฟล์มีเวลาต่อท้าย (เช่น 12-1728390000.jpg) เพื่อให้แอป/CDN
ไม่ใช้รูปเก่าจากแคชหลังเปลี่ยนรูป

หมายเหตุ: ไฟล์อยู่ในดิสก์ของเครื่องที่รัน backend — ถ้า deploy ไปที่ที่ดิสก์ไม่ถาวร
(เช่น container ที่รีสตาร์ทแล้วข้อมูลหาย) ต้องย้ายไปเก็บที่ object storage แทน
(เช่น Supabase Storage) โดยแก้เฉพาะไฟล์นี้
"""
import time
from pathlib import Path

from fastapi import HTTPException

# <root ของ backend>/uploads/avatars
AVATAR_DIR = Path(__file__).resolve().parents[1] / "uploads" / "avatars"
MAX_AVATAR_BYTES = 3 * 1024 * 1024  # 3 MB (แอปย่อรูปก่อนส่งอยู่แล้ว)


def _detect_extension(data: bytes) -> str | None:
    """ดูจาก magic bytes ไม่เชื่อนามสกุล/Content-Type ที่ client ส่งมา"""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_avatar(user_id: int, data: bytes) -> str:
    """ตรวจรูปแล้วบันทึก คืนชื่อไฟล์ (เก็บลงคอลัมน์ users.avatar_path)"""
    if not data:
        raise HTTPException(status_code=400, detail="ไม่พบไฟล์รูป")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="รูปใหญ่เกินไป (สูงสุด 3 MB)")
    ext = _detect_extension(data)
    if ext is None:
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์รูป JPG, PNG หรือ WEBP")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{user_id}-{int(time.time())}.{ext}"
    (AVATAR_DIR / filename).write_bytes(data)
    return filename


def delete_avatar_file(filename: str | None) -> None:
    if not filename:
        return
    # ชื่อไฟล์มาจากฐานข้อมูลเอง แต่กัน path แปลกๆ ไว้ก่อน
    path = AVATAR_DIR / Path(filename).name
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
