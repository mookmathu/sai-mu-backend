import pytest

from app import login_throttle


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """ตัวนับกรอกรหัสผ่านผิดเก็บในหน่วยความจำ — ล้างทุกเทสต์ ไม่ให้เทสต์หนึ่งทำให้อีกเทสต์โดนพัก"""
    login_throttle.reset()
    yield
    login_throttle.reset()
