"""ทดสอบออฟไลน์ (ไม่เรียก Gemini จริง ไม่กินโควตา): การสลับโมเดลสำรอง แคชคำตอบ และตัวจำกัดข้อความต่อวัน"""
from types import SimpleNamespace as NS

import pytest
from google.genai import errors

from app import thai_text, usage_limit
from app.rag import gemini_client as gc
from app.rag.gemini_client import GeminiClient, QuotaExhaustedError
from app.usage_limit import DailyLimitExceeded, UsageGuard

PRIMARY, FALLBACK = "model-primary", "model-fallback"


def api_error(code: int, text: str = "") -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": text, "status": "X"}})


class FakeModels:
    """จำลอง client.models — behaviors: {ชื่อโมเดล: [ผลต่อครั้งที่เรียก (ข้อความ หรือ Exception)]}"""

    def __init__(self, behaviors):
        self.behaviors = {k: list(v) for k, v in behaviors.items()}
        self.calls: list[str] = []
        self.configs: list = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        self.configs.append(config)
        result = self.behaviors[model].pop(0)
        if isinstance(result, Exception):
            raise result
        return NS(text=result)


class _PlainClient(GeminiClient):
    """answer() ที่ตัดตัวอักษรล่องหน (ZWSP) ออก เพื่อให้เทสต์เทียบข้อความตรง ๆ ได้"""

    def answer(self, *a, **k):
        return thai_text.strip_word_breaks(super().answer(*a, **k))


def make_client(monkeypatch, behaviors, **kw) -> tuple[GeminiClient, FakeModels]:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = _PlainClient(**kw)
    fake = FakeModels(behaviors)
    client.client = NS(models=fake)
    return client, fake


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    gc.reset_runtime_state()
    usage_limit.reset_all()
    monkeypatch.setenv("ANSWER_MODELS", f"{PRIMARY},{FALLBACK}")
    monkeypatch.delenv("ANSWER_CACHE", raising=False)
    monkeypatch.setenv("DAILY_CHAT_LIMIT", "3")
    monkeypatch.setattr(gc.time, "sleep", lambda *_: None)
    tokens = [
        gc.conversation_history.set(None),
        gc.usage_guard.set(None),
        gc.cache_lookup_allowed.set(True),
    ]
    yield
    gc.reset_runtime_state()
    usage_limit.reset_all()


# ---------- สลับโมเดลสำรอง ----------

def test_primary_used_when_healthy(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: ["คำตอบหลัก"], FALLBACK: []})
    assert c.answer("q", ["ctx"]) == "คำตอบหลัก"
    assert fake.calls == [PRIMARY] and c.last_model == PRIMARY


def test_per_day_quota_switches_to_fallback_and_primary_is_skipped_afterwards(monkeypatch):
    c, fake = make_client(
        monkeypatch,
        {PRIMARY: [api_error(429, "GenerateRequestsPerDayPerProjectPerModel-FreeTier")], FALLBACK: ["สำรอง1", "สำรอง2"]},
    )
    assert c.answer("q1", ["ctx"]) == "สำรอง1"
    assert fake.calls == [PRIMARY, FALLBACK]
    # ครั้งถัดไปไม่เสียเวลา/โควตาไปลองโมเดลหลักที่หมดแล้วซ้ำ
    assert c.answer("q2", ["ctx"]) == "สำรอง2"
    assert fake.calls == [PRIMARY, FALLBACK, FALLBACK]


def test_per_minute_429_switches_without_sleeping(monkeypatch):
    slept = []
    monkeypatch.setattr(gc.time, "sleep", lambda s: slept.append(s))
    c, fake = make_client(
        monkeypatch,
        {PRIMARY: [api_error(429, "GenerateRequestsPerMinutePerProjectPerModel")], FALLBACK: ["สำรอง"]},
    )
    assert c.answer("q", ["ctx"]) == "สำรอง"
    assert slept == []


def test_503_retries_same_model_first(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: [api_error(503), "หลักหลังลองใหม่"], FALLBACK: []})
    assert c.answer("q", ["ctx"]) == "หลักหลังลองใหม่"
    assert fake.calls == [PRIMARY, PRIMARY]


