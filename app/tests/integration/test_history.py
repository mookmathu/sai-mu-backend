from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import daily_fortune, history, mailer, models
from app.config import settings
from app.database import Base, get_db
from app.main import app


def test_classify():
    assert history.classify("เบอร์ 0812345678 ดีไหม") == "numerology"
    assert history.classify("สีมงคลวันนี้") == "color"
    assert history.classify("วันนี้ดวงเป็นไง") == "daily"
    assert history.classify("ดวงความรักของฉัน") == "zodiac"
    assert history.classify("สวัสดี") == "general"


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
    monkeypatch.setattr(daily_fortune, "today_thai", lambda: date(2026, 10, 8))

    class Env:
        client = TestClient(app)
        outbox = sent
        session = Session

    yield Env
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _signup(env, name="alice", email="a@example.com"):
    env.client.post("/auth/otp/request", json={"email": email, "purpose": "signup"})
    r = env.client.post(
        "/auth/register",
        json={"username": name, "email": email, "password": "password123",
              "otp_code": env.outbox[-1], "birth_day": 2, "birth_month": 10, "birth_year": 1997},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_requires_login(env):
    assert env.client.get("/history").status_code in (401, 403)


def test_daily_fortune_recorded_once_per_day(env):
    h = _signup(env)
    env.client.get("/daily/fortune", headers=h)
    env.client.get("/daily/fortune", headers=h)
    items = env.client.get("/history", headers=h).json()
    assert items["total"] == 1
    e = items["items"][0]
    assert e["kind"] == "daily" and e["category"] == "daily" and "เลขนำโชค" in e["content"]
    assert e["created_at"].endswith("+00:00")  # ใส่ tz ชัดเจน


def test_name_and_number_recorded_only_when_logged_in(env):
    # ไม่ login: ใช้ได้ แต่ไม่บันทึก
    assert env.client.post("/numerology/number", json={"text": "5532"}).status_code == 200
    h = _signup(env)
    assert env.client.get("/history", headers=h).json()["total"] == 0
    env.client.post("/numerology/number", json={"text": "5532"}, headers=h)
    env.client.post("/numerology/number", json={"text": "5532"}, headers=h)  # ซ้ำ -> ไม่เพิ่มแถว
    env.client.post("/numerology/name", json={"first_name": "สมชาย", "last_name": "ใจดี"}, headers=h)
    body = env.client.get("/history?category=numerology", headers=h).json()
    assert body["total"] == 2
    titles = {i["title"] for i in body["items"]}
    assert "เลขศาสตร์เบอร์/ทะเบียน: 5532" in titles and "เลขศาสตร์ชื่อ: สมชาย ใจดี" in titles


def test_invalid_token_on_public_endpoint_still_works(env):
    r = env.client.post("/numerology/number", json={"text": "5532"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 200


def test_save_filter_search_delete_and_isolation(env):
    a = _signup(env)
    b = _signup(env, "bob", "b@example.com")
    env.client.post("/numerology/number", json={"text": "5532"}, headers=a)
    env.client.get("/daily/fortune", headers=a)
    env.client.post("/numerology/number", json={"text": "9999"}, headers=b)

    items = env.client.get("/history", headers=a).json()["items"]
    assert len(items) == 2
    target = next(i for i in items if i["kind"] == "number")

    # คนอื่นแตะรายการของเราไม่ได้
    assert env.client.patch(f"/history/{target['id']}/saved", json={"saved": True}, headers=b).status_code == 404
    assert env.client.delete(f"/history/{target['id']}", headers=b).status_code == 404

    r = env.client.patch(f"/history/{target['id']}/saved", json={"saved": True}, headers=a)
    assert r.status_code == 200 and r.json()["is_saved"] is True
    assert env.client.get("/history?saved=true", headers=a).json()["total"] == 1
    assert env.client.get("/history?q=5532", headers=a).json()["total"] == 1
    assert env.client.get("/history?category=daily", headers=a).json()["total"] == 1
    assert env.client.get("/history?category=bogus", headers=a).status_code == 422

    # ล้างแต่เก็บที่บันทึกไว้
    assert env.client.delete("/history?keep_saved=true", headers=a).status_code == 204
    left = env.client.get("/history", headers=a).json()
    assert left["total"] == 1 and left["items"][0]["is_saved"] is True
    assert env.client.get("/history", headers=b).json()["total"] == 1  # ของ bob ไม่โดน

    assert env.client.delete(f"/history/{target['id']}", headers=a).status_code == 204
    assert env.client.get("/history", headers=a).json()["total"] == 0


def test_sort_and_paging(env):
    h = _signup(env)
    for n in ("1111", "2222", "3333"):
        env.client.post("/numerology/number", json={"text": n}, headers=h)
    new = env.client.get("/history?limit=2", headers=h).json()
    assert new["total"] == 3 and len(new["items"]) == 2
    assert "3333" in new["items"][0]["title"]
    old = env.client.get("/history?sort=old&limit=1", headers=h).json()
    assert "1111" in old["items"][0]["title"]
    assert env.client.get("/history?limit=999", headers=h).status_code == 422


def test_chat_recorded_and_backfill(env):
    h = _signup(env)
    db = env.session()
    uid = db.query(models.User).first().id
    history.record_chat(db, uid, "ดวงความรักของฉัน", "คำตอบ…")
    history.record_chat(db, uid, "เบอร์ 081 ดีไหม", "คำตอบเบอร์", category="numerology")
    db.add_all([
        models.ChatMessage(user_id=uid, role="user", content="สีมงคลวันนี้", created_at=datetime(2026, 10, 1, 3, 0)),
        models.ChatMessage(user_id=uid, role="assistant", content="สีส้ม", created_at=datetime(2026, 10, 1, 3, 1)),
        models.ChatMessage(user_id=uid, role="user", content="ข้อความค้างไม่มีคำตอบ", created_at=datetime(2026, 10, 1, 4, 0)),
    ])
    db.commit()
    assert history.backfill_from_chat(db) == 1
    assert history.backfill_from_chat(db) == 0  # ทำซ้ำไม่เพิ่ม
    db.close()
    cats = {i["title"]: i["category"] for i in env.client.get("/history", headers=h).json()["items"]}
    assert cats["ดวงความรักของฉัน"] == "zodiac" and cats["เบอร์ 081 ดีไหม"] == "numerology"
    assert cats["สีมงคลวันนี้"] == "color" and "ข้อความค้างไม่มีคำตอบ" not in cats


def test_prune_keeps_saved(env, monkeypatch):
    monkeypatch.setattr(history, "MAX_UNSAVED_PER_USER", 2)
    h = _signup(env)
    db = env.session()
    uid = db.query(models.User).first().id
    first = history.record_chat(db, uid, "คำถาม 1", "ตอบ 1")
    first.is_saved = True
    db.commit()
    for i in range(2, 6):
        history.record_chat(db, uid, f"คำถาม {i}", f"ตอบ {i}")
    db.close()
    titles = [i["title"] for i in env.client.get("/history", headers=h).json()["items"]]
    assert "คำถาม 1" in titles and len(titles) == 3  # ที่บันทึกไว้ 1 + ไม่บันทึกล่าสุด 2
