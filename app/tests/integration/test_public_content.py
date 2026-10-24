"""
ทดสอบ endpoint สาธารณะ (ไม่ต้องใช้ X-Admin-Key) ที่แอป Flutter ฝั่งผู้ใช้จะเรียก:
- GET /content/daily-colors (และกรองด้วย year/month)
- GET /content/daily-colors/today
- GET /content/sacred-places
"""

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app import config, models
from app.database import Base, get_db
from app.main import app

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
Base.metadata.create_all(bind=_engine)


def _override_get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
config.settings.admin_api_key = "test-admin-key-for-pytest"

client = TestClient(app)


def setup_function():
    db = _TestSessionLocal()
    db.query(models.DailyColorChart).delete()
    db.query(models.SacredPlace).delete()
    db.commit()
    db.close()


def _seed_daily_color(**overrides):
    db = _TestSessionLocal()
    row = {
        "year": 2026,
        "month": 1,
        "day_of_month": 1,
        "element_name": "ดิน หยาง",
        "help_colors": "ทอง",
        "love_colors": "น้ำตาล",
        "luck_colors": "ดำ",
        "problem_colors": "เขียวเข้ม",
        "zodiac_note": None,
        "source_note": "ทดสอบ",
    }
    row.update(overrides)
    db.add(models.DailyColorChart(**row))
    db.commit()
    db.close()


def test_public_daily_colors_requires_no_key():
    _seed_daily_color()
    res = client.get("/content/daily-colors")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_public_daily_colors_filters_by_year_and_month():
    _seed_daily_color(month=1, day_of_month=1)
    _seed_daily_color(month=2, day_of_month=1)
    res = client.get("/content/daily-colors", params={"year": 2026, "month": 2})
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["month"] == 2


def test_public_daily_colors_today_returns_404_when_missing():
    res = client.get("/content/daily-colors/today")
    assert res.status_code == 404


def test_public_daily_colors_today_returns_row_when_present():
    today = date.today()
    _seed_daily_color(year=today.year, month=today.month, day_of_month=today.day)
    res = client.get("/content/daily-colors/today")
    assert res.status_code == 200
    assert res.json()["day_of_month"] == today.day


def test_public_sacred_places_requires_no_key():
    db = _TestSessionLocal()
    db.add(models.SacredPlace(name="ศาลพระพรหมเอราวัณ", category="ศาล"))
    db.commit()
    db.close()
    res = client.get("/content/sacred-places")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_public_sacred_place_detail_not_found():
    res = client.get("/content/sacred-places/9999")
    assert res.status_code == 404
