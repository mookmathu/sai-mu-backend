"""ทดสอบ "ทางเดิน" ของคำถามในแชท (chat._dispatch_to_rag) โดยไม่เรียก Gemini/ChromaDB จริง
ใช้ RAG ปลอมที่แค่บันทึกว่าถูกเรียกเมธอดไหน — เช็คว่าคำถามแต่ละแบบเข้าทางที่ควรเข้า
(รันออฟไลน์ได้ ไม่กินโควตา)"""
from datetime import date
from types import SimpleNamespace as NS

import pytest

from app import content_crud, number_luck, numerology, taksa, transit
from app.rag.rag_service import extract_named_zodiac_sign
from app.routers import chat


class FakeRAG:
    def __getattr__(self, name):
        if not name.startswith("ask"):
            raise AttributeError(name)

        def call(*a, **k):
            return {"answer": name, "sources": []}

        return call


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(content_crud, "get_daily_color_chart_by_date", lambda *a, **k: None)


def route(message: str, birth=date(2004, 3, 1)) -> str:
    user = NS(birth_date=birth, birth_time=None)
    zodiac = "มีน"
    named = extract_named_zodiac_sign(message)
    name = taksa.extract_name_to_check(message)
    topic = chat._detect_topic(message)
    digits = None
    if numerology.is_phone_or_plate_question(message):
        digits = numerology.extract_phone_or_plate_query(message)
    number_text = None
    if any(k in message for k in numerology.PHONE_OR_PLATE_KEYWORDS):
        number_text = number_luck.extract_plate(message) or digits
    color = number_luck.extract_car_color(message) if number_text else None
    res = chat._dispatch_to_rag(
        FakeRAG(), NS(message=message), user, zodiac, named, name, topic, digits, None,
        number_text=number_text, car_color=color,
    )
    return res["answer"]


CASES = [
    ("ดวงวันนี้เป็นยังไง", "ask_daily_report"),
    ("ดวงความรักช่วงนี้เป็นไง", "ask_daily_report"),
    ("สีมงคลวันนี้คืออะไร", "ask_daily_color"),
    ("เลขมงคลวันนี้", "ask_daily_lucky_numbers"),
    ("เลขนำโชควันนี้คืออะไร", "ask_daily_lucky_numbers"),
    ("รถสีขาวเหมาะกับฉันไหม", "ask_car_color"),
    ("สีรถอะไรเหมาะกับฉัน", "ask_car_color"),
    ("ทะเบียนรถ ก2547 ดีไหม", "ask_number_luck"),
    ("เบอร์ 0812345678 ดีไหม", "ask_number_luck"),
    ("ทะเบียน ม1510 รถสีเทาดีไหมคะ", "ask_number_luck"),
    ("ราศีตุลย์นิสัยเป็นไง", "ask_zodiac_traits"),
    ("ราศีของฉันนิสัยเป็นยังไง", "ask_zodiac_traits"),
    ("เลขของฉันคืออะไร", "ask_birthdate_numerology"),
    ("บทสวดพระพิฆเนศ", "ask"),
    ("ใส่สีอะไรไปสัมภาษณ์งานดี", "ask_daily_color"),
    ("วัดไหนเหมาะขอพรเรื่องการงาน", "ask"),
    ("เลขมงคลของเบอร์โทร 0812345678", "ask_number_luck"),
    ("ดวงการเงินเดือนนี้เป็นยังไง", "ask_daily_horoscope_topic"),
    ("ดวงของฉันเป็นยังไง", "ask_combined"),
]


@pytest.mark.parametrize("message,expected", CASES)
def test_question_routes_to_expected_branch(message, expected):
    assert route(message) == expected
