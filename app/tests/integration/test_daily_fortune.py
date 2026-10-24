from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import daily_fortune, mailer, models
from app.config import settings
from app.database import Base, get_db
from app.main import app

# ---------- ฟังก์ชันล้วน ----------


def test_digit_root():
    assert [digit_root for digit_root in map(daily_fortune.digit_root, (0, 5, 10, 19, 99))] == [0, 5, 1, 1, 9]


def test_lucky_numbers_deterministic_and_personal():
    today = date(2026, 10, 8)  # พฤหัสบดี → เลขประจำวัน 5
    a = daily_fortune.lucky_numbers(today, date(1997, 10, 2))
    assert a == daily_fortune.lucky_numbers(today, date(1997, 10, 2))
    assert a[0] == 5 and all(1 <= n <= 9 for n in a) and 2 <= len(a) <= 3 and len(set(a)) == len(a)
    # คนละวันเกิด ได้เลขส่วนตัวไม่เหมือนกัน (ตัวอย่างนี้)
    assert a != daily_fortune.lucky_numbers(today, date(2004, 10, 15))


def test_weekday_color_and_numbers_cover_week():
    # จันทร์ 5 ต.ค. 2026 .. อาทิตย์ 11 ต.ค. 2026
    expected = ["เหลือง", "ชมพู", "เขียว", "ส้ม", "ฟ้า", "ม่วง", "แดง"]
    for i, color in enumerate(expected):
        d = date(2026, 10, 5 + i)
        out = daily_fortune.build_daily_fortune(zodiac_sign="กันย์", birth_date=date(1997, 10, 2), today=d)
        assert out["colors"][0]["name"] == color and out["colors"][0]["hex"]
        assert out["numbers"][0] == [2, 3, 4, 5, 6, 7, 1][i]


def test_parse_colors():
    assert daily_fortune.parse_colors("ดำ, น้ำเงินเข้ม**") == ["ดำ", "น้ำเงินเข้ม"]
    assert daily_fortune.parse_colors("ขาว/ทอง") == ["ขาว", "ทอง"]
    assert daily_fortune.parse_colors(None) == [] and daily_fortune.parse_colors("  ") == []


def test_chart_colors_override_weekday_color():
    class Chart:
        luck_colors = "ทอง, ขาว"
        problem_colors = "ดำ**"

    out = daily_fortune.build_daily_fortune(
        zodiac_sign="ตุลย์", birth_date=date(2000, 1, 1), today=date(2026, 10, 8), color_chart=Chart()
    )
    assert [c["name"] for c in out["colors"]] == ["ทอง", "ขาว"]
    assert [c["name"] for c in out["avoid_colors"]] == ["ดำ"]
    assert out["color_note"] == "สีให้โชคลาภประจำวันนี้"


def test_every_house_has_text():
    assert len(daily_fortune.HOUSE_FORTUNE) == 12
    assert all(len(t) == 4 and all(t) for t in daily_fortune.HOUSE_FORTUNE)


def test_house_matches_transit():
    from app import transit

    out = daily_fortune.build_daily_fortune(zodiac_sign="กันย์", birth_date=date(1997, 10, 2), today=date(2026, 10, 8))
    no, name = transit.calculate_transit_house("กันย์", date(2026, 10, 8))
    assert (out["moon_house_no"], out["moon_house_name"]) == (no, name)
    from app import thai_text

    # headline มีตัวอักษรล่องหน (ZWSP) คั่นคำไว้ให้ขึ้นบรรทัดสวย — ตัดออกก่อนเทียบ
    assert thai_text.strip_word_breaks(out["headline"]) == daily_fortune.HOUSE_FORTUNE[no - 1][1]


# ---------- endpoint ----------


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    sent = []
    monkeypatch.setattr(mailer, "send_otp_email", lambda to, code, purpose: sent.append(code))
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 0)

    class Env:
        client = TestClient(app)
        outbox = sent
        session = Session

    yield Env
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _login(env):
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    r = env.client.post(
        "/auth/register",
        json={"username": "alice", "email": "a@example.com", "password": "password123",
              "otp_code": env.outbox[-1], "birth_day": 2, "birth_month": 10, "birth_year": 1997},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_endpoint_returns_fortune(env, monkeypatch):
    monkeypatch.setattr(daily_fortune, "today_thai", lambda: date(2026, 10, 8))
    h = _login(env)
    r = env.client.get("/daily/fortune", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["date"] == "2026-10-08" and body["weekday"] == "พฤหัสบดี" and body["zodiac_sign"] == "กันย์"
    assert body["colors"][0]["name"] == "ส้ม" and body["numbers"][0] == 5 and body["headline"]


def test_endpoint_uses_admin_color_chart_when_present(env, monkeypatch):
    monkeypatch.setattr(daily_fortune, "today_thai", lambda: date(2026, 10, 8))
    h = _login(env)
    db = env.session()
    db.add(models.DailyColorChart(year=2026, month=10, day_of_month=8, luck_colors="เขียว, ทอง", problem_colors="แดง"))
    db.commit()
    db.close()
    body = env.client.get("/daily/fortune", headers=h).json()
    assert [c["name"] for c in body["colors"]] == ["เขียว", "ทอง"] and body["avoid_colors"][0]["name"] == "แดง"


def test_endpoint_requires_login(env):
    assert env.client.get("/daily/fortune").status_code in (401, 403)
