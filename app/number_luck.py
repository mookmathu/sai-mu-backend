# -*- coding: utf-8 -*-
"""
number_luck.py
--------------
เลขมงคลของ เบอร์โทร / ทะเบียนรถ: รวมค่าตัวเลขทุกหลัก (และอักษรไทยนำหน้าทะเบียน
แปลงเป็นเลขด้วยตารางเดียวกับชื่อ ดู name_numerology.TABLE) แล้วเทียบกลุ่มผลรวม

แหล่งอ้างอิง: GODTOWA https://www.godtowathailand.com/content/25171 (สูตรบวกเลขและกลุ่มผลรวม
ดีมาก/ปานกลาง/ไม่ดี — บทความระบุว่าขึ้นกับความเชื่อ) ส่วนค่าของอักษรใช้ตารางมหามงคล
ผลรวม 1, 2 และตั้งแต่ 55 ขึ้นไปบทความไม่ได้ระบุ จะตอบ "unknown" ไม่เดาความหมาย
"""
from __future__ import annotations

import re

from . import name_numerology as nn
from .number_meanings import get_meaning

GREAT = {4, 5, 6, 9, 14, 15, 19, 23, 24, 32, 36, 40, 41, 42, 44, 45, 46, 50, 51, 54}
FAIR = {8, 10, 13, 16, 18, 22, 25, 26, 28, 31, 35, 38, 39, 47, 49, 52, 53}
POOR = {3, 7, 11, 12, 17, 20, 21, 27, 29, 30, 33, 34, 37, 43, 48}

LEVEL_TEXT = {
    "great": "กลุ่มที่เชื่อว่าส่งเสริมโอกาสสำเร็จ อุปสรรคน้อย การเงินและความสุขดี",
    "fair": "กลุ่มกลาง อาจเหนื่อยหรือมีอุปสรรคบ้าง แต่ถ้าพยายามก็ไปถึงเป้าหมายได้",
    "poor": "กลุ่มที่ควรระวัง งาน เงิน ความรัก และความปลอดภัย ถ้าไม่สบายใจลองเลือกเลขอื่น",
    "unknown": "ผลรวมนี้ไม่อยู่ในกลุ่มที่แหล่งอ้างอิงระบุไว้ จึงไม่ตีความ",
}

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
SOURCE = "GODTOWA https://www.godtowathailand.com/content/25171 (อักษรใช้ตารางมหามงคล)"


def level_of(n: int) -> str:
    if n in GREAT:
        return "great"
    if n in FAIR:
        return "fair"
    if n in POOR:
        return "poor"
    return "unknown"


def analyze_number(text: str) -> dict:
    text = (text or "").strip().translate(_THAI_DIGITS)
    digits = [int(c) for c in text if c.isdigit()]
    letters = [(c, nn.CHAR_VALUE[c]) for c in text if c in nn.CHAR_VALUE]
    if not digits:
        raise ValueError("ต้องมีตัวเลขอย่างน้อย 1 หลัก")
    total = sum(digits) + sum(v for _, v in letters)
    level = level_of(total)
    return {
        "input": text,
        "digit_sum": sum(digits),
        "letters": [{"char": c, "value": v} for c, v in letters],
        "letter_sum": sum(v for _, v in letters),
        "total": total,
        "level": level,
        "note": LEVEL_TEXT[level],
        "meaning": get_meaning(total),
        "source": SOURCE,
    }


# ---------------------------------------------------------------------
# ดึงทะเบียนรถ / สีรถ จากข้อความแชท
# ---------------------------------------------------------------------

# ทะเบียนไทย: เลขนำ (ไม่บังคับ) + อักษร 1-3 ตัว + เลข 1-4 หลัก เช่น 5กก-1555, กข 123, 1ฎก 9999
_PLATE_RE = re.compile(r"(?<![\u0E00-\u0E7F\d])(\d?[ก-ฮ]{1,3})\s*[-–]?\s*(\d{1,4})(?!\d)")

CAR_COLORS = [
    "น้ำเงินเข้ม", "เขียวเข้ม", "เขียวอ่อน", "ฟ้าอ่อน", "ชมพูอ่อน", "น้ำเงิน", "น้ำตาล", "บรอนซ์",
    "แดง", "ชมพู", "ส้ม", "เหลือง", "เขียว", "ฟ้า", "ม่วง", "ขาว", "ดำ", "เทา", "เงิน", "ทอง", "ครีม",
]
_COLOR_RE = re.compile(
    r"(?:สี|รถ)\s*(?:สี)?\s*(" + "|".join(sorted(CAR_COLORS, key=len, reverse=True)) + r")"
)


def extract_plate(question: str) -> str | None:
    """ดึงทะเบียนรถ (อักษร+เลข) ออกจากคำถาม คืน None ถ้าไม่เจอ"""
    q = (question or "").translate(_THAI_DIGITS)
    for m in _PLATE_RE.finditer(q):
        head = m.group(1)
        # มีเลขนำ (5กก-1555) ถือเป็นทะเบียนเลย ถ้าไม่มี ต้องมีคำว่า ทะเบียน/ป้าย ในประโยคด้วย
        # กันไปจับคำอย่าง "รถ 2 คัน"
        if head[0].isdigit() or "ทะเบียน" in q or "ป้าย" in q:
            return f"{head}{m.group(2)}"
    return None


def extract_car_color(question: str) -> str | None:
    """ดึงสีรถที่ผู้ใช้พูดถึง เช่น 'สีรถแดง', 'รถสีขาว', 'สีดำ'"""
    m = _COLOR_RE.search(question or "")
    return m.group(1) if m else None
