"""PATCH /auth/me และ POST/DELETE /auth/me/avatar"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import avatars, mailer, models
from app.config import settings
from app.database import Base, get_db
from app.main import app

BIRTH = {"birth_day": 15, "birth_month": 6, "birth_year": 2000}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture()
def env(monkeypatch, tmp_path):
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
    monkeypatch.setattr(avatars, "AVATAR_DIR", tmp_path / "avatars")

    class Env:
        client = TestClient(app)
        outbox = sent
        session = Session
        dir = tmp_path / "avatars"

    yield Env
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _signup(env, email="a@example.com", username="alice"):
    env.client.post("/auth/otp/request", json={"email": email, "purpose": "signup"})
    r = env.client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": "password123", "otp_code": env.outbox[-1], **BIRTH},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_patch_changes_fields_and_recomputes_zodiac(env):
    h = _signup(env)
    r = env.client.patch(
        "/auth/me", headers=h,
        json={"username": "alice2", "birth_day": 2, "birth_month": 10, "birth_year": 1997,
              "birth_hour": 4, "birth_minute": 10},
    )
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["username"] == "alice2" and u["birth_date"] == "1997-10-02" and u["birth_time"].startswith("04:10")
    assert u["astro_profile"]["zodiac_sign"] == "กันย์" and u["astro_profile"]["zodiac_animal"] == "ฉลู"
    assert env.client.get("/auth/me", headers=h).json()["username"] == "alice2"


def test_patch_without_time_clears_birth_time(env):
    h = _signup(env)
    env.client.patch("/auth/me", headers=h, json={"username": "alice", **BIRTH, "birth_hour": 8, "birth_minute": 0})
    r = env.client.patch("/auth/me", headers=h, json={"username": "alice", **BIRTH})
    assert r.status_code == 200 and r.json()["birth_time"] is None


def test_patch_duplicate_username_rejected_but_own_name_ok(env):
    h = _signup(env, "a@example.com", "alice")
    _signup(env, "b@example.com", "bob")
    assert env.client.patch("/auth/me", headers=h, json={"username": "bob", **BIRTH}).status_code == 400
    assert env.client.patch("/auth/me", headers=h, json={"username": "alice", **BIRTH}).status_code == 200


def test_patch_validation_and_auth(env):
    h = _signup(env)
    bad_date = {"username": "alice", "birth_day": 31, "birth_month": 2, "birth_year": 2000}
    assert env.client.patch("/auth/me", headers=h, json=bad_date).status_code == 422
    half_time = {"username": "alice", **BIRTH, "birth_hour": 5}
    assert env.client.patch("/auth/me", headers=h, json=half_time).status_code == 422
    assert env.client.patch("/auth/me", json={"username": "alice", **BIRTH}).status_code in (401, 403)


def test_avatar_upload_replace_and_delete(env):
    h = _signup(env)
    r = env.client.post("/auth/me/avatar", headers=h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    url1 = r.json()["avatar_url"]
    assert url1.startswith("/uploads/avatars/") and url1.endswith(".png")
    first = env.dir / url1.rsplit("/", 1)[1]
    assert first.read_bytes() == PNG

    import time as _t
    _t.sleep(1.05)  # ชื่อไฟล์มีวินาทีต่อท้าย
    r = env.client.post("/auth/me/avatar", headers=h, files={"file": ("b.jpg", JPG, "image/jpeg")})
    url2 = r.json()["avatar_url"]
    assert url2 != url1 and url2.endswith(".jpg")
    assert not first.exists()  # รูปเก่าถูกลบ
    assert env.client.get("/auth/me", headers=h).json()["avatar_url"] == url2

    r = env.client.delete("/auth/me/avatar", headers=h)
    assert r.status_code == 200 and r.json()["avatar_url"] is None
    assert list(env.dir.glob("*")) == []


def test_avatar_rejects_non_image_and_too_big(env, monkeypatch):
    h = _signup(env)
    r = env.client.post("/auth/me/avatar", headers=h, files={"file": ("x.png", b"<?php echo 1; ?>", "image/png")})
    assert r.status_code == 400  # นามสกุล/Content-Type หลอกได้ แต่ magic bytes ไม่ใช่รูป
    monkeypatch.setattr(avatars, "MAX_AVATAR_BYTES", 32)
    r = env.client.post("/auth/me/avatar", headers=h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 413
    db = env.session()
    assert db.query(models.User).one().avatar_path is None
    db.close()


def test_avatar_requires_login(env):
    r = env.client.post("/auth/me/avatar", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code in (401, 403)


def test_delete_account_requires_password_and_removes_everything(env):
    h = _signup(env)
    env.client.post("/auth/me/avatar", headers=h, files={"file": ("a.png", PNG, "image/png")})
    files = list(env.dir.iterdir())
    assert len(files) == 1
    # รหัสผ่านผิด / ไม่ส่ง → ไม่ลบ
    assert env.client.request("DELETE", "/auth/me", headers=h, json={"password": "wrong-pass"}).status_code == 400
    assert env.client.request("DELETE", "/auth/me", headers=h).status_code == 400
    assert env.client.get("/auth/me", headers=h).status_code == 200
    # รหัสผ่านถูก → ลบ
    r = env.client.request("DELETE", "/auth/me", headers=h, json={"password": "password123"})
    assert r.status_code == 200, r.text
    assert env.client.get("/auth/me", headers=h).status_code in (401, 403, 404)
    assert list(env.dir.iterdir()) == []
    db = env.session()
    try:
        assert db.query(models.User).count() == 0
        assert db.query(models.UserAstroProfile).count() == 0
        assert db.query(models.HistoryEntry).count() == 0
    finally:
        db.close()
    # สมัครใหม่ด้วยอีเมลเดิมได้
    _signup(env)


def test_delete_account_social_only_needs_email_confirmation(env):
    h = _signup(env)
    db = env.session()
    try:
        u = db.query(models.User).first()
        u.password_hash = None
        db.commit()
    finally:
        db.close()
    assert env.client.request("DELETE", "/auth/me", headers=h, json={"confirm_email": "other@example.com"}).status_code == 400
    r = env.client.request("DELETE", "/auth/me", headers=h, json={"confirm_email": "A@Example.com"})
    assert r.status_code == 200, r.text


def test_delete_account_requires_login(env):
    assert env.client.request("DELETE", "/auth/me").status_code in (401, 403)
