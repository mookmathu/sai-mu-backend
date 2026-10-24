# -*- coding: utf-8 -*-
"""
taksa.py
--------
คำนวณ "ทักษาปกรณ์" (ระบบตั้งชื่อมงคลของไทย) จากวันเกิด — ใช้ตรวจว่าอักษรตัวแรก
ของชื่อที่จะตั้ง อยู่ในหมวดไหนใน 8 หมวดของทักษา (บริวาร/อายุ/เดช/ศรี/มูละ/
อุตสาหะ/มนตรี/กาลกิณี) สำหรับคนเกิดวันนั้นๆ

หลักการ (ตามตำราทักษาปกรณ์ที่แพร่หลาย — ดูที่มาที่ CONSONANT_GROUPS):
    พยัญชนะไทยแบ่งเป็น 8 กลุ่ม แต่ละกลุ่มเป็น "กลุ่มประจำวัน" ของวันหนึ่ง คนเกิดวันไหนให้กลุ่ม
    ประจำวันนั้นเป็นหมวดบริวาร แล้วเดินตามวงทักษา (ดู DAY_START_GROUP) ไปทีละกลุ่ม ครบ 8 หมวด
    (บริวาร อายุ เดช ศรี มูละ อุตสาหะ มนตรี กาลกิณี)

    หมวดสำคัญที่สุดที่ต้องระวังคือ "กาลกิณี" (category_index = 7) เพราะเชื่อกันว่า
    ถ้าอักษรต้นชื่อตกในกลุ่มนี้ของวันเกิดตัวเอง จะไม่เป็นมงคล ควรเลี่ยง

ข้อจำกัดที่ควรรู้:
    - ระบบพื้นฐานนี้แยกแค่ 7 วันในสัปดาห์ ยังไม่แยก "พุธกลางวัน" กับ "พุธกลางคืน
      (ราหู)" ออกจากกันแบบตำราเต็มรูปแบบ ซึ่งบางตำราถือว่าเป็นคนละหมวดกัน
    - การตั้งชื่อจริงในทางปฏิบัติมักดูอักษรทุกตัวในชื่อประกอบกัน ไม่ใช่แค่ตัวแรก
      ฟังก์ชันนี้เน้นเช็คเฉพาะ "อักษรตัวแรก" ซึ่งถือเป็นน้ำหนักสำคัญที่สุดตามความเชื่อ
      ทั่วไป แต่ไม่ใช่การฟันธงว่าชื่อทั้งชื่อดีหรือไม่ดีแบบสมบูรณ์
    - เป็นความเชื่อทางโหราศาสตร์ไทย ไม่ใช่ข้อเท็จจริงทางวิทยาศาสตร์
"""
from __future__ import annotations

import re
from datetime import date

# กลุ่มพยัญชนะไทย 8 กลุ่ม (ดัชนี 0-7) เรียงตาม "วงทักษา" = ลำดับดาว อาทิตย์ จันทร์ อังคาร พุธ เสาร์ พฤหัสบดี
# ราหู(พุธกลางคืน) ศุกร์ กลุ่มประจำวัน (นามอัฐเคราะห์) คือ
#   0 อาทิตย์ = อ+สระ, 1 จันทร์ = กขคฆง, 2 อังคาร = จฉชซฌญ, 3 พุธ(กลางวัน) = ฎฏฐฑฒณ,
#   4 เสาร์ = ดตถทธน, 5 พฤหัสบดี = บปผฝพฟภม, 6 ราหู(พุธกลางคืน) = ยรลว, 7 ศุกร์ = ศษสหฬฮ
# ที่มา: ตาราง นามอัฐเคราะห์ ในบทความ "ทักษาปกรณ์ ตำรายอดนิยมตั้งชื่อคนไทย" (ศิลปวัฒนธรรม, silpa-mag.com)
# และตรวจกับอักษรกาลกิณีที่บทความ Wongnai "ชื่อมงคลลูกชาย" ระบุไว้ (อาทิตย์ห้าม ศษสหฬฮ, จันทร์ห้ามสระ,
# อังคารห้าม กขคฆง, เสาร์ห้าม ฎฏฐฑฒณ)
CONSONANT_GROUPS: list[list[str]] = [
    list("อาอิอีอุอูเอโอ"),  # กลุ่ม 0 อาทิตย์: สระอิสระ/อ
    list("กขคฆง"),  # กลุ่ม 1 จันทร์
    list("จฉชซฌญ"),  # กลุ่ม 2 อังคาร
    list("ฎฏฐฑฒณ"),  # กลุ่ม 3 พุธ (กลางวัน)
    list("ดตถทธน"),  # กลุ่ม 4 เสาร์
    list("บปผฝพฟภม"),  # กลุ่ม 5 พฤหัสบดี
    list("ยรลว"),  # กลุ่ม 6 ราหู (พุธกลางคืน)
    list("ศษสหฬฮ"),  # กลุ่ม 7 ศุกร์
]

