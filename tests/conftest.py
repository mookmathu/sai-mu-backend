"""ตั้งค่าชุดทดสอบ — ใช้ฐานข้อมูล sqlite ชั่วคราว ไม่แตะ Supabase และไม่เรียก Gemini จริง

รัน:  pip install pytest   แล้ว   python -m pytest tests -v
"""
import os
import tempfile

# ต้องตั้งก่อน import app (settings อ่านค่าตอน import)
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_API_KEY"] = "test-admin-key"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import app

settings.otp_resend_cooldown_seconds = 0  # ไม่ต้องรอระหว่างขอ OTP ซ้ำในการทดสอบ
settings.login_otp_required = False  # เทสต์เดิมล็อกอินด้วยรหัสผ่านอย่างเดียว (เทสต์ OTP ล็อกอินเปิดเองในเทสต์นั้น)


@pytest.fixture(autouse=True)
def _fresh_db():
    # เทสต์ใน app/tests ตั้ง dependency_overrides ไว้ที่ app ตัวเดียวกัน — ล้างระหว่างเทสต์ชุดนี้ แล้วคืนค่าให้
    saved = dict(app.dependency_overrides)
    saved_admin_key = settings.admin_api_key
    app.dependency_overrides.clear()
    settings.admin_api_key = "test-admin-key"
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)
    settings.admin_api_key = saved_admin_key


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


ADMIN = {"X-Admin-Key": "test-admin-key"}


def signup(client, db, email="mu@example.com", username="mu", password="password123"):
    """สมัครสมาชิกผ่าน endpoint จริง (ขอ OTP แล้วอ่านรหัสจากฐานข้อมูลโดยตรง)
    คืน (response, headers ที่มี Bearer token)"""
    from app import otp
    code = otp.issue_otp(db, email, otp.PURPOSE_SIGNUP)
    r = client.post("/auth/register", json={
        "username": username, "email": email, "password": password, "otp_code": code,
        "birth_day": 15, "birth_month": 5, "birth_year": 2000,
    })
    headers = {"Authorization": f"Bearer {r.json().get('access_token', '')}"}
    return r, headers


import pytest as _pytest_throttle  # noqa: E402


@_pytest_throttle.fixture(autouse=True)
def _reset_login_throttle():
    """ล้างตัวนับกรอกรหัสผ่านผิด (เก็บในหน่วยความจำ) ทุกเทสต์"""
    from app import login_throttle

    login_throttle.reset()
    yield
    login_throttle.reset()