def test_503_twice_falls_back(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: [api_error(503), api_error(503)], FALLBACK: ["สำรอง"]})
    assert c.answer("q", ["ctx"]) == "สำรอง"


def test_all_models_out_of_daily_quota_raises_quota_error(monkeypatch):
    per_day = "RequestsPerDay"
    c, _ = make_client(monkeypatch, {PRIMARY: [api_error(429, per_day)], FALLBACK: [api_error(429, "PerDay")]})
    with pytest.raises(QuotaExhaustedError):
        c.answer("q", ["ctx"])


def test_non_quota_client_error_is_not_swallowed(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: [api_error(401, "bad key")], FALLBACK: ["x"]})
    with pytest.raises(errors.ClientError):
        c.answer("q", ["ctx"])
    assert fake.calls == [PRIMARY]


def test_model_rejecting_thinking_budget_is_retried_without_it(monkeypatch):
    c, fake = make_client(
        monkeypatch,
        {PRIMARY: [api_error(400, "Thinking budget is not supported for this model"), "ตอบได้"], FALLBACK: []},
    )
    assert c.answer("q", ["ctx"]) == "ตอบได้"
    assert fake.configs[0].thinking_config is not None
    assert fake.configs[1].thinking_config is None


def test_generic_400_invalid_argument_retries_without_thinking_config_once(monkeypatch):
    """เคสจริงจาก gemini-3.5-flash-lite: ตอบ 400 INVALID_ARGUMENT ทั่วไปโดยไม่พูดถึง thinking"""
    generic = "Request contains an invalid argument."
    c, fake = make_client(monkeypatch, {PRIMARY: [api_error(400, generic), "ตอบได้"], FALLBACK: []})
    assert c.answer("q", ["ctx"]) == "ตอบได้"
    assert fake.configs[1].thinking_config is None
    # ครั้งถัดไปไม่ส่ง thinking_config ตั้งแต่แรก
    fake.behaviors[PRIMARY] = ["ตอบอีก"]
    c.answer("q2", ["ctx"])
    assert fake.configs[2].thinking_config is None


def test_persistent_400_after_dropping_thinking_config_is_raised(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: [api_error(400, "x"), api_error(400, "x")], FALLBACK: ["ไม่ควรถึง"]})
    with pytest.raises(errors.ClientError):
        c.answer("q", ["ctx"])
    assert fake.calls == [PRIMARY, PRIMARY]


def test_fixed_model_never_falls_back(monkeypatch):
    """eval ต้องใช้โมเดลตัวเดียวคงที่ — ถ้าโควตาหมดต้อง error ไม่ใช่แอบสลับไปโมเดลอื่น"""
    c, fake = make_client(monkeypatch, {PRIMARY: [api_error(429, "PerDay")], FALLBACK: ["x"]}, model=PRIMARY, use_cache=False)
    with pytest.raises(QuotaExhaustedError):
        c.answer("q", ["ctx"])
    assert fake.calls == [PRIMARY]


def test_output_cleanup_still_applies_to_fallback_model(monkeypatch):
    c, _ = make_client(monkeypatch, {PRIMARY: [api_error(429, "PerDay")], FALLBACK: ["**ดีมาก** เลยค่ะ"]})
    out = c.answer("q", ["ctx"])
    assert "**" not in out and not out.endswith("ค่ะ")


# ---------- แคช ----------

def test_cache_hit_skips_gemini_and_does_not_count_usage(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: ["คำตอบแรก"], FALLBACK: []})
    guard = UsageGuard(user_id=1)
    gc.usage_guard.set(guard)
    assert c.answer("ดวงวันนี้", ["ctx"]) == "คำตอบแรก"
    assert c.answer("ดวงวันนี้", ["ctx"]) == "คำตอบแรก"
    assert fake.calls == [PRIMARY]
    assert c.last_from_cache is True
    assert usage_limit.used_today(1) == 1


