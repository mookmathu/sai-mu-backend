# -*- coding: utf-8 -*-
"""
name_numerology.py
------------------
โหราเลขศาสตร์ชื่อ ตามตารางค่าตัวอักษรและกลุ่มเลขของเว็บมหามงคล
(https://www.mahamongkol.com/content.php?id=47 อ้างตำราท่านอาจารย์พลูหลวง)

กติกา
- แต่ละตัวอักษร/สระ/วรรณยุกต์ในตารางมีค่า 1-9 ตัวอักษรที่ไม่อยู่ในตาราง (ช่องว่าง ฯ ๆ ตัวเลข อังกฤษ) ไม่นับ
- ไม่ลดผลรวมเหลือหลักเดียว (ผลรวม 105 ก็เป็น 105) แล้วนำผลรวมไปเทียบกลุ่มเลข
- วิเคราะห์ 3 ส่วน: ชื่อ (40%), นามสกุล (20%), ชื่อ+นามสกุล (40%)
- ตรวจ "เลขกลับ" ด้วย (13 -> 31)
- เลขบางตัวอยู่ได้หลายกลุ่ม (เช่น 19, 23) จึงคืนเป็นรายการ tag

ข้อควรรู้: ตัวที่มี ์ กำกับ (การันต์) ตารางให้ ์ มีค่า 9 ตัวเอง ส่วนตัวอักษรที่ถูกการันต์ครอบ
ไม่มีข้อมูลว่านับหรือไม่ จึงนับตามตัวอักษรไว้ก่อน (ตั้ง SKIP_SILENCED=True ถ้าต้องการไม่นับ)
ภาพตารางมีเครื่องหมายเล็ก ๆ ที่ผู้ใช้ยืนยันเทียบกับภาพจริงให้แล้ว ถ้าตารางต้นฉบับต่างไปแก้ที่ TABLE ที่เดียว
"""
from __future__ import annotations

from .number_meanings import get_meaning

TABLE: dict[int, str] = {
    1: "กดถทภ" + "ฤๅา" + "ำ" + "่" + "ุ",
    2: "ขชงบป" + "เแ" + "้" + "ู",
    3: "ฆตฑฒ" + "๋",
    4: "คธญรษ" + "โะ" + "ั" + "ิ",
    5: "ฉณฌนมหฎฬฮ" + "ึ",
    6: "จลวอ" + "ใ",
    7: "ซศส" + "๊" + "ี" + "ื",
    8: "ผฝพฟย" + "็",
    9: "ฏฐ" + "ไ" + "์",
}

SKIP_SILENCED = False

CHAR_VALUE: dict[str, int] = {ch: n for n, chars in TABLE.items() for ch in chars}

WEIGHTS = {"first": 40, "last": 20, "full": 40}

GOOD = {2, 4, 5, 6, 9, 14, 15, 19, 23, 24, 36, 41, 42, 45, 50, 51, 54, 55, 56, 59,
        63, 65, 90, 95, 99, 100, 104, 105}
MIDDLE = {32, 40, 44, 46, 64, 79, 89, 97, 98}
CAUTION_FEMALE = {16, 17, 18, 19, 20, 109}   # ความรัก/ชีวิตคู่
CAUTION_MALE = {13, 23, 31, 32, 46, 64, 68, 86}  # ครอบครัว/การงาน

TAG_TEXT = {
    "good": "เลขกลุ่มที่ส่งเสริมความสำเร็จ ความมั่นคง ชื่อเสียง และการเงิน",
    "middle": "เลขกลุ่มกลาง ผลออกมาผสม ต้องใช้ความพยายามมากกว่าปกติหรือดีเป็นบางช่วง",
    "caution_female": "มีข้อควรระวังเรื่องความรักและชีวิตคู่ ควรใส่ใจการสื่อสารและการเลือกคู่",
    "caution_male": "มีข้อควรระวังเรื่องความสัมพันธ์ในครอบครัวและการงาน ควรรอบคอบกับการตัดสินใจ",
}


def char_values(text: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    chars = list(text or "")
    for i, ch in enumerate(chars):
        v = CHAR_VALUE.get(ch)
        if v is None:
            continue
        if SKIP_SILENCED and i + 1 < len(chars) and chars[i + 1] == "์" and ch != "์":
            continue
        out.append((ch, v))
    return out


def total(text: str) -> int:
    return sum(v for _, v in char_values(text))


def reverse_number(n: int) -> int:
    return int(str(n)[::-1])


def tags_for(n: int, gender: str | None = None) -> list[str]:
    """gender: 'male' | 'female' | None (None = แสดงข้อควรระวังของทั้งสองเพศ)"""
    tags = []
    if n in GOOD:
        tags.append("good")
    if n in MIDDLE:
        tags.append("middle")
    if n in CAUTION_FEMALE and gender in (None, "female"):
        tags.append("caution_female")
    if n in CAUTION_MALE and gender in (None, "male"):
        tags.append("caution_male")
    return tags


def _part(text: str, weight: int, gender: str | None) -> dict:
    s = total(text)
    r = reverse_number(s) if s else 0
    return {
        "text": text,
        "total": s,
        "weight": weight,
        "tags": tags_for(s, gender),
        "reverse_total": r,
        "reverse_tags": tags_for(r, gender) if r != s else [],
        "notes": [TAG_TEXT[t] for t in tags_for(s, gender)],
        "meaning": get_meaning(s) if s else None,
    }


def analyze_name(first: str, last: str = "", gender: str | None = None) -> dict:
    first = (first or "").strip()
    last = (last or "").strip()
    if not first:
        raise ValueError("ต้องมีชื่อ")
    if gender not in (None, "male", "female"):
        gender = None
    return {
        "first": _part(first, WEIGHTS["first"], gender),
        "last": _part(last, WEIGHTS["last"], gender),
        "full": _part(first + last, WEIGHTS["full"], gender),
        "source": "มหามงคล (ตำราท่านอาจารย์พลูหลวง) https://www.mahamongkol.com/content.php?id=47",
    }
