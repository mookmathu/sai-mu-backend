# -*- coding: utf-8 -*-
"""
number_meanings.py
------------------
ความหมายรายเลข 0-100 สำหรับหน้า "เลขศาสตร์" (ผลรวมของชื่อ / เบอร์โทร / ทะเบียนรถ)

ข้อมูลอยู่ที่ app/data/number_meanings.json — เรียบเรียงจากข้อความของ chunk number-0..100 ใน
ฐานความรู้ RAG (chunks_clean.json) เป็นภาษาสุภาพอ่านง่าย แบ่งเป็น ภาพรวม / จุดเด่น / ข้อควรระวัง /
สิ่งที่เหมาะ แต่ละเลข เป็นความเชื่อตามตำรา ไม่แสดงแหล่งอ้างอิงในแอป

ผลรวมที่เกิน 100 ลดทอนตามกฎเดียวกับ numerology.reduce_name_total ก่อนค้นหา
(101-109 → หลักร้อย+หน่วย เช่น 105 → 15, ตั้งแต่ 110 → หลักสิบ+หน่วย เช่น 124 → 24)
ไฟล์ข้อมูลไม่มี/เสีย → คืน None (ฝั่งแอปจะโชว์คำอธิบายกลุ่มเดิมแทน ไม่ error)
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from .numerology import reduce_name_total

logger = logging.getLogger("uvicorn.error")
_PATH = Path(__file__).parent / "data" / "number_meanings.json"


@lru_cache(maxsize=1)
def _load() -> dict[str, dict]:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("โหลด number_meanings.json ไม่สำเร็จ")
        return {}


def get_meaning(total: int) -> dict | None:
    """คืนความหมายของผลรวม total (ลดทอนให้อยู่ใน 0-100 ก่อน) หรือ None ถ้าไม่มีข้อมูล"""
    if total is None or total < 0:
        return None
    n = reduce_name_total(total)
    item = _load().get(str(n))
    if not item:
        return None
    return {"number": n, "from_total": total, **item, "profiles": get_profiles(n)}


# ---------- โปรไฟล์ดาวประจำเลขหลักเดียว (0-9) ----------
_DIGIT_PATH = Path(__file__).parent / "data" / "digit_profiles.json"


@lru_cache(maxsize=1)
def _load_digits() -> dict[str, dict]:
    try:
        return json.loads(_DIGIT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("โหลด digit_profiles.json ไม่สำเร็จ")
        return {}


def _digit_entry(d: int, role: str) -> dict | None:
    p = _load_digits().get(str(d))
    if not p:
        return None
    return {"number": d, "role": role, **p}


def get_profiles(number: int) -> list[dict]:
    """ดาวประจำเลขแต่ละหลักของ number (0-100) + เลขรวมที่บวกกันได้ เช่น 41 → เลข 4, 1 และ 5"""
    if number is None or number < 0:
        return []
    digits = [int(c) for c in str(number)]
    out: list[dict] = []
    seen: set[int] = set()
    if len(digits) == 1:
        roles = ["เลขหลัก"]
    elif len(digits) == 2:
        roles = ["เลขหลักสิบ", "เลขหลักหน่วย"]
    else:
        roles = ["เลขหลักร้อย", "เลขหลักสิบ", "เลขหลักหน่วย"]
    for d, r in zip(digits, roles):
        if d in seen:
            continue
        seen.add(d)
        e = _digit_entry(d, r)
        if e:
            out.append(e)
    root = number
    while root > 9:
        root = sum(int(c) for c in str(root))
    if len(digits) > 1 and root not in seen and root != 0:
        e = _digit_entry(root, "ผลรวมของเลขทั้งหมด")
        if e:
            out.append(e)
    return out
