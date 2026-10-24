# -*- coding: utf-8 -*-
"""
taksa_jon.py
------------
ทักษาจรประจำปี: ปีนี้ผู้ใช้ "ตกภูมิ" ใดของทักษา (บริวาร อายุ เดช ศรี มูละ อุตสาหะ มนตรี กาลกรรณี)

แหล่งอ้างอิง: พ.อ. ประเพิน สุทธิบุตร. โหราศาสตร์สำเร็จ. (สแกนจากหอสมุดแห่งชาติ)
  - หน้า 154-155  แผนผังทักษาพยากรณ์ (ภูมิ 1-8 ตามดาว 1 อาทิตย์ ... 8 ราหู, ภูมิ 9 เกตุ)
  - หน้า 156-157  การนับทักษา (เวียนขวาตามรอบแผนผัง) และความหมายของทักษา
  - หน้า 162-163  การคิดตกภูมิทักษาจร และวิธีนับ (นับเข้าภูมิ 9 ก่อนภูมิ 2)
ตรวจกับตัวอย่างในหนังสือแล้ว (หน้า 162: เกิดวันเสาร์ เศษ 9 ตกภูมิพุธ)

ข้อจำกัด:
  - ใช้ได้กับ "ดวงช่วงปีนี้" ไม่ใช่ดวงรายวัน
  - ภูมิ 9 (เกตุ) ถือเป็นภูมิพฤหัสตามที่หนังสืออธิบาย (บางตำราให้ตกกาลกรรณี)
  - คนเกิดวันพุธไม่แยกกลางวัน/กลางคืน (หนังสือกล่าวว่าบางสำนักให้ใช้ราหูเริ่มต้น)
  - ใช้อาทิตย์จากสุริยยาตร์ เทียบกับอาทิตย์ตอนเกิด (ไม่ทราบเวลาเกิดใช้เที่ยงวัน)
"""
from __future__ import annotations

from datetime import date, time

from . import suriyayart

SOURCE = "ประเพิน สุทธิบุตร. โหราศาสตร์สำเร็จ. หอสมุดแห่งชาติ (หน้า 154-163) — ทักษาจร"

# ภูมิ 1..8 = อาทิตย์ จันทร์ อังคาร พุธ พฤหัส ศุกร์ เสาร์ ราหู
RING = [1, 2, 3, 4, 7, 5, 8, 6]            # เวียนขวารอบแผนผัง (หน้า 156)
CYCLE9 = [1, 9, 2, 3, 4, 7, 5, 8, 6]       # วงนับทักษาจร มีภูมิ 9 แทรกก่อนภูมิ 2 (หน้า 163)
ROLES = ["บริวาร", "อายุ", "เดช", "ศรี", "มูละ", "อุตสาหะ", "มนตรี", "กาลกรรณี"]
# ดัชนีวันแบบไทย (อาทิตย์=0 .. เสาร์=6) -> ภูมิของวันเกิด
DAY_TO_BHUMI = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7}
PLANET = {1: "อาทิตย์", 2: "จันทร์", 3: "อังคาร", 4: "พุธ", 5: "พฤหัสบดี", 6: "ศุกร์", 7: "เสาร์", 8: "ราหู", 9: "เกตุ"}

# ความหมายตามหน้า 156-157 (เรียบเรียงใหม่ด้วยถ้อยคำของโครงการ)
MEANING = {
    "บริวาร": "คนรอบข้าง ลูกน้อง ครอบครัวใกล้ชิด",
    "อายุ": "ช่วงชีวิต สุขภาพ ความเจ็บไข้",
    "เดช": "อำนาจ ชื่อเสียง ความก้าวหน้า",
    "ศรี": "ความเจริญ ทรัพย์ ลาภ สิ่งมงคล",
    "มูละ": "รากฐาน ที่อยู่อาศัย หลักแหล่ง",
    "อุตสาหะ": "ความเพียร ความอดทน",
    "มนตรี": "ที่ปรึกษา ผู้ใหญ่ ผู้สนับสนุน",
    "กาลกรรณี": "อุปสรรค ศัตรู ความทุกข์",
}


def _sun_long(d: date, tf: float = 0.5) -> float:
    i, deg, lip = suriyayart.sun_rasi(d.day, d.month, d.year, tf)
    return i * 30 + deg + lip / 60


def birth_bhumi(birth_date: date) -> int:
    return DAY_TO_BHUMI[(birth_date.weekday() + 1) % 7]


def role_of(bhumi: int, birth_b: int) -> str:
    """ตำแหน่งทักษา (บริวาร..กาลกรรณี) ของภูมิ bhumi สำหรับคนที่ภูมิวันเกิดคือ birth_b"""
    if bhumi == 9:
        bhumi = 5
    return ROLES[(RING.index(bhumi) - RING.index(birth_b)) % 8]


def jon_number(birth_date: date, today: date, birth_time: time | None = None) -> int:
    """เลข "ปีที่ใช้หาร 9" = ปีปัจจุบัน - ปีเกิด (+1 ถ้าอาทิตย์จรผ่านอาทิตย์กำเนิดแล้ว) (หน้า 162)"""
    n = today.year - birth_date.year
    tf = 0.5 if birth_time is None else (birth_time.hour + birth_time.minute / 60) / 24
    natal = _sun_long(birth_date, tf)
    ref = _sun_long(date(today.year, 1, 1))
    passed = (_sun_long(today) - ref) % 360 >= (natal - ref) % 360
    return n + (1 if passed else 0)


def yearly_taksa_jon(birth_date: date, today: date, birth_time: time | None = None) -> dict:
    b = birth_bhumi(birth_date)
    n = jon_number(birth_date, today, birth_time)
    r = n % 9 or 9
    landed = CYCLE9[(CYCLE9.index(b) + r - 1) % 9]   # นับภูมิวันเกิดเป็นหนึ่ง
    role = role_of(landed, b)
    return {
        "birth_bhumi": b,
        "number": n,
        "remainder": r,
        "landed_bhumi": landed,
        "landed_planet": PLANET[landed],
        "role": role,
        "meaning": MEANING[role],
        "source": SOURCE,
    }
