# -*- coding: utf-8 -*-
"""
daily_fortune.py
----------------
ดวงประจำวันแบบสั้นสำหรับการ์ดหน้า Home: คำทำนายคร่าว ๆ + สีแนะนำ + เลขประจำวัน
ไม่เรียก LLM (เร็วและฟรี) — ทุกอย่างคำนวณจากกฎที่ตรวจสอบย้อนได้

1) ดวงคร่าว ๆ  : ใช้ตำแหน่งดวงจันทร์วันนี้เทียบกับราศีอาทิตย์กำเนิดของผู้ใช้ → ได้ "ภพ" ที่
   จันทร์ผ่าน (transit.calculate_transit_house) แล้วเลือกข้อความสั้นของภพนั้นจากตารางด้านล่าง
   (เขียนเป็นแนวโน้ม ไม่ฟันธง ความหมายภพตรงกับ chunk house-1..12 ใน RAG)
2) สีแนะนำ     : ถ้าแอดมินกรอกตารางสีมงคลของวันนี้ไว้ (daily_color_charts) ใช้ "สีให้โชคลาภ"
   ของวันนั้น ไม่งั้นใช้ "สีประจำวัน" ตามวันในสัปดาห์แบบไทย (อาทิตย์=แดง จันทร์=เหลือง ...)
3) เลขประจำวัน : กฎง่าย ๆ ที่กำหนดเอง (ไม่ได้อ้างตำราใด — ปรับได้ที่ฟังก์ชัน lucky_numbers):
     เลขประจำวัน = ลำดับวันในสัปดาห์ (อา=1 จ=2 ... ส=7)
     เลขวันที่    = ผลรวมหลักของ วัน+เดือน+ปี ของวันนี้ ย่อเหลือหลักเดียว
     เลขส่วนตัว   = ผลรวมหลักของวันเกิดผู้ใช้ + เลขวันที่ ย่อเหลือหลักเดียว
   วันเดียวกันได้เลขเหมือนเดิมทุกครั้งที่เปิดแอป แต่แต่ละคนได้ไม่เหมือนกัน
"""
from datetime import date, datetime, timedelta, timezone

from . import thai_text, transit

# เวลาไทยคงที่ UTC+7 (ไม่ใช้ zoneinfo เพราะ Windows ต้องติดตั้ง tzdata เพิ่ม)
THAI_TZ = timezone(timedelta(hours=7))


def today_thai() -> date:
    return datetime.now(THAI_TZ).date()


WEEKDAY_NAMES = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]  # date.weekday()
WEEKDAY_NUMBER = [2, 3, 4, 5, 6, 7, 1]  # อา=1 จ=2 ... ส=7 (เรียงตาม date.weekday())

# สีประจำวันแบบไทย เรียงตาม date.weekday() (จันทร์=0)
WEEKDAY_COLORS = ["เหลือง", "ชมพู", "เขียว", "ส้ม", "ฟ้า", "ม่วง", "แดง"]

COLOR_HEX: dict[str, str] = {
    "แดง": "#E53935", "ชมพู": "#F48FB1", "ส้ม": "#FB8C00", "เหลือง": "#FDD835",
    "เขียว": "#43A047", "ฟ้า": "#4FC3F7", "น้ำเงิน": "#1E3A8A", "น้ำเงินเข้ม": "#1E3A8A",
    "ม่วง": "#8E24AA", "ขาว": "#FFFFFF", "ดำ": "#212121", "เทา": "#9E9E9E",
    "น้ำตาล": "#795548", "ทอง": "#D4AF37", "เงิน": "#C0C0C0", "ครีม": "#FFF1C1",
    "เขียวอ่อน": "#A5D6A7", "เขียวเข้ม": "#2E7D32", "ฟ้าอ่อน": "#B3E5FC", "ชมพูอ่อน": "#F8BBD0",
}

