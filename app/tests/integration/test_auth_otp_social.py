"""
ทดสอบ flow ใหม่ของ auth:
- OTP ทางอีเมล: สมัครสมาชิก (signup) และตั้งรหัสผ่านใหม่ (reset)
- Google / Facebook login (mock การตรวจ token กับ provider — ไม่มีเครือข่ายจริง)
- ผู้ใช้ social ใหม่ต้องกรอกวันเกิดผ่าน /auth/social/complete

ใช้ fixture ตั้ง/คืน dependency_overrides ต่อเทสต์ (ไม่ตั้งระดับโมดูลเหมือนไฟล์อื่น)
เพื่อไม่ชนกับไฟล์เทสต์อื่นที่ override get_db บน app ตัวเดียวกัน
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import mailer, models, social
from app.config import settings
from app.database import Base, get_db
from app.main import app

BIRTH = {"birth_day": 15, "birth_month": 6, "birth_year": 2000}


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)  # ไฟล์เทสต์อื่นตั้งไว้ตอน import — ต้องคืนค่าเดิมหลังจบ
    app.dependency_overrides[get_db] = override

    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mailer, "send_otp_email", lambda to, code, purpose: sent.append((to, code, purpose)))
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 0)
    # เทสต์ชุดนี้ตรวจ flow เดิม (ล็อกอินได้ token ตรง ๆ) — เทสต์ OTP ตอนล็อกอินอยู่ใน tests/test_api.py
    monkeypatch.setattr(settings, "login_otp_required", False)

    class Env:
        client = TestClient(app)
        outbox = sent
        session = Session

    yield Env
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _signup(env, email="a@example.com", username="alice", password="password123", code=None):
    if code is None:
        r = env.client.post("/auth/otp/request", json={"email": email, "purpose": "signup"})
        assert r.status_code == 200, r.text
        code = env.outbox[-1][1]
    return env.client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password, "otp_code": code, **BIRTH},
    )


# ---------- OTP: สมัครสมาชิก ----------


def test_signup_with_otp_success_and_login(env):
    r = _signup(env)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == "a@example.com"
    assert env.outbox[-1][0] == "a@example.com" and len(env.outbox[-1][1]) == 6

    login = env.client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert login.status_code == 200


def test_signup_without_valid_otp_rejected(env):
    r = _signup(env, code="123456")  # ไม่เคยขอ OTP
    assert r.status_code == 400
    assert env.client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 401


def test_otp_is_single_use(env):
    assert _signup(env).status_code == 201
    code = env.outbox[-1][1]
    again = _signup(env, email="a@example.com", username="alice2", code=code)
    assert again.status_code == 400  # อีเมลถูกใช้แล้ว (เช็คก่อน OTP)


def test_wrong_otp_locks_after_max_attempts(env, monkeypatch):
    monkeypatch.setattr(settings, "otp_max_attempts", 3)
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    real = env.outbox[-1][1]
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(3):
        assert _signup(env, code=wrong).status_code == 400
    # ใส่รหัสถูกหลังโดนล็อกก็ใช้ไม่ได้แล้ว ต้องขอใหม่
    assert _signup(env, code=real).status_code == 400


def test_expired_otp_rejected(env, monkeypatch):
    monkeypatch.setattr(settings, "otp_expire_minutes", -1)  # หมดอายุทันที
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    assert _signup(env, code=env.outbox[-1][1]).status_code == 400


def test_resend_cooldown_returns_429(env, monkeypatch):
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 60)
    assert env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"}).status_code == 200
    r = env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    assert r.status_code == 429


def test_new_otp_invalidates_old_one(env):
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    old = env.outbox[-1][1]
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    new = env.outbox[-1][1]
    if old != new:  # (ชนกัน 1 ใน 1,000,000 ข้ามได้)
        assert _signup(env, code=old).status_code == 400
    assert _signup(env, code=new).status_code == 201


def test_duplicate_username_does_not_burn_otp(env):
    assert _signup(env).status_code == 201
    env.client.post("/auth/otp/request", json={"email": "b@example.com", "purpose": "signup"})
    code = env.outbox[-1][1]
    dup = _signup(env, email="b@example.com", username="alice", code=code)
    assert dup.status_code == 400 and "ชื่อผู้ใช้" in dup.json()["detail"]
    ok = _signup(env, email="b@example.com", username="bob", code=code)  # ใช้ OTP เดิมต่อได้
    assert ok.status_code == 201


def test_signup_otp_for_existing_email_rejected(env):
    assert _signup(env).status_code == 201
    r = env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    assert r.status_code == 400


def test_invalid_birth_date_is_422_not_500(env):
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    r = env.client.post(
        "/auth/register",
        json={
            "username": "alice", "email": "a@example.com", "password": "password123",
            "otp_code": env.outbox[-1][1], "birth_day": 31, "birth_month": 2, "birth_year": 2000,
        },
    )
    assert r.status_code == 422


def test_otp_stored_hashed_only(env):
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "signup"})
    code = env.outbox[-1][1]
    db = env.session()
    row = db.query(models.OtpCode).one()
    assert code not in row.code_hash and len(row.code_hash) == 64
    db.close()


# ---------- OTP: ลืมรหัสผ่าน ----------


def _verify_reset_otp(env, email, code):
    return env.client.post("/auth/password/verify-otp", json={"email": email, "otp_code": code})


def _full_reset(env, email, new_password):
    """ลืมรหัสผ่านครบ 3 ขั้น: ขอ OTP -> ตรวจ OTP ได้ reset_token -> ตั้งรหัสใหม่"""
    assert env.client.post("/auth/otp/request", json={"email": email, "purpose": "reset"}).status_code == 200
    code = env.outbox[-1][1]
    v = _verify_reset_otp(env, email, code)
    assert v.status_code == 200, v.text
    return env.client.post(
        "/auth/password/reset", json={"reset_token": v.json()["reset_token"], "new_password": new_password}
    )


def test_password_reset_flow(env):
    assert _signup(env).status_code == 201
    done = _full_reset(env, "a@example.com", "newpassword9")
    assert done.status_code == 200, done.text
    assert env.outbox[-1][2] == "reset"
    assert env.client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 401
    assert env.client.post("/auth/login", json={"email": "a@example.com", "password": "newpassword9"}).status_code == 200


def test_reset_requires_verified_otp_first(env):
    assert _signup(env).status_code == 201
    # ไม่มี reset_token ที่ถูกต้อง -> ตั้งรหัสผ่านไม่ได้
    r = env.client.post("/auth/password/reset", json={"reset_token": "x" * 30, "new_password": "newpassword9"})
    assert r.status_code == 401
    # wrong OTP -> ไม่ได้ token
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "reset"})
    real = env.outbox[-1][1]
    wrong = "000000" if real != "000000" else "111111"
    assert _verify_reset_otp(env, "a@example.com", wrong).status_code == 400


def test_reset_otp_is_single_use(env):
    assert _signup(env).status_code == 201
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "reset"})
    code = env.outbox[-1][1]
    assert _verify_reset_otp(env, "a@example.com", code).status_code == 200
    assert _verify_reset_otp(env, "a@example.com", code).status_code == 400


def test_reset_token_is_not_an_access_token_and_vice_versa(env):
    access = _signup(env).json()["access_token"]
    # access token เอามาตั้งรหัสผ่านไม่ได้
    r = env.client.post("/auth/password/reset", json={"reset_token": access, "new_password": "newpassword9"})
    assert r.status_code == 401
    # reset token เอาไปเข้า /auth/me ไม่ได้
    env.client.post("/auth/otp/request", json={"email": "a@example.com", "purpose": "reset"})
    tok = _verify_reset_otp(env, "a@example.com", env.outbox[-1][1]).json()["reset_token"]
    assert env.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_reset_for_unknown_email_looks_identical_and_sends_nothing(env):
    r = env.client.post("/auth/otp/request", json={"email": "ghost@example.com", "purpose": "reset"})
    assert r.status_code == 200
    assert env.outbox == []


def test_signup_otp_cannot_be_used_for_reset(env):
    assert _signup(env).status_code == 201
    env.client.post("/auth/otp/request", json={"email": "x@example.com", "purpose": "signup"})
    code = env.outbox[-1][1]
    assert _verify_reset_otp(env, "a@example.com", code).status_code == 400


# ---------- Google / Facebook ----------


def _fake_google(monkeypatch, sub="g-1", email="g@example.com", verified=True, name="Gina Google"):
    monkeypatch.setattr(
        social,
        "verify_google_id_token",
        lambda t: social.SocialIdentity("google", sub, email, verified, name),
    )


def _fake_facebook(monkeypatch, pid="f-1", email="f@example.com", name="Fah Face"):
    monkeypatch.setattr(
        social,
        "verify_facebook_access_token",
        lambda t: social.SocialIdentity("facebook", pid, email, bool(email), name),
    )


def test_google_new_user_needs_profile_then_completes(env, monkeypatch):
    _fake_google(monkeypatch)
    r = env.client.post("/auth/google", json={"id_token": "x" * 20})
    assert r.status_code == 200
    body = r.json()
    assert body["needs_profile"] is True and body["access_token"] is None
    assert body["email"] == "g@example.com" and body["suggested_username"] == "GinaGoogle"

    done = env.client.post(
        "/auth/social/complete",
        json={"registration_token": body["registration_token"], "username": "gina", **BIRTH},
    )
    assert done.status_code == 201, done.text
    assert done.json()["user"]["astro_profile"]["zodiac_sign"]

    # login ครั้งถัดไป ได้ token ตรงๆ
    again = env.client.post("/auth/google", json={"id_token": "x" * 20}).json()
    assert again["needs_profile"] is False and again["access_token"]


def test_facebook_new_user_flow(env, monkeypatch):
    _fake_facebook(monkeypatch)
    body = env.client.post("/auth/facebook", json={"access_token": "x" * 20}).json()
    assert body["needs_profile"] is True
    done = env.client.post(
        "/auth/social/complete",
        json={"registration_token": body["registration_token"], "username": "fah", **BIRTH},
    )
    assert done.status_code == 201
    db = env.session()
    u = db.query(models.User).one()
    assert u.facebook_id == "f-1" and u.password_hash is None and u.google_id is None
    db.close()


def test_google_links_existing_email_account(env, monkeypatch):
    assert _signup(env, email="a@example.com").status_code == 201
    _fake_google(monkeypatch, sub="g-77", email="A@Example.com")  # ตัวพิมพ์ต่างกันก็ต้องจับคู่ได้
    body = env.client.post("/auth/google", json={"id_token": "x" * 20}).json()
    assert body["needs_profile"] is False and body["user"]["username"] == "alice"
    db = env.session()
    assert db.query(models.User).count() == 1
    assert db.query(models.User).one().google_id == "g-77"
    db.close()


def test_unverified_google_email_not_linked(env, monkeypatch):
    assert _signup(env, email="a@example.com").status_code == 201
    _fake_google(monkeypatch, email="a@example.com", verified=False)
    r = env.client.post("/auth/google", json={"id_token": "x" * 20})
    assert r.status_code == 400


def test_google_without_email_still_rejected(env, monkeypatch):
    _fake_google(monkeypatch, email=None, verified=False)
    r = env.client.post("/auth/google", json={"id_token": "x" * 20})
    assert r.status_code == 400


def _fb_no_email_token(env, monkeypatch):
    _fake_facebook(monkeypatch, email=None)
    body = env.client.post("/auth/facebook", json={"access_token": "x" * 20}).json()
    assert body["needs_profile"] is True and body["needs_email"] is True and body["email"] is None
    return body["registration_token"]


def test_facebook_without_email_enters_email_otp_flow(env, monkeypatch):
    tok = _fb_no_email_token(env, monkeypatch)
    assert env.client.post("/auth/otp/request", json={"email": "Me@Example.com", "purpose": "signup"}).status_code == 200
    code = env.outbox[-1][1]
    done = env.client.post(
        "/auth/social/complete",
        json={"registration_token": tok, "username": "fah", "email": "Me@Example.com", "otp_code": code, **BIRTH},
    )
    assert done.status_code == 201, done.text
    assert done.json()["user"]["email"] == "me@example.com"
    db = env.session()
    u = db.query(models.User).one()
    assert u.facebook_id == "f-1" and u.password_hash is None
    db.close()
    # ครั้งถัดไป login ด้วย Facebook ได้ตรงๆ
    again = env.client.post("/auth/facebook", json={"access_token": "x" * 20}).json()
    assert again["needs_profile"] is False and again["access_token"]


def test_facebook_no_email_requires_email_and_otp(env, monkeypatch):
    tok = _fb_no_email_token(env, monkeypatch)
    r = env.client.post("/auth/social/complete", json={"registration_token": tok, "username": "fah", **BIRTH})
    assert r.status_code == 400


def test_facebook_no_email_wrong_otp_rejected(env, monkeypatch):
    tok = _fb_no_email_token(env, monkeypatch)
    env.client.post("/auth/otp/request", json={"email": "me@example.com", "purpose": "signup"})
    r = env.client.post(
        "/auth/social/complete",
        json={"registration_token": tok, "username": "fah", "email": "me@example.com", "otp_code": "000000", **BIRTH},
    )
    assert r.status_code == 400
    assert env.session().query(models.User).count() == 0


def test_facebook_no_email_cannot_take_existing_email(env, monkeypatch):
    assert _signup(env, email="taken@example.com").status_code == 201
    tok = _fb_no_email_token(env, monkeypatch)
    # ขอ OTP ของอีเมลที่มีบัญชีอยู่แล้วไม่ได้
    assert env.client.post("/auth/otp/request", json={"email": "taken@example.com", "purpose": "signup"}).status_code == 400
    r = env.client.post(
        "/auth/social/complete",
        json={"registration_token": tok, "username": "fah", "email": "taken@example.com", "otp_code": "123456", **BIRTH},
    )
    assert r.status_code == 400
    db = env.session()
    assert db.query(models.User).one().facebook_id is None
    db.close()


def test_facebook_no_email_duplicate_username_does_not_burn_otp(env, monkeypatch):
    assert _signup(env, email="a@example.com", username="fah").status_code == 201
    tok = _fb_no_email_token(env, monkeypatch)
    env.client.post("/auth/otp/request", json={"email": "me@example.com", "purpose": "signup"})
    code = env.outbox[-1][1]
    body = {"registration_token": tok, "email": "me@example.com", "otp_code": code, **BIRTH}
    assert env.client.post("/auth/social/complete", json={**body, "username": "fah"}).status_code == 400
    assert env.client.post("/auth/social/complete", json={**body, "username": "fah2"}).status_code == 201


def test_social_only_account_password_login_is_401_not_500(env, monkeypatch):
    _fake_google(monkeypatch)
    body = env.client.post("/auth/google", json={"id_token": "x" * 20}).json()
    env.client.post(
        "/auth/social/complete", json={"registration_token": body["registration_token"], "username": "gina", **BIRTH}
    )
    r = env.client.post("/auth/login", json={"email": "g@example.com", "password": "anything123"})
    assert r.status_code == 401


def test_social_only_user_can_set_password_via_reset(env, monkeypatch):
    _fake_google(monkeypatch)
    body = env.client.post("/auth/google", json={"id_token": "x" * 20}).json()
    env.client.post(
        "/auth/social/complete", json={"registration_token": body["registration_token"], "username": "gina", **BIRTH}
    )
    assert _full_reset(env, "g@example.com", "brandnew123").status_code == 200
    assert env.client.post("/auth/login", json={"email": "g@example.com", "password": "brandnew123"}).status_code == 200


def test_registration_token_is_not_an_access_token_and_vice_versa(env, monkeypatch):
    _fake_google(monkeypatch)
    body = env.client.post("/auth/google", json={"id_token": "x" * 20}).json()
    reg = body["registration_token"]
    assert env.client.get("/auth/me", headers={"Authorization": f"Bearer {reg}"}).status_code == 401

    access = _signup(env).json()["access_token"]
    r = env.client.post("/auth/social/complete", json={"registration_token": access, "username": "zed", **BIRTH})
    assert r.status_code == 401


def test_complete_twice_and_duplicate_username(env, monkeypatch):
    _fake_google(monkeypatch)
    tok = env.client.post("/auth/google", json={"id_token": "x" * 20}).json()["registration_token"]
    payload = {"registration_token": tok, "username": "gina", **BIRTH}
    assert env.client.post("/auth/social/complete", json=payload).status_code == 201
    assert env.client.post("/auth/social/complete", json=payload).status_code == 400

    _fake_facebook(monkeypatch)
    tok2 = env.client.post("/auth/facebook", json={"access_token": "x" * 20}).json()["registration_token"]
    r = env.client.post("/auth/social/complete", json={"registration_token": tok2, "username": "gina", **BIRTH})
    assert r.status_code == 400 and "ชื่อผู้ใช้" in r.json()["detail"]


# ---------- ตัวตรวจ token จริง (mock เครือข่าย) ----------


def test_google_verify_requires_config(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "google_client_ids", "")
    with pytest.raises(HTTPException) as e:
        social.verify_google_id_token("x" * 20)
    assert e.value.status_code == 503


def test_google_verify_rejects_wrong_audience(monkeypatch):
    from fastapi import HTTPException
    from google.oauth2 import id_token as gid

    monkeypatch.setattr(settings, "google_client_ids", "mine.apps.googleusercontent.com")
    monkeypatch.setattr(gid, "verify_oauth2_token", lambda *a, **k: {"aud": "someone-else", "sub": "1"})
    with pytest.raises(HTTPException) as e:
        social.verify_google_id_token("x" * 20)
    assert e.value.status_code == 401


def test_google_verify_accepts_matching_audience(monkeypatch):
    from google.oauth2 import id_token as gid

    monkeypatch.setattr(settings, "google_client_ids", "a.apps.googleusercontent.com, b.apps.googleusercontent.com")
    monkeypatch.setattr(
        gid,
        "verify_oauth2_token",
        lambda *a, **k: {"aud": "b.apps.googleusercontent.com", "sub": "42", "email": "e@x.com", "email_verified": True, "name": "E"},
    )
    ident = social.verify_google_id_token("x" * 20)
    assert (ident.provider_id, ident.email, ident.email_verified) == ("42", "e@x.com", True)


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def test_facebook_verify_checks_app_id_and_user(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "facebook_app_id", "123")
    monkeypatch.setattr(settings, "facebook_app_secret", "sec")

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/debug_token"):
            assert params["access_token"] == "123|sec"
            return _Resp({"data": {"is_valid": True, "app_id": "123", "user_id": "9"}})
        return _Resp({"id": "9", "name": "N", "email": "n@x.com"})

    monkeypatch.setattr(social.requests, "get", fake_get)
    ident = social.verify_facebook_access_token("x" * 20)
    assert (ident.provider_id, ident.email) == ("9", "n@x.com")

    # token ของแอปอื่น
    monkeypatch.setattr(
        social.requests, "get",
        lambda url, params=None, timeout=None: _Resp({"data": {"is_valid": True, "app_id": "999", "user_id": "9"}}),
    )
    with pytest.raises(HTTPException) as e:
        social.verify_facebook_access_token("x" * 20)
    assert e.value.status_code == 401


# --- จำกัดการเดารหัสผ่าน (login_throttle) ---

def _make_user(env, email="t@example.com", username="tuser"):
    env.client.post("/auth/otp/request", json={"email": email, "purpose": "signup"})
    code = env.outbox[-1][1]
    r = env.client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": "password123", "otp_code": code, **BIRTH},
    )
    assert r.status_code == 201, r.text


def test_login_locks_after_repeated_wrong_passwords(env, monkeypatch):
    monkeypatch.setenv("LOGIN_MAX_FAILS", "3")
    _make_user(env)
    bad = {"email": "t@example.com", "password": "wrong-password"}
    for _ in range(3):
        assert env.client.post("/auth/login", json=bad).status_code == 401
    r = env.client.post("/auth/login", json=bad)
    assert r.status_code == 429 and "นาที" in r.json()["detail"]
    assert "Retry-After" in r.headers
    # แม้ใส่รหัสถูกก็ยังโดนพักอยู่ (กันเดาแล้วลองรหัสถูกทีหลัง)
    assert env.client.post("/auth/login", json={"email": "t@example.com", "password": "password123"}).status_code == 429


def test_successful_login_resets_failure_counter(env, monkeypatch):
    monkeypatch.setenv("LOGIN_MAX_FAILS", "3")
    _make_user(env)
    bad = {"email": "t@example.com", "password": "wrong-password"}
    good = {"email": "t@example.com", "password": "password123"}
    for _ in range(2):
        env.client.post("/auth/login", json=bad)
    assert env.client.post("/auth/login", json=good).status_code == 200
    for _ in range(2):  # เริ่มนับใหม่ ยังไม่ครบ 3
        assert env.client.post("/auth/login", json=bad).status_code == 401
    assert env.client.post("/auth/login", json=good).status_code == 200


def test_lockout_is_per_email(env, monkeypatch):
    monkeypatch.setenv("LOGIN_MAX_FAILS", "2")
    monkeypatch.setenv("LOGIN_IP_MAX_FAILS", "100")
    _make_user(env, "a@example.com", "usera")
    _make_user(env, "b@example.com", "userb")
    for _ in range(2):
        env.client.post("/auth/login", json={"email": "a@example.com", "password": "x" * 9})
    assert env.client.post("/auth/login", json={"email": "a@example.com", "password": "x" * 9}).status_code == 429
    assert env.client.post("/auth/login", json={"email": "b@example.com", "password": "password123"}).status_code == 200