# วันเกิด (day_index อาทิตย์=0..เสาร์=6) -> ดัชนีกลุ่มที่เป็น "บริวาร" ของวันนั้น (กลุ่มประจำวัน)
# แล้วหมวดถัดไป (อายุ เดช ศรี ... กาลกิณี) เดินไปตามวงทักษา ครบ 8 หมวด
DAY_START_GROUP: list[int] = [0, 1, 2, 3, 5, 7, 4]  # อา จ อ พุธ พฤหัส ศุกร์ เสาร์

# หมวดทักษา 8 หมวด เรียงตามลำดับ category_index 0-7 พร้อมความหมาย/น้ำหนักคร่าวๆ
TAKSA_CATEGORIES: list[dict] = [
    {"name": "บริวาร", "meaning": "เรื่องบริวาร ลูกน้อง ผู้ใต้บังคับบัญชา การดูแลคนรอบข้าง"},
    {"name": "อายุ", "meaning": "เรื่องสุขภาพ อายุขัย ความมั่นคงปลอดภัยในชีวิต"},
    {"name": "เดช", "meaning": "เรื่องอำนาจ บารมี ตำแหน่งหน้าที่การงาน ความเป็นผู้นำ"},
    {"name": "ศรี", "meaning": "เรื่องความรุ่งเรือง โชคลาภ ความรัก เสน่ห์ดึงดูด"},
    {"name": "มูละ", "meaning": "เรื่องรากฐาน ทรัพย์สิน ครอบครัว ที่อยู่อาศัย"},
    {"name": "อุตสาหะ", "meaning": "เรื่องความขยันหมั่นเพียร การทำงานหนัก ความบากบั่น"},
    {"name": "มนตรี", "meaning": "เรื่องผู้อุปถัมภ์ ผู้ใหญ่ที่ให้การสนับสนุน ที่ปรึกษาที่ดี"},
    {"name": "กาลกิณี", "meaning": "กลุ่มอักษรต้องห้าม เชื่อว่านำเรื่องไม่เป็นมงคลมาให้ ไม่ควรใช้ขึ้นต้นชื่อ"},
]

# ชื่อวันในสัปดาห์ เรียงตามดัชนี day_index 0-6 (อาทิตย์=0 ... เสาร์=6) ให้ตรงกับสูตร
DAY_NAMES_THAI = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"]


def get_thai_day_index(birth_date: date) -> int:
    """แปลง date เป็นดัชนีวัน 0=อาทิตย์ ... 6=เสาร์ (Python's date.weekday()
    ให้ จันทร์=0...อาทิตย์=6 ซึ่งเป็นคนละแบบกับที่สูตรทักษาต้องการ เลยต้องแปลง)"""
    return (birth_date.weekday() + 1) % 7


def get_taksa_mapping(day_index: int) -> dict[str, list[str]]:
    """คืน dict {ชื่อหมวด: [รายชื่อพยัญชนะในหมวดนั้น]} ทั้ง 8 หมวด สำหรับวันเกิดที่ระบุ"""
    mapping = {}
    for category_index, category in enumerate(TAKSA_CATEGORIES):
        group_index = (DAY_START_GROUP[day_index] + category_index) % 8
        mapping[category["name"]] = CONSONANT_GROUPS[group_index]
    return mapping


