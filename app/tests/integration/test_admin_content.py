"""
ทดสอบ CRUD ของหน้าเว็บแอดมิน (เสื้อสีมงคล / สถานที่สิ่งศักดิ์สิทธิ์):
- ไม่ส่ง/ส่ง X-Admin-Key ผิด ต้องโดนบล็อกด้วย 401 เสมอ
- ส่ง key ถูกต้องแล้วครบวงจร create -> read -> update -> delete ต้องทำงานถูกต้อง

ใช้ sqlite in-memory แยกต่างหาก (ไม่ใช่ sai_mu_dev.db ตัวจริง) ผ่าน dependency
override ของ get_db กันไม่ให้ test เขียนทับข้อมูล dev จริงบนเครื่อง
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app import config, models
from app.database import Base, get_db
from app.main import app

TEST_ADMIN_KEY = "test-admin-key-for-pytest"

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
config.settings.admin_api_key = TEST_ADMIN_KEY

client = TestClient(app)
AUTH_HEADERS = {"X-Admin-Key": TEST_ADMIN_KEY}


def setup_function():
    """ล้างตารางก่อนแต่ละ test กันข้อมูลจาก test อื่นมาปน"""
    db = _TestSessionLocal()
    db.query(models.DailyColorChart).delete()
    db.query(models.SacredPlace).delete()
    db.commit()
    db.close()


def test_admin_endpoints_reject_missing_or_wrong_key():
    assert client.get("/admin/content/daily-colors").status_code == 401
    assert (
        client.get("/admin/content/daily-colors", headers={"X-Admin-Key": "wrong"}).status_code == 401
    )


def test_daily_color_full_crud_cycle():
    create_payload = {
        "year": 2026,
        "month": 1,
        "day_of_month": 1,
        "element_name": "ดิน หยาง",
        "help_colors": "ทอง, สีเงิน",
        "love_colors": "น้ำตาล, ครีม",
        "luck_colors": "ดำ, น้ำเงินเข้ม",
        "problem_colors": "เขียวเข้ม",
        "zodiac_note": None,
        "source_note": "ทดสอบ",
    }
    created = client.post("/admin/content/daily-colors", headers=AUTH_HEADERS, json=create_payload)
    assert created.status_code == 201
    item_id = created.json()["id"]

    listed = client.get("/admin/content/daily-colors", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    update_payload = {**create_payload, "element_name": "ไฟ หยิน", "luck_colors": "แดง"}
    updated = client.put(
        f"/admin/content/daily-colors/{item_id}", headers=AUTH_HEADERS, json=update_payload
    )
    assert updated.status_code == 200
    assert updated.json()["element_name"] == "ไฟ หยิน"
    assert updated.json()["luck_colors"] == "แดง"

    deleted = client.delete(f"/admin/content/daily-colors/{item_id}", headers=AUTH_HEADERS)
    assert deleted.status_code == 204

    listed_after = client.get("/admin/content/daily-colors", headers=AUTH_HEADERS)
    assert listed_after.json() == []


def test_daily_color_update_and_delete_missing_id_returns_404():
    payload = {"year": 2026, "month": 2, "day_of_month": 14, "element_name": "ทอง หยาง"}
    assert client.put("/admin/content/daily-colors/9999", headers=AUTH_HEADERS, json=payload).status_code == 404
    assert client.delete("/admin/content/daily-colors/9999", headers=AUTH_HEADERS).status_code == 404


def test_daily_color_rejects_out_of_range_year_month_or_day():
    bad_year = {"year": 1999, "month": 1, "day_of_month": 1}
    bad_month = {"year": 2026, "month": 13, "day_of_month": 1}
    bad_day = {"year": 2026, "month": 1, "day_of_month": 32}
    assert client.post("/admin/content/daily-colors", headers=AUTH_HEADERS, json=bad_year).status_code == 422
    assert client.post("/admin/content/daily-colors", headers=AUTH_HEADERS, json=bad_month).status_code == 422
    assert client.post("/admin/content/daily-colors", headers=AUTH_HEADERS, json=bad_day).status_code == 422


def test_sacred_place_full_crud_cycle():
    create_payload = {
        "name": "ศาลพระพรหมเอราวัณ",
        "category": "ศาล",
        "district": "ปทุมวัน",
        "highlight": "พระพรหมเอราวัณ",
    }
    created = client.post("/admin/content/sacred-places", headers=AUTH_HEADERS, json=create_payload)
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert created.json()["province"] == "กรุงเทพมหานคร"  # default province ต้องถูกเติมให้อัตโนมัติ

    updated = client.put(
        f"/admin/content/sacred-places/{item_id}",
        headers=AUTH_HEADERS,
        json={**create_payload, "district": "ราชเทวี"},
    )
    assert updated.status_code == 200
    assert updated.json()["district"] == "ราชเทวี"

    deleted = client.delete(f"/admin/content/sacred-places/{item_id}", headers=AUTH_HEADERS)
    assert deleted.status_code == 204

    listed_after = client.get("/admin/content/sacred-places", headers=AUTH_HEADERS)
    assert listed_after.json() == []


def test_admin_static_page_is_served():
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "แผงจัดการเนื้อหา" in response.text
