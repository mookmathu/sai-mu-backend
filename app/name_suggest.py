"""แนะนำชื่อไทย 3-4 ชื่อ โดยคัดจากรายชื่อใน app/data/thai_names.json

เงื่อนไขการคัด (คำนวณจริงจากโค้ด ไม่ให้ AI เดา):
- อักษรตัวแรกของชื่อต้องไม่ใช่หมวดกาลกิณีของวันเกิด (taksa)
- ผลรวมเลขศาสตร์ของชื่อต้องไม่มีข้อควรระวัง (name_numerology) และให้ความสำคัญกับเลขกลุ่มดีก่อน
- พยายามให้ชื่อที่ได้มาจากหมวดทักษาหลากหลาย ไม่ซ้ำหมวดเดียวกันหมด
"""
from __future__ import annotations

import json
import random
import re
from datetime import date
from pathlib import Path

from . import name_numerology, taksa

_DATA = Path(__file__).parent / "data" / "thai_names.json"

_SUGGEST_PATTERNS = [
    r"(แนะนำ|ช่วยคิด|ช่วยตั้ง|ขอ|อยากได้|อยากให้ช่วย|ตั้ง)\s*(ชื่อ)",
    r"ชื่อ\s*(อะไร|ไหน)\s*ดี",
    r"ตั้งชื่อ(ให้|ลูก|หลาน|เด็ก)",
    r"(ชื่อ)(ลูก|หลาน)(ชาย|สาว)?\s*(อะไร|แนะนำ)",
]
_SPECIFIC_NAME = re.compile(r"[\"'“”‘’「」『』]")
_CHECK_WORDS = ["ดีไหม", "ดีมั้ย", "เป็นมงคลไหม", "เช็คชื่อ", "เช็กชื่อ", "ใช้ได้ไหม", "เหมาะไหม"]

_DAYS = {"อาทิตย์": 0, "จันทร์": 1, "อังคาร": 2, "พุธ": 3, "พฤหัส": 4, "ศุกร์": 5, "เสาร์": 6}


def is_name_suggest_question(question: str) -> bool:
    """ถามหาชื่อให้ (ไม่ได้ระบุชื่อเฉพาะมาให้เช็ค) เช่น 'แนะนำชื่อลูกชายเกิดวันอังคาร'"""
    if _SPECIFIC_NAME.search(question) or any(w in question for w in _CHECK_WORDS):
        return False
    return any(re.search(p, question) for p in _SUGGEST_PATTERNS)


def extract_day_index(question: str) -> int | None:
    """ดึงวันเกิดที่พูดถึงในคำถาม (0=อาทิตย์ ... 6=เสาร์) ถ้าไม่มีคืน None"""
    for word, idx in _DAYS.items():
        if word in question:
            return idx
    return None


def extract_gender(question: str) -> str | None:
    if re.search(r"ลูกสาว|หลานสาว|ผู้หญิง|เด็กหญิง|ผู้หญิง|ชื่อหญิง|\bหญิง", question):
        return "f"
    if re.search(r"ลูกชาย|หลานชาย|ผู้ชาย|เด็กชาย|ชื่อชาย|\bชาย", question):
        return "m"
    return None


def load_names() -> list[dict]:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def suggest_names(day_index: int, gender: str | None = None, count: int = 4,
                  rng: random.Random | None = None) -> list[dict]:
    """คืนรายการชื่อ [{name, meaning, first_letter, category, number, number_group}]"""
    rng = rng or random.Random()
    num_gender = {"m": "male", "f": "female"}.get(gender)
    good, ok = [], []
    for item in load_names():
        if gender and item["gender"] not in (gender, "u"):
            continue
        cat = taksa.classify_consonant(taksa.first_consonant(item["name"]), day_index)
        if cat is None or cat["name"] == "กาลกิณี":
            continue
        total = name_numerology.total(item["name"])
        tags = name_numerology.tags_for(total, num_gender)
        if any(t.startswith("caution") for t in tags):
            continue
        entry = {
            "name": item["name"],
            "meaning": item["meaning"],
            "first_letter": taksa.first_consonant(item["name"]),
            "category": cat["name"],
            "category_meaning": cat["meaning"],
            "number": total,
            "number_group": "good" if "good" in tags else ("middle" if "middle" in tags else "neutral"),
        }
        (good if "good" in tags else ok).append(entry)
    rng.shuffle(good)
    rng.shuffle(ok)
    pool = good + ok
    picked, used = [], set()
    for e in pool:                      # รอบแรก: ไม่ซ้ำหมวดทักษา
        if e["category"] not in used and len(picked) < count:
            picked.append(e)
            used.add(e["category"])
    for e in pool:                      # รอบสอง: เติมให้ครบจำนวน
        if len(picked) >= count:
            break
        if e not in picked:
            picked.append(e)
    return picked


def facts_text(day_index: int, names: list[dict]) -> str:
    day = taksa.DAY_NAMES_THAI[day_index]
    lines = [f"ชื่อที่คัดไว้แล้ว (คำนวณจริงจากระบบ) สำหรับคนเกิดวัน{day}:"]
    for n in names:
        lines.append(
            f"- {n['name']} ความหมาย: {n['meaning']} | ขึ้นต้นด้วย {n['first_letter']} "
            f"อยู่หมวด {n['category']} ({n['category_meaning']}) | เลขศาสตร์ชื่อรวม {n['number']}"
            f"{' (กลุ่มเลขดี)' if n['number_group'] == 'good' else ''}"
        )
    return "\n".join(lines)
