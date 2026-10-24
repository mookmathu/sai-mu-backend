from datetime import date
from types import SimpleNamespace

from app import number_luck
from app.rag.rag_service import NumerologyRAG
from app.routers import chat as chat_router


def test_extract_plate():
    assert number_luck.extract_plate("ทะเบียน 5กก-1555 ดีไหม") == "5กก1555"
    assert number_luck.extract_plate("ทะเบียน กข 123") == "กข123"
    assert number_luck.extract_plate("เบอร์ 0623941583 ดีไหม") is None
    assert number_luck.extract_plate("ผมมีรถ 2 คัน") is None


def test_extract_car_color():
    assert number_luck.extract_car_color("ทะเบียน 5กก-1555 สีรถแดง ดีไหม") == "แดง"
    assert number_luck.extract_car_color("รถสีน้ำเงินเข้มเหมาะไหม") == "น้ำเงินเข้ม"
    assert number_luck.extract_car_color("ทะเบียนนี้ดีไหม") is None


class FakeRag:
    def __init__(self):
        self.calls = []

    def ask_number_luck(self, *a, **k):
        self.calls.append((a, k))
        return {"answer": "ok", "sources": []}

    def ask_daily_horoscope_topic(self, *a, **k):  # ต้องไม่ถูกเรียก
        raise AssertionError("ต้องตอบเรื่องเบอร์ ไม่ใช่ดวงรายวัน")


def test_phone_with_topic_goes_to_number_luck_not_horoscope():
    rag = FakeRag()
    user = SimpleNamespace(birth_date=date(1997, 10, 2))  # พฤหัสบดี → ส้ม
    data = SimpleNamespace(message="เบอร์ 0623941583 เรื่องความรักดีไหม")
    chat_router._dispatch_to_rag(
        rag, data, user, "กันย์", None, None, ("ความรัก", 7), "0623941583", None,
        number_text="0623941583", car_color=None,
    )
    (args, kwargs), = rag.calls
    assert args[1] == "0623941583"
    assert kwargs["topic_keyword"] == "ความรัก"
    assert kwargs["birth_weekday_color"] == "ส้ม" and kwargs["birth_weekday_name"] == "พฤหัสบดี"


class FakeRetriever:
    def get_by_ids(self, ids):
        return [SimpleNamespace(id=i, title=i, text=f"ความหมาย {i}") for i in ids]


class FakeGemini:
    def __init__(self):
        self.question = None

    def answer(self, question, context):
        self.question = question
        return "คำตอบ"


def _rag():
    rag = NumerologyRAG.__new__(NumerologyRAG)
    rag.retriever, rag.gemini = FakeRetriever(), FakeGemini()
    return rag


def test_ask_number_luck_facts_in_prompt():
    rag = _rag()
    r = rag.ask_number_luck(
        "ทะเบียน 5กก-1555 สีรถแดง ดีไหม", "5กก1555", topic_keyword=None,
        car_color="แดง", birth_weekday_color="แดง", birth_weekday_name="อาทิตย์",
    )
    q = rag.gemini.question
    assert "= 23" in q and "ตรงกับสีประจำวันเกิด" in q
    assert any(s["id"] == "godtowa-sum" for s in r["sources"])


def test_ask_number_luck_color_without_birthdate_is_not_judged():
    rag = _rag()
    rag.ask_number_luck("ทะเบียน 1234 สีรถดำ", "1234", car_color="ดำ")
    assert "ประเมินสีรถไม่ได้" in rag.gemini.question