# ข้อความสั้นรายภพ — (หัวข้อที่เด่นวันนี้, หัวเรื่อง, สรุป, คำแนะนำ) เขียนเป็นแนวโน้ม
HOUSE_FORTUNE: list[tuple[str, str, str, str]] = [
    ("ตัวเองและสุขภาพ", "วันนี้เป็นวันของตัวคุณเอง",
     "คนรอบข้างจะสังเกตเห็นคุณมากกว่าปกติ ลองใส่ใจเรื่องสุขภาพและการแต่งตัว วันนี้เหมาะกับการเริ่มอะไรใหม่ๆ",
     "ลองเริ่มสิ่งที่คิดไว้นานแล้ว และดูแลร่างกายให้พักผ่อนพอ"),
    ("การเงิน", "วันนี้เรื่องเงินต้องคิดดีๆ",
     "จะได้คิดเรื่องรายรับรายจ่ายเยอะหน่อย อาจเจอช่องทางหาเงินเพิ่ม แต่ก็ใช้จ่ายง่ายเหมือนกัน",
     "ก่อนซื้อของชิ้นใหญ่ ให้รอข้ามคืนก่อนค่อยตัดสินใจ"),
    ("การสื่อสารและการเดินทาง", "วันนี้เหมาะกับการคุยและออกไปข้างนอก",
     "การติดต่อคนอื่นจะราบรื่น ทั้งเพื่อนสนิท พี่น้อง และงานใกล้ตัว ไปไหนใกล้ๆ ก็สะดวก",
     "ตอบข้อความที่ค้างอยู่ หรือชวนคนที่คิดถึงไปเจอกัน"),
    ("ครอบครัวและบ้าน", "วันนี้อยากอยู่บ้านกับคนที่ไว้ใจ",
     "วันนี้จะใส่ใจเรื่องที่บ้านและคนในครอบครัวมากเป็นพิเศษ รู้สึกอยากอยู่ในที่ที่สบายใจ",
     "ใช้เวลากับคนที่บ้าน หรือจัดห้องจัดของให้เป็นระเบียบ"),
    ("ความคิดสร้างสรรค์และความรักใหม่", "วันนี้ความคิดดีและอารมณ์สดใส",
     "จะรู้สึกอยากทำสิ่งที่ชอบ ความคิดใหม่ ๆ เข้ามาง่าย คนที่กำลังคุยกันอยู่ก็มีโอกาสสนิทกันขึ้น",
     "ลองทำงานอดิเรกหรือสิ่งที่อยากลอง ให้เวลากับความสุขของตัวเอง"),
    ("หน้าที่และอุปสรรค", "วันนี้มีงานเล็กงานน้อยให้จัดการเยอะ",
     "อาจมีงานและเรื่องจุกจิกเข้ามาพร้อมกันจนเหนื่อย ร่างกายก็อาจล้าง่ายกว่าปกติ",
     "ทำทีละอย่าง เลี่ยงการเถียงกับคนอื่น และพักให้พอ"),
    ("คู่ครองและความสัมพันธ์", "วันนี้เรื่องคนสำคัญและคนข้างๆ เด่น",
     "เหมาะกับการคุยจริงจังกับแฟน คู่ค้า หรือคนที่ทำงานด้วยกัน การเจรจาวันนี้มีโอกาสสำเร็จ",
     "ฟังอีกฝ่ายให้จบก่อน แล้วพูดด้วยน้ำเสียงนุ่มนวล"),
    ("การเปลี่ยนแปลง", "วันนี้อาจมีเรื่องไม่คาดคิดเข้ามา",
     "อาจมีเรื่องที่คุณควบคุมไม่ได้ หรือต้องปรับแผนกะทันหัน อารมณ์อาจแกว่งง่ายกว่าปกติ",
     "ใจเย็นไว้ก่อน อย่าเพิ่งเซ็นสัญญาหรือตกลงอะไรเร็วเกินไป"),
    ("โชคลาภและบารมี", "วันนี้โชคดีและมีคนช่วย",
     "มีแนวโน้มได้รับโชคหรือคำแนะนำดีๆ จากผู้ใหญ่ การเรียนและการเดินทางไกลก็ราบรื่น",
     "ลองขอคำปรึกษาจากคนที่เก่งกว่า ไปทำบุญ หรือวางแผนระยะยาว"),
    ("การงาน", "วันนี้งานของคุณเป็นที่สังเกต",
     "คนที่ทำงานจะเห็นความตั้งใจของคุณ มีโอกาสได้รับความไว้ใจหรืองานสำคัญเพิ่ม",
     "ตั้งใจกับงานที่สำคัญที่สุด และตรงต่อเวลา"),
    ("เพื่อนและผลตอบแทน", "วันนี้มีเพื่อนและคนรอบตัวช่วยเหลือ",
     "เพื่อนและคนรู้จักจะเป็นกำลังใจ สิ่งที่ตั้งใจทำมาก่อนหน้านี้มีโอกาสเห็นผล",
     "ทักหาเพื่อนที่ไม่ได้คุยกันนานๆ หรือไปร่วมกิจกรรมกลุ่ม"),
    ("การพักผ่อนและเรื่องส่วนตัว", "วันนี้เหมาะกับการพักและอยู่กับตัวเอง",
     "พลังงานอาจน้อยกว่าปกติ และอาจมีค่าใช้จ่ายเล็กๆ โผล่มาโดยไม่ทันตั้งตัว",
     "ลดงานลง นอนให้เต็มที่ และระวังเรื่องใช้จ่ายจุกจิก"),
]


