"""
car_color.py
------------
ตำราสีรถมงคลตามวันเกิด (หลักภูมิทักษา) — ใช้ตอบคำถามสีรถในแชทด้วยข้อมูลจริงจากตาราง
แทนการให้ AI เดา

ที่มา: เรียบเรียงใหม่เป็นข้อมูลของแอปเอง จากบทความ "สีรถถูกโฉลกกับวันเกิด" ของ
MYHORA.com (https://myhora.com/content/?0010) ซึ่งอ้างหลักภูมิทักษาและสวัสดิรักษาคำกลอน
(ข้อเท็จจริงเชิงตำราเท่านั้น ไม่คัดลอกข้อความต้นฉบับ) เป็นความเชื่อทางโหราศาสตร์ไทย
ไม่ใช่ข้อเท็จจริงทางวิทยาศาสตร์

หลักการ: 8 กลุ่มสี เรียงเป็นวงจรเดียวกันเสมอ (แดง→ขาว/เงิน→ชมพู→เขียว→ดำ/ม่วง→ส้ม/ทอง→
เทา→น้ำเงิน) แต่ละวันเกิดเริ่มนับ "ภูมิบริวาร" จากสีของวันตัวเอง แล้วไล่ไปตามวงจร
ภูมิทั้ง 8: บริวาร อายุ เดช ศรี มูลละ อุตสาหะ มนตรี กาลกิณี — ภูมิสุดท้าย (กาลกิณี) คือสีต้องห้าม
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

SOURCE_TITLE = "ตำราสีรถตามวันเกิด (อ้างอิง MYHORA.com)"
SOURCE_URL = "https://myhora.com/content/?0010"

# (รหัส, ชื่อกลุ่มสี, ตัวอย่างสีที่อยู่ในกลุ่ม) เรียงตามวงจร
COLOR_GROUPS: list[tuple[str, str, str]] = [
    ("red", "แดง", "แดงสด แดงกุหลาบ"),
    ("white", "ขาว/เงิน/เหลืองอ่อน", "ขาว เงิน เหลืองอ่อน บรอนซ์เงิน"),
    ("pink", "ชมพู/แดงอ่อน", "ชมพู โอโรส แดงอ่อน"),
    ("green", "เขียว", "เขียวทุกโทน"),
    ("black", "ดำ/ม่วง/น้ำตาลเข้ม", "ดำ ม่วง น้ำตาลเข้ม สีทึบ"),
    ("orange", "ส้ม/แสด/เหลืองเข้ม/ทอง", "ส้ม แสด เหลืองเข้ม ทอง"),
    ("grey", "เทา/ดำสลัว", "เทา ดำสลัว บรอนซ์เข้ม"),
    ("blue", "น้ำเงิน/ฟ้า/คราม", "น้ำเงิน ฟ้า คราม"),
]
_GROUP_IDX = {g[0]: i for i, g in enumerate(COLOR_GROUPS)}

# ชื่อสีที่ผู้ใช้พิมพ์ → กลุ่มสี (สีดำล้วนจัดเข้ากลุ่ม ดำ/ม่วง ตามตำรา)
COLOR_WORD_TO_GROUP: dict[str, str] = {
    "แดง": "red",
    "ขาว": "white", "เงิน": "white", "ครีม": "white", "เหลืองอ่อน": "white",
    "ชมพู": "pink", "ชมพูอ่อน": "pink", "โอโรส": "pink",
    "เขียว": "green", "เขียวเข้ม": "green", "เขียวอ่อน": "green",
    "ดำ": "black", "ม่วง": "black", "น้ำตาล": "black",
    "ส้ม": "orange", "แสด": "orange", "เหลือง": "orange", "ทอง": "orange",
    "เทา": "grey", "บรอนซ์": "grey",
    "น้ำเงิน": "blue", "น้ำเงินเข้ม": "blue", "ฟ้า": "blue", "ฟ้าอ่อน": "blue", "คราม": "blue",
}

# ภูมิทักษา 8 ภูมิ ตามลำดับ พร้อมเรื่องที่ส่งเสริม (เรียบเรียงใหม่)
BHUMI: list[tuple[str, str]] = [
    ("บริวาร", "บารมี มีคนคอยช่วยเหลือ"),
    ("อายุ", "สุขภาพดี อายุยืน"),
    ("เดช", "อำนาจ อิทธิพล คนเกรงใจ"),
    ("ศรี", "ศิริมงคล โชคลาภ"),
    ("มูลละ", "เงินทอง ทรัพย์สมบัติ"),
    ("อุตสาหะ", "ความขยันหมั่นเพียร"),
    ("มนตรี", "มีผู้ใหญ่เมตตาอุปถัมภ์"),
    ("กาลกิณี", "สีต้องห้าม ไม่เป็นมงคล"),
]

# ข้อมูลรายวันเกิด: จุดเริ่มวงจร (สีประจำวันนั้น), เลข/อักษรทะเบียนที่ควรเลี่ยง,
# และสีที่ควรเลี่ยงเป็นพิเศษตาม "อายุย่าง" (รายการอายุ, กลุ่มสี)
# หมายเหตุ: วันเสาร์ ในต้นฉบับพิมพ์ช่วงอายุแรกเป็น 23,32,40,... ซึ่งซ้ำกับช่วงที่สอง
# จึงตีความเป็น 22,31,40,... ตามรูปแบบของวันอื่น (รอบละ 9 ปี)
DAYS: dict[str, dict] = {
    "sun": {
        "label": "วันอาทิตย์", "start": "red",
        "avoid_numbers": [6, 3], "avoid_letters": "ศ ษ ส ห ฬ ฮ",
        "age_avoid": [
            ([23, 32, 41, 50, 59, 68, 77], "pink"),
            ([24, 33, 42, 51, 60, 69], "green"),
            ([18, 27, 36, 45, 54, 63, 72], "grey"),
        ],
    },
    "mon": {
        "label": "วันจันทร์", "start": "white",
        "avoid_numbers": [1, 5], "avoid_letters": "",
        "age_avoid": [
            ([22, 31, 40, 49, 58, 67], "green"),
            ([23, 32, 41, 50, 59, 68], "black"),
            ([26, 35, 44, 53, 62, 71, 80], "blue"),
        ],
    },
    "tue": {
        "label": "วันอังคาร", "start": "pink",
        "avoid_numbers": [2, 1], "avoid_letters": "ก ข ค ฆ ง",
        "age_avoid": [
            ([22, 31, 40, 49, 58, 67], "black"),
            ([23, 32, 41, 50, 59, 68], "orange"),
            ([18, 27, 36, 45, 54, 63, 72], "red"),
        ],
    },
    "wed_day": {
        "label": "วันพุธ (เกิดกลางวัน 06:00-18:00)", "start": "green",
        "avoid_numbers": [3, 8], "avoid_letters": "จ ฉ ช ซ ฌ ญ",
        "age_avoid": [
            ([22, 31, 40, 49, 58, 67], "orange"),
            ([23, 32, 41, 50, 59, 68], "grey"),
            ([18, 27, 36, 45, 54, 63, 72], "white"),
        ],
    },
    "wed_night": {
        "label": "วันพุธ (เกิดกลางคืน/ราหู 18:01-06:00)", "start": "grey",
        "avoid_numbers": [5, 4], "avoid_letters": "บ ป ผ ฝ พ ฟ ภ ม",
        "age_avoid": [
            ([23, 32, 41, 50, 59, 68, 77], "red"),
            ([24, 33, 42, 51, 60, 69], "white"),
            ([22, 31, 40, 49, 58, 67], "black"),
        ],
    },
    "thu": {
        "label": "วันพฤหัสบดี", "start": "orange",
        "avoid_numbers": [7], "avoid_letters": "ด ต ถ ท ธ น",
        "age_avoid": [
            ([22, 31, 40, 49, 58, 67], "blue"),
            ([24, 33, 42, 51, 60, 69, 78], "red"),
            ([18, 27, 36, 45, 54, 63, 72], "green"),
        ],
    },
    "fri": {
        "label": "วันศุกร์", "start": "blue",
        "avoid_numbers": [8, 7], "avoid_letters": "ย ร ล ว",
        "age_avoid": [
            ([23, 32, 41, 50, 59, 68, 77], "white"),
            ([24, 33, 42, 51, 60, 69], "pink"),
            ([18, 27, 36, 45, 54, 63, 72], "orange"),
        ],
    },
    "sat": {
        "label": "วันเสาร์", "start": "black",
        "avoid_numbers": [4, 6], "avoid_letters": "ฎ ฏ ฐ ฑ ฒ ณ",
        "age_avoid": [
            ([22, 31, 40, 49, 58, 67], "grey"),
            ([23, 32, 41, 50, 59, 68, 77], "blue"),
            ([18, 27, 36, 45, 54, 63, 72], "pink"),
        ],
    },
}

_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # date.weekday()


def astro_day_key(birth_date: date, birth_time: time | None = None) -> str:
    """วันเกิดทางโหราศาสตร์ — วันเปลี่ยนตอน 06:00 (เกิดก่อน 06:00 นับเป็นวันก่อนหน้า) และวันพุธแยก
    กลางวัน (06:00-18:00) กับกลางคืน/ราหู (18:01-06:00) ถ้าไม่มีเวลาเกิด ใช้วันตามปฏิทิน
    และถือวันพุธเป็นกลางวัน"""
    d = birth_date
    night = False
    if birth_time is not None:
        if birth_time < time(6, 0):
            d = birth_date - timedelta(days=1)
            night = True
        elif birth_time > time(18, 0):
            night = True
    key = _WEEKDAY_KEYS[d.weekday()]
    if key == "wed":
        return "wed_night" if night else "wed_day"
    return key


def age_yang(birth_date: date, today: date | None = None) -> int:
    """อายุย่าง = อายุเต็มปี + 1 (ปีที่กำลังย่างเข้า) ใช้เทียบช่วงอายุที่ตำราห้ามสีบางสี"""
    today = today or date.today()
    full = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return full + 1


def bhumi_colors(day_key: str) -> list[dict]:
    """ภูมิทั้ง 8 ของวันเกิดนั้น เรียงตามภูมิ พร้อมกลุ่มสีที่ตกในภูมินั้น"""
    start = _GROUP_IDX[DAYS[day_key]["start"]]
    out = []
    for i, (name, meaning) in enumerate(BHUMI):
        g = COLOR_GROUPS[(start + i) % 8]
        out.append({"bhumi": name, "meaning": meaning, "group": g[0], "group_name": g[1], "examples": g[2]})
    return out


def assess_color(day_key: str, color_word: str | None, birth_date: date | None = None) -> dict | None:
    """ประเมินสีรถที่ผู้ใช้ถามกับวันเกิด — None ถ้าไม่รู้จักสีนี้"""
    group = COLOR_WORD_TO_GROUP.get(color_word or "")
    if not group:
        return None
    entry = next(b for b in bhumi_colors(day_key) if b["group"] == group)
    result = {
        "color": color_word,
        "group_name": entry["group_name"],
        "bhumi": entry["bhumi"],
        "meaning": entry["meaning"],
        "forbidden": entry["bhumi"] == "กาลกิณี",
        "age_warning": None,
    }
    if birth_date is not None:
        yang = age_yang(birth_date)
        for ages, g in DAYS[day_key]["age_avoid"]:
            if group == g and yang in ages:
                result["age_warning"] = yang
    return result


def facts_text(day_key: str, color_word: str | None = None, birth_date: date | None = None) -> str:
    """สรุปข้อมูลจริงเป็นข้อความให้ Gemini เรียบเรียง (ห้ามเปลี่ยนข้อมูลในนี้)"""
    day = DAYS[day_key]
    lines = [f"วันเกิดทางโหราศาสตร์ของผู้ใช้: {day['label']}"]
    lines.append("สีรถตามภูมิทักษาของวันเกิดนี้ (เรียงตามภูมิ):")
    for b in bhumi_colors(day_key):
        lines.append(f"- ภูมิ{b['bhumi']} ({b['meaning']}): สี{b['group_name']} [{b['examples']}]")
    nums = " และ ".join(str(n) for n in day["avoid_numbers"])
    plate = f"เลขทะเบียนที่ควรเลี่ยง: {nums}"
    if day["avoid_letters"]:
        plate += f" ตัวอักษรที่ควรเลี่ยง: {day['avoid_letters']}"
    lines.append(plate)
    if birth_date is not None:
        yang = age_yang(birth_date)
        lines.append(
            f"อายุเต็มปีของผู้ใช้ {yang - 1} ปี อายุย่างปัจจุบัน {yang} ปี (อายุย่าง = อายุเต็ม + 1 คือปีที่กำลังย่างเข้า) "
            f"เมื่อพูดถึงอายุให้พูดว่า \"อายุย่าง {yang} ปี\" และบอกสั้นๆ ว่านับจากอายุจริง {yang - 1} ปี ห้ามพูดแค่ \"อายุ {yang} ปี\""
        )
        for ages, g in day["age_avoid"]:
            if yang in ages:
                gname = COLOR_GROUPS[_GROUP_IDX[g]][1]
                lines.append(f"ช่วงอายุย่างนี้ควรเลี่ยงสี{gname} เป็นพิเศษ (นอกเหนือจากสีกาลกิณี)")
    res = assess_color(day_key, color_word, birth_date)
    if color_word and res:
        verdict = "เป็นสีกาลกิณี ต้องห้าม" if res["forbidden"] else f"อยู่ในภูมิ{res['bhumi']} ใช้ได้ ส่งเสริมเรื่อง {res['meaning']}"
        lines.append(f"สีรถที่ผู้ใช้ถาม: {color_word} → กลุ่มสี{res['group_name']} {verdict}")
        if res["age_warning"]:
            lines.append(f"แต่ตอนนี้อายุย่าง {res['age_warning']} ควรเลี่ยงสีกลุ่มนี้เป็นพิเศษ")
    elif color_word:
        lines.append(f"สีรถที่ผู้ใช้ถาม: {color_word} (ไม่อยู่ในตารางกลุ่มสีที่ระบบมี บอกตามตรงว่าประเมินไม่ได้)")
    return "\n".join(lines)
