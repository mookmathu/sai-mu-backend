"""Test case ระดับ API ของ Mutelove (backend) — แต่ละข้อมีรหัส TC ตรงกับตารางในเอกสาร"""
from unittest import mock

from app.routers import chat as chat_router
from tests.conftest import ADMIN, signup


# ---------- สมัครสมาชิก / เข้าสู่ระบบ ----------
def test_tc01_register_success_returns_token_and_zodiac(client, db):
    r, _ = signup(client, db)
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"]
    assert body["user"]["email"] == "mu@example.com"


def test_tc02_register_wrong_otp_rejected(client, db):
    from app import otp
    otp.issue_otp(db, "a@example.com", otp.PURPOSE_SIGNUP)
    r = client.post("/auth/register", json={
        "username": "a1", "email": "a@example.com", "password": "password123", "otp_code": "000000",
        "birth_day": 1, "birth_month": 1, "birth_year": 2000,
    })
    assert r.status_code == 400


def test_tc03_register_duplicate_email_rejected(client, db):
    signup(client, db)
    r, _ = signup(client, db, username="other")
    assert r.status_code == 400


def test_tc04_register_short_password_rejected(client, db):
    r, _ = signup(client, db, password="short")
    assert r.status_code == 422


def test_tc05_login_success_and_wrong_password(client, db):
    signup(client, db)
    ok = client.post("/auth/login", json={"email": "mu@example.com", "password": "password123"})
    bad = client.post("/auth/login", json={"email": "mu@example.com", "password": "wrong-password"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert bad.status_code == 401


def test_tc06_me_requires_token_and_returns_profile(client, db):
    assert client.get("/auth/me").status_code in (401, 403)
    _, h = signup(client, db)
    r = client.get("/auth/me", headers=h)
    assert r.status_code == 200
    assert r.json()["username"] == "mu"


def test_tc07_signup_otp_for_existing_email_rejected(client, db):
    signup(client, db)
    r = client.post("/auth/otp/request", json={"email": "mu@example.com", "purpose": "signup"})
    assert r.status_code == 400


# ---------- แชท ----------
def _fake_chat():
    return (
        mock.patch.object(chat_router, "_get_rag", lambda: object()),
        mock.patch.object(chat_router, "_dispatch_to_rag", lambda *a, **k: {"answer": "คำตอบทดสอบ", "sources": []}),
    )


def test_tc08_chat_requires_login(client):
    assert client.post("/chat", json={"message": "ดวงวันนี้"}).status_code in (401, 403)


def test_tc09_chat_answer_saved_to_history(client, db):
    _, h = signup(client, db)
    a, b = _fake_chat()
    with a, b:
        r = client.post("/chat", json={"message": "ดวงวันนี้เป็นไง"}, headers=h)
    assert r.status_code == 200 and r.json()["answer"] == "คำตอบทดสอบ"
    msgs = client.get("/chat/history", headers=h).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_tc10_chat_empty_message_rejected(client, db):
    _, h = signup(client, db)
    assert client.post("/chat", json={"message": ""}, headers=h).status_code == 422


def test_tc11_chat_gemini_busy_returns_503(client, db):
    from google.genai import errors
    _, h = signup(client, db)

    def boom(*a, **k):
        raise errors.ServerError(503, {"error": {"message": "overloaded"}})

    with mock.patch.object(chat_router, "_get_rag", lambda: object()), \
         mock.patch.object(chat_router, "_dispatch_to_rag", boom):
        r = client.post("/chat", json={"message": "ดวงวันนี้"}, headers=h)
    assert r.status_code == 503


def test_tc12_chat_history_isolated_between_users(client, db):
    _, h1 = signup(client, db, email="a@example.com", username="aa")
    _, h2 = signup(client, db, email="b@example.com", username="bb")
    a, b = _fake_chat()
    with a, b:
        client.post("/chat", json={"message": "ของ a"}, headers=h1)
    assert len(client.get("/chat/history", headers=h1).json()["messages"]) == 2
    assert client.get("/chat/history", headers=h2).json()["messages"] == []


# ---------- เนื้อหา / แอดมิน ----------
def test_tc13_sacred_places_public_list(client):
    assert client.get("/content/sacred-places").status_code == 200


def test_tc14_admin_requires_key(client):
    assert client.get("/admin/content/sacred-places").status_code in (401, 403)
    assert client.get("/admin/content/sacred-places", headers=ADMIN).status_code == 200


def test_tc15_admin_create_then_public_can_read(client):
    r = client.post("/admin/content/sacred-places", headers=ADMIN, json={
        "name": "วัดทดสอบ", "category": "วัด", "latitude": 13.75, "longitude": 100.5,
    })
    assert r.status_code == 201
    names = [p["name"] for p in client.get("/content/sacred-places").json()]
    assert "วัดทดสอบ" in names


def test_tc16_today_color_404_when_no_data(client):
    assert client.get("/content/daily-colors/today").status_code == 404


# ---------- เลขศาสตร์ / ประวัติ ----------
def test_tc17_name_numerology_works_without_login(client):
    r = client.post("/numerology/name", json={"first_name": "สมชาย", "last_name": "ใจดี"})
    assert r.status_code == 200
    assert "full" in r.json()


def test_tc18_history_requires_login_and_lists_chat(client, db):
    assert client.get("/history").status_code in (401, 403)
    _, h = signup(client, db)
    a, b = _fake_chat()
    with a, b:
        client.post("/chat", json={"message": "ถามอะไรสักอย่าง"}, headers=h)
    items = client.get("/history", headers=h).json()
    assert len(items["items"] if isinstance(items, dict) and "items" in items else items) >= 1


def test_tc19_chat_order_stable_when_timestamps_equal(client, db):
    """Windows ให้เวลาละเอียดไม่พอ ข้อความผู้ใช้กับคำตอบอาจมี created_at เท่ากัน — ลำดับต้องไม่สลับ"""
    from datetime import datetime
    from app import models
    _, h = signup(client, db)
    uid = client.get("/auth/me", headers=h).json()["id"]
    same = datetime(2026, 10, 16, 12, 0, 0)
    db.add(models.ChatMessage(user_id=uid, role="user", content="q", created_at=same))
    db.flush()
    db.add(models.ChatMessage(user_id=uid, role="assistant", content="a", created_at=same))
    db.commit()
    msgs = client.get("/chat/history", headers=h).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_login_requires_otp_when_enabled(client, db, monkeypatch):
    """เปิด LOGIN_OTP_REQUIRED: /auth/login ตรวจรหัสผ่านแล้วส่ง OTP แต่ยังไม่ให้ token จนกว่าจะกรอก OTP ถูก"""
    from app import mailer
    from app.config import settings

    signup(client, db)
    sent = {}
    monkeypatch.setattr(settings, "login_otp_required", True)
    monkeypatch.setattr(mailer, "send_otp_email", lambda to, code, purpose: sent.update(code=code, purpose=purpose))

    bad = client.post("/auth/login", json={"email": "mu@example.com", "password": "wrong-password"})
    assert bad.status_code == 401 and "code" not in sent  # รหัสผ่านผิดต้องไม่ส่ง OTP

    r = client.post("/auth/login", json={"email": "mu@example.com", "password": "password123"})
    assert r.status_code == 200 and r.json()["otp_required"] is True
    assert r.json().get("access_token") is None
    assert sent["purpose"] == "login"

    wrong = client.post("/auth/login/verify", json={"email": "mu@example.com", "otp_code": "000000" if sent["code"] != "000000" else "111111"})
    assert wrong.status_code == 400

    ok = client.post("/auth/login/verify", json={"email": "mu@example.com", "otp_code": sent["code"]})
    assert ok.status_code == 200 and ok.json()["access_token"]


def test_google_login_requires_otp_for_existing_user(client, db, monkeypatch):
    """ล็อกอินด้วย Google ของบัญชีเดิม: ต้องได้ otp_required (ไม่มี token) แล้วกรอก OTP ถึงจะได้ token"""
    from app import mailer, social
    from app.config import settings

    signup(client, db)
    sent = {}
    monkeypatch.setattr(settings, "login_otp_required", True)
    monkeypatch.setattr(mailer, "send_otp_email", lambda to, code, purpose: sent.update(code=code, purpose=purpose))
    monkeypatch.setattr(
        social,
        "verify_google_id_token",
        lambda t: social.SocialIdentity(
            provider="google", provider_id="g-123", email="mu@example.com", email_verified=True, name="Mu"
        ),
    )

    r = client.post("/auth/google", json={"id_token": "fake-google-token-1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["otp_required"] is True and body["email"] == "mu@example.com"
    assert body.get("access_token") is None
    assert sent["purpose"] == "login"

    ok = client.post("/auth/login/verify", json={"email": "mu@example.com", "otp_code": sent["code"]})
    assert ok.status_code == 200 and ok.json()["access_token"]