def day_table_text(day_index: int) -> str:
    """ข้อความตารางหมวดทักษาของวันเกิดนี้ (สร้างจากโค้ดโดยตรง ไม่พึ่งข้อความที่ฝังใน ChromaDB
    จะได้ตรงกับการคำนวณเสมอ)"""
    mapping = get_taksa_mapping(day_index)
    parts = []
    for name, letters in mapping.items():
        if letters is CONSONANT_GROUPS[0]:
            shown_text = " ".join(_GROUP0_DISPLAY)
        else:
            shown_text = "".join(dict.fromkeys(letters))
        parts.append(f"{name} ({shown_text})")
    day = DAY_NAMES_THAI[day_index]
    kal_letters = mapping['กาลกิณี']
    kal = " ".join(_GROUP0_DISPLAY) if kal_letters is CONSONANT_GROUPS[0] else ''.join(dict.fromkeys(kal_letters))
    return (
        f"สำหรับคนเกิดวัน{day} พยัญชนะไทยแบ่งเป็น 8 หมวดดังนี้: " + " / ".join(parts)
        + f" หมวดที่ควรหลีกเลี่ยงเป็นพิเศษสำหรับการตั้งชื่อคือหมวดกาลกิณี ได้แก่อักษร {kal} "
        f"เพราะเชื่อว่าไม่เป็นมงคลสำหรับคนเกิดวัน{day}"
    )


def classify_consonant(consonant: str, day_index: int) -> dict | None:
    """หาว่าพยัญชนะตัวเดียว (เช่น 'ภ') อยู่หมวดไหนของวันเกิดนี้ คืน dict
    {"name": ..., "meaning": ...} หรือ None ถ้าไม่ใช่พยัญชนะไทยที่รู้จัก"""
    for category_index, category in enumerate(TAKSA_CATEGORIES):
        group_index = (DAY_START_GROUP[day_index] + category_index) % 8
        if consonant in CONSONANT_GROUPS[group_index]:
            return category
    return None


_LEADING_VOWELS = "เแโใไ"


def first_consonant(name: str) -> str:
    """อักษรตัวแรกของชื่อที่ใช้ดูทักษา — ข้ามสระหน้า (เ แ โ ใ ไ) ที่เขียนนำพยัญชนะ
    เช่น "เกษม" ดู "ก" ไม่ใช่ "เ" ถ้าสระหน้าตามด้วย "อ" (เช่น "เอก") จะได้ "อ" ซึ่งอยู่กลุ่มอ/สระ
    ถ้าชื่อขึ้นต้นด้วยสระอื่นหรืออักษรที่ไม่ใช่ไทย ใช้ตัวแรกตามเดิม"""
    name = name.strip()
    i = 0
    while i < len(name) - 1 and name[i] in _LEADING_VOWELS:
        i += 1
    return name[i] if name else ""


def check_name_first_letter(name: str, birth_date: date) -> dict:
    """เช็คอักษรตัวแรกของชื่อ (ตัวที่มีน้ำหนักสำคัญที่สุดตามความเชื่อทักษา) ว่า
    ตกหมวดไหนสำหรับคนเกิดวันนี้ คืนข้อมูลครบสำหรับเอาไปประกอบคำตอบ:
        {
            "first_letter": "ภ",
            "day_name": "อังคาร",
            "category": {"name": "ศรี", "meaning": "..."},
            "is_kalakin": False,
        }
    """
    name = name.strip()
    if not name:
        raise ValueError("ชื่อว่างเปล่า")

    day_index = get_thai_day_index(birth_date)
    day_name = DAY_NAMES_THAI[day_index]

    first_letter = first_consonant(name)
    category = classify_consonant(first_letter, day_index)

    return {
        "first_letter": first_letter,
        "day_name": day_name,
        "category": category,
        "is_kalakin": bool(category and category["name"] == "กาลกิณี"),
    }


# อักษรของกลุ่ม 0 (สระอิสระ/อ) แสดงเป็นพยางค์ให้อ่านง่าย — ตามข้อความตำรา "อาอิอีอุอูเอโอ"
_GROUP0_DISPLAY = ["อ", "อา", "อิ", "อี", "อุ", "อู", "เอ", "โอ"]