def moon_stay_info(zodiac_sign: str, today: date) -> dict:
    """ดวงจันทร์อยู่ภพเดิมนานประมาณ 2-3 วัน — คืนว่าวันนี้เป็นวันที่เท่าไรของช่วงนั้น
    (day_index จาก total_days) และวันที่ภพจะเปลี่ยน (next_change) ไว้บอกผู้ใช้ตรงๆ
    ว่าทำไมดวงช่วงนี้คล้ายเมื่อวาน"""
    house_no, _ = transit.calculate_transit_house(zodiac_sign, today)
    start = today
    while (today - start).days < 4 and transit.calculate_transit_house(
        zodiac_sign, start - timedelta(days=1)
    )[0] == house_no:
        start -= timedelta(days=1)
    end = today
    while (end - today).days < 4 and transit.calculate_transit_house(
        zodiac_sign, end + timedelta(days=1)
    )[0] == house_no:
        end += timedelta(days=1)
    return {
        "day_index": (today - start).days + 1,
        "total_days": (end - start).days + 1,
        "last_day": end,
        "next_change": end + timedelta(days=1),
    }


def digit_root(n: int) -> int:
    """ผลรวมหลักซ้ำจนเหลือหลักเดียว (1-9) เช่น 19 → 10 → 1; 0 → 0"""
    n = abs(n)
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n


def _digit_sum(d: date) -> int:
    return sum(int(c) for c in f"{d.day}{d.month}{d.year}")


def lucky_numbers(today: date, birth: date) -> list[int]:
    weekday_no = WEEKDAY_NUMBER[today.weekday()]
    date_no = digit_root(_digit_sum(today))
    personal_no = digit_root(_digit_sum(birth) + _digit_sum(today))
    numbers: list[int] = []
    for n in (weekday_no, date_no, personal_no):
        if n and n not in numbers:
            numbers.append(n)
    if len(numbers) < 2:  # กรณีซ้ำกันหมด เติมเลขรวมเพื่อให้มีอย่างน้อย 2 ตัว
        extra = digit_root(weekday_no + date_no) or 9
        if extra not in numbers:
            numbers.append(extra)
    return numbers


def parse_colors(text: str | None) -> list[str]:
    """แยกชื่อสีจากข้อความอิสระของตารางสีมงคล เช่น "ดำ, น้ำเงินเข้ม**" → ["ดำ","น้ำเงินเข้ม"]"""
    if not text:
        return []
    cleaned = text.replace("*", " ").replace("และ", ",").replace("/", ",").replace("\n", ",")
    result: list[str] = []
    for part in cleaned.split(","):
        name = part.strip()
        if name and name not in result:
            result.append(name)
    return result


def _color(name: str) -> dict:
    return {"name": name, "hex": COLOR_HEX.get(name)}


def build_daily_fortune(*, zodiac_sign: str, birth_date: date, today: date, color_chart=None, birth_time=None) -> dict:
    """คืน dict ตรงกับ DailyFortuneOut (schemas ใน routers/daily.py)
    color_chart = แถว DailyColorChart ของวันนี้ (หรือ None ถ้ายังไม่มีข้อมูล)"""
    house_no, house_name = transit.calculate_transit_house(zodiac_sign, today)
    focus, headline, summary, tip = HOUSE_FORTUNE[house_no - 1]

    chart_colors = parse_colors(getattr(color_chart, "luck_colors", None)) if color_chart else []
    if chart_colors:
        colors = [_color(c) for c in chart_colors[:3]]
        color_note = "สีให้โชคลาภประจำวันนี้"
        avoid = [_color(c) for c in parse_colors(getattr(color_chart, "problem_colors", None))[:3]]
    else:
        colors = [_color(WEEKDAY_COLORS[today.weekday()])]
        color_note = f"สีประจำวัน{WEEKDAY_NAMES[today.weekday()]}"
        avoid = []

    result = {
        "date": today.isoformat(),
        "weekday": WEEKDAY_NAMES[today.weekday()],
        "zodiac_sign": zodiac_sign,
        "moon_house_no": house_no,
        "moon_house_name": house_name,
        "focus": focus,
        "headline": headline,
        "summary": summary,
        "tip": tip,
        "colors": colors,
        "color_note": color_note,
        "avoid_colors": avoid,
        "numbers": lucky_numbers(today, birth_date),
    }
    # ดวงหลายหมวด (ภาพรวม/งาน/เงิน/รัก/สุขภาพ/โชค/เรียน/ครอบครัว/เดินทาง) — ถ้าคำนวณพลาด
    # ยังคืนการ์ดแบบเดิมได้ตามปกติ
    try:
        from . import daily_engine

        report = daily_engine.build_daily_report(
            zodiac_sign=zodiac_sign, birth_date=birth_date, today=today, birth_time=birth_time
        )
        result["categories"] = report["categories"]
        result["factors"] = report["factors"]
        result["birth_time_known"] = report["birth_time_known"]
        result["lunar_phase"] = report["lunar_phase"]
        result["best_key"] = report["best_key"]
        result["caution_key"] = report["caution_key"]
    except Exception:  # noqa: BLE001
        pass
    # จัดภาษาไทย: ไม้ยมกเว้นวรรค + แทรกจุดตัดคำให้ขึ้นบรรทัดใหม่ไม่ตัดกลางคำ
    for key in ("focus", "headline", "summary", "tip"):
        result[key] = thai_text.polish(result[key])
    return result