def test_cache_shared_between_users_with_identical_input(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: ["ดวงราศีมีน"], FALLBACK: []})
    gc.usage_guard.set(UsageGuard(1))
    c.answer("ดวงราศีมีนวันนี้", ["ctx"])
    gc.usage_guard.set(UsageGuard(2))
    assert c.answer("ดวงราศีมีนวันนี้", ["ctx"]) == "ดวงราศีมีน"
    assert usage_limit.used_today(2) == 0


def test_different_question_or_context_is_not_a_cache_hit(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: ["ก", "ข", "ค"], FALLBACK: []})
    assert c.answer("q1", ["ctx"]) == "ก"
    assert c.answer("q2", ["ctx"]) == "ข"
    assert c.answer("q1", ["ctx อื่น"]) == "ค"


def test_answer_generated_with_history_is_never_cached(monkeypatch):
    """กันเนื้อหาจากบทสนทนาของคนแรกหลุดไปให้คนอื่นผ่านแคช"""
    c, fake = make_client(monkeypatch, {PRIMARY: ["ตอบพร้อมประวัติ", "ตอบใหม่"], FALLBACK: []})
    gc.conversation_history.set([("ทะเบียน ก2547", "ตอบเรื่องทะเบียน")])
    c.answer("ดวงวันนี้", ["ctx"])
    gc.conversation_history.set(None)
    assert c.answer("ดวงวันนี้", ["ctx"]) == "ตอบใหม่"


def test_follow_up_does_not_read_cache(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: ["สะอาด", "ต่อเนื่อง"], FALLBACK: []})
    c.answer("แล้วสีล่ะ", ["ctx"])  # ไม่มีประวัติ → เก็บลงแคช
    gc.cache_lookup_allowed.set(False)
    assert c.answer("แล้วสีล่ะ", ["ctx"]) == "ต่อเนื่อง"


def test_cache_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("ANSWER_CACHE", "0")
    c, fake = make_client(monkeypatch, {PRIMARY: ["1", "2"], FALLBACK: []})
    assert c.answer("q", ["ctx"]) == "1"
    assert c.answer("q", ["ctx"]) == "2"


def test_cache_expires_and_evicts():
    cache = gc.AnswerCache(max_entries=2, ttl_seconds=100)
    cache.set("a", "1"); cache.set("b", "2"); cache.set("c", "3")
    assert cache.get("a") is None and cache.get("b") == "2" and cache.get("c") == "3"
    short = gc.AnswerCache(ttl_seconds=-1)
    short.set("x", "y")
    assert short.get("x") is None


# ---------- ตัวจำกัดข้อความต่อวัน ----------

def test_daily_limit_blocks_after_limit_and_counts_per_user(monkeypatch):
    c, fake = make_client(monkeypatch, {PRIMARY: ["1", "2", "3", "4"], FALLBACK: []})
    guard = UsageGuard(7)
    gc.usage_guard.set(guard)
    for i in range(3):
        c.answer(f"q{i}", ["ctx"])
    assert guard.exhausted()
    with pytest.raises(DailyLimitExceeded):
        c.answer("q-new", ["ctx"])
    # ผู้ใช้อื่นไม่โดนผลกระทบ
    gc.usage_guard.set(UsageGuard(8))
    assert c.answer("q-new", ["ctx"]) == "4"


def test_cached_answer_is_still_served_when_not_exhausted_check_is_done_by_router(monkeypatch):
    """ตัวจำกัดนับเฉพาะครั้งที่เรียก Gemini จริง: ถามซ้ำจากแคชกี่ครั้งก็ไม่เพิ่มตัวนับ"""
    c, _ = make_client(monkeypatch, {PRIMARY: ["x"], FALLBACK: []})
    gc.usage_guard.set(UsageGuard(5))
    for _ in range(10):
        c.answer("same", ["ctx"])
    assert usage_limit.used_today(5) == 1


def test_failed_gemini_call_does_not_consume_quota(monkeypatch):
    c, _ = make_client(monkeypatch, {PRIMARY: [api_error(429, "PerDay")], FALLBACK: [api_error(503), api_error(503)]})
    gc.usage_guard.set(UsageGuard(9))
    with pytest.raises(Exception):
        c.answer("q", ["ctx"])
    assert usage_limit.used_today(9) == 0