def suggest_first_letters(birth_date: date) -> dict:
    """ตารางอักษรต้นชื่อของวันเกิดนี้ครบทั้ง 8 หมวด สำหรับคนที่กำลังจะตั้งชื่อ

    ตำราที่มีบอกเพียงว่า "หมวดกาลกิณีควรเลี่ยง" ไม่ได้จัดอันดับว่าหมวดไหนดีกว่ากัน
    ฟังก์ชันนี้จึงไม่ฟันธงว่าหมวดไหน "ดีที่สุด" แค่แสดงความหมายของแต่ละหมวดให้ผู้ใช้
    เลือกตามเรื่องที่อยากเสริม และทำเครื่องหมายหมวดที่ควรเลี่ยง (กาลกิณี) เท่านั้น
    """
    day_index = get_thai_day_index(birth_date)
    categories = []
    for category_index, category in enumerate(TAKSA_CATEGORIES):
        group_index = (DAY_START_GROUP[day_index] + category_index) % 8
        letters = _GROUP0_DISPLAY if group_index == 0 else list(CONSONANT_GROUPS[group_index])
        categories.append(
            {
                "name": category["name"],
                "meaning": category["meaning"],
                "letters": list(letters),
                "avoid": category["name"] == "กาลกิณี",
            }
        )
    return {"day_name": DAY_NAMES_THAI[day_index], "categories": categories}


# ---------------------------------------------------------------------
# ตัวช่วยจับ "เจตนา" ว่าผู้ใช้กำลังถามเช็คชื่อมงคล + ดึงชื่อที่อยากเช็คออกจากประโยค
# เป็น heuristic ง่ายๆ (keyword + regex) เหมาะกับขอบเขตโปรเจกต์ปัญหาพิเศษ ไม่ใช่ NLU
# เต็มรูปแบบ — ถ้าดึงไม่ได้ ให้ผู้เรียกไป fallback ตอบแบบทั่วไปแทน
# ---------------------------------------------------------------------
NAME_CHECK_KEYWORDS = ["ตั้งชื่อ", "เช็คชื่อ", "เช็กชื่อ", "ชื่อมงคล", "ทักษา", "ชื่อเป็นมงคล"]

_QUOTE_PATTERN = re.compile(r'["\'“”‘’「」『』]([ก-๙]{1,30})["\'“”‘’「」『』]')
_NAME_KEYWORD_PATTERN = re.compile(r"ชื่อ\s*([ก-๙]{2,30})")
_TRAILING_QUESTION_WORDS = [
    "เป็นมงคลไหม", "ใช้ได้ไหม", "โอเคไหม", "มงคลไหม", "ดีมั้ย", "ดีไหม", "เหมาะไหม",
    "คืออะไร", "รวมแล้วเลขอะไร", "ได้เลขอะไร", "เลขอะไร",
]
# คำลงท้ายสุภาพที่คนไทยพิมพ์ติดท้ายประโยคเกือบทุกครั้ง (ค่ะ/คะ/ครับ ฯลฯ) — ถ้าไม่ตัด
# ออกก่อน จะรวมติดไปกับชื่อที่ดึงได้ผิดๆ โดยเฉพาะเวลาพิมพ์แบบไม่เว้นวรรคคั่นระหว่างชื่อ
# กับคำถามท้ายประโยค (เช่น "ชื่อภูมิดีไหมคะ" ไม่มีช่องว่างเลย ซึ่งเป็นการพิมพ์ภาษาไทย
# แบบธรรมชาติที่สุด เพราะปกติภาษาไทยไม่เว้นวรรคระหว่างคำอยู่แล้ว)
_POLITE_PARTICLES = ["ค่ะ", "คะ", "ครับ", "จ้า", "จ้ะ", "ฮะ", "น้า", "นะคะ", "นะครับ", "นะ"]

# คำเชื่อม/คำฟุ่มเฟือยที่มักแทรกอยู่ระหว่างชื่อกับคำถามท้ายประโยค เช่น "ตั้งชื่อกิตติ
# ศักดิ์ให้ดีไหมคะ" (มีคำว่า "ให้" คั่นอยู่) — เสี่ยงตัดชื่อที่ลงท้ายด้วยคำเหล่านี้จริงๆ
# น้อยมาก จึงปลอดภัยที่จะตัดออกด้วย
_FILLER_WORDS = ["ให้หน่อย", "ให้ที", "ให้", "หน่อย", "ดูหน่อย", "ที"]


def _strip_trailing_noise(candidate: str) -> str:
    """ตัดคำถามท้ายประโยค (_TRAILING_QUESTION_WORDS) และคำลงท้ายสุภาพ
    (_POLITE_PARTICLES) ออกจากท้ายสตริงซ้ำไปเรื่อยๆ จนกว่าจะตัดไม่ได้อีกแล้ว — ต้องทำ
    แบบวนซ้ำ (ไม่ใช่ตัดครั้งเดียว) เพราะบางประโยคมีทั้งคำถามและคำลงท้ายสุภาพต่อกัน เช่น
    "ดีไหมคะ" ต้องตัด "คะ" ออกก่อนถึงจะเจอ "ดีไหม" ให้ตัดต่อได้อีกที"""
    changed = True
    while changed:
        changed = False
        for suffix in _TRAILING_QUESTION_WORDS + _POLITE_PARTICLES + _FILLER_WORDS:
            if candidate.endswith(suffix) and len(candidate) > len(suffix):
                candidate = candidate[: -len(suffix)]
                changed = True
    return candidate


def is_name_check_question(question: str) -> bool:
    """เช็คว่าเป็นคำถามเช็คชื่อมงคลไหม — จับได้ 2 แบบ: (1) มีคำเฉพาะทาง เช่น
    'ตั้งชื่อ'/'ทักษา' หรือ (2) มีคำว่า 'ชื่อ' คู่กับคำถามท้ายประโยคทั่วไป เช่น
    'ชื่อภูมิดีไหม' ซึ่งเป็นวิธีถามที่เป็นธรรมชาติมากแต่ไม่มีศัพท์เฉพาะเลย"""
    if any(kw in question for kw in NAME_CHECK_KEYWORDS):
        return True
    return "ชื่อ" in question and any(w in question for w in _TRAILING_QUESTION_WORDS)


def extract_name_to_check(question: str) -> str | None:
    """ดึงชื่อที่ผู้ใช้อยากเช็คออกจากประโยคคำถาม เช่น 'ชื่อภูมิดีไหม' -> 'ภูมิ'
    หรือ 'ตั้งชื่อ "กิตติ" ดีไหม' -> 'กิตติ' — ลองจับข้อความในเครื่องหมายคำพูดก่อน
    เพราะแม่นกว่า ถ้าไม่เจอค่อย fallback ไปจับคำหลัง 'ชื่อ' แทน"""
    quoted = _QUOTE_PATTERN.search(question)
    if quoted:
        return quoted.group(1)

    keyword_match = _NAME_KEYWORD_PATTERN.search(question)
    if not keyword_match:
        return None

    candidate = _strip_trailing_noise(keyword_match.group(1))
    return candidate or None


if __name__ == "__main__":
    # ทดสอบเร็วๆ ด้วยตัวอย่างที่รู้คำตอบอยู่แล้ว (คนเกิดวันอังคาร ชื่อ "ภูมิ" กับ "กิตติ")
    tue = date(2000, 1, 4)  # 4 ม.ค. 2000 เป็นวันอังคารจริง (เช็คแล้ว)
    print("วันเกิดตัวอย่าง:", DAY_NAMES_THAI[get_thai_day_index(tue)])
    for test_name in ["ภูมิ", "กิตติ", "ศิริ", "ยศ"]:
        result = check_name_first_letter(test_name, tue)
        cat = result["category"]
        cat_desc = f"{cat['name']} ({cat['meaning']})" if cat else "ไม่พบหมวด (อักษรไม่รู้จัก)"
        flag = " ⚠️ กาลกิณี!" if result["is_kalakin"] else ""
        print(f"{test_name}: อักษร '{result['first_letter']}' → {cat_desc}{flag}")