def test_limit_zero_means_unlimited(monkeypatch):
    monkeypatch.setenv("DAILY_CHAT_LIMIT", "0")
    assert usage_limit.remaining_today(1) is None
    assert not UsageGuard(1).exhausted()


def test_low_remaining_notice(monkeypatch):
    monkeypatch.setenv("DAILY_CHAT_LIMIT", "7")
    g = UsageGuard(3)
    assert g.low_remaining_notice() is None  # ยังไม่ได้ใช้ Gemini ใน request นี้ → ไม่เตือน
    g.after(); g.after()  # ใช้ไป 2 เหลือ 5
    assert "5" in g.low_remaining_notice()
    for _ in range(5):  # ใช้ครบ 7 → เหลือ 0
        g.after()
    assert "สุดท้าย" in g.low_remaining_notice()
    g2 = UsageGuard(4)
    g2.after()  # ใช้ 1 เหลือ 6 → ยังไม่เตือน
    assert g2.low_remaining_notice() is None


def test_messages_have_no_forbidden_particles():
    """ข้อความที่แอปแสดงเอง ใช้โทนเดียวกับคำตอบ AI (ไม่มีคำลงท้ายเพศ/นะ)"""
    from app.rag.gemini_client import strip_particles

    assert strip_particles(usage_limit.LIMIT_REACHED_MESSAGE) == usage_limit.LIMIT_REACHED_MESSAGE


# ---------- ต่อกับ endpoint /chat จริง (จำลอง RAG/DB) ----------

def test_chat_endpoint_enforces_daily_limit_and_adds_notice(monkeypatch):
    from datetime import date

    from fastapi import BackgroundTasks

    from app import crud
    from app.routers import chat as chat_router
    from app.schemas import ChatRequest

    monkeypatch.setenv("DAILY_CHAT_LIMIT", "2")
    monkeypatch.setattr(chat_router, "_get_rag", lambda: object())
    monkeypatch.setattr(crud, "get_recent_exchanges", lambda *a, **k: [])
    dispatched = []

    def fake_dispatch(*a, **k):
        dispatched.append(1)
        gc.usage_guard.get().after()  # จำลองว่าเรียก Gemini จริง 1 ครั้ง
        return {"answer": "คำตอบจาก AI", "sources": []}

    monkeypatch.setattr(chat_router, "_dispatch_to_rag", fake_dispatch)
    user = NS(id=42, birth_date=date(2004, 3, 1), birth_time=None, astro_profile=NS(zodiac_sign="มีน"))

    def ask(msg):
        return chat_router.chat(ChatRequest(message=msg), BackgroundTasks(), user, None)

    r1 = ask("ดวงวันนี้เป็นยังไง")
    assert r1.answer.startswith("คำตอบจาก AI") and "เหลือโควตา" in r1.answer  # เหลือ 1 → เตือนล่วงหน้า
    r2 = ask("ดวงความรักล่ะ")
    assert "สุดท้าย" in r2.answer
    r3 = ask("ถามอีกข้อ")
    assert r3.answer == usage_limit.LIMIT_REACHED_MESSAGE
    assert len(dispatched) == 2  # ข้อที่ 3 ไม่ถูกส่งไปค้น/เรียก Gemini เลย


def test_chat_endpoint_converts_limit_raised_inside_rag_to_friendly_answer(monkeypatch):
    from datetime import date

    from fastapi import BackgroundTasks

    from app import crud
    from app.routers import chat as chat_router
    from app.schemas import ChatRequest

    monkeypatch.setattr(chat_router, "_get_rag", lambda: object())
    monkeypatch.setattr(crud, "get_recent_exchanges", lambda *a, **k: [])
    monkeypatch.setattr(chat_router, "_dispatch_to_rag", lambda *a, **k: (_ for _ in ()).throw(DailyLimitExceeded()))
    user = NS(id=43, birth_date=date(2004, 3, 1), birth_time=None, astro_profile=NS(zodiac_sign="มีน"))
    r = chat_router.chat(ChatRequest(message="สวัสดี"), BackgroundTasks(), user, None)
    assert r.answer == usage_limit.LIMIT_REACHED_MESSAGE
