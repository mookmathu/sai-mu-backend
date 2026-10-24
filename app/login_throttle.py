"""
login_throttle.py
-----------------
กันการเดารหัสผ่านที่หน้า login: กรอกผิดเกินกำหนดต่ออีเมล (หรือต่อ IP) ภายในช่วงเวลาหนึ่ง
จะถูกพักไว้ชั่วคราวและตอบ 429 พร้อมบอกว่าต้องรอกี่นาที ล็อกอินสำเร็จแล้วตัวนับของอีเมลนั้นจะรีเซ็ต

- เก็บตัวนับในหน่วยความจำของ process (เหมือน usage_limit.py) รีสตาร์ทแล้วเริ่มใหม่ ถ้ารันหลาย worker
  ต่างคนต่างนับ — พอสำหรับโครงงาน ถ้าขึ้นจริงหลายเครื่องควรย้ายไป Redis
- ปรับค่าได้ใน .env: LOGIN_MAX_FAILS (ดีฟอลต์ 5) LOGIN_FAIL_WINDOW_MINUTES (15) LOGIN_IP_MAX_FAILS (20)
- IP: ใช้ที่อยู่ที่เซิร์ฟเวอร์เห็น ถ้าอยู่หลัง proxy ต้องตั้งให้ uvicorn อ่าน X-Forwarded-For (--proxy-headers)
"""

from __future__ import annotations

import os
import threading
import time

from fastapi import HTTPException


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def max_fails() -> int:
    return _int_env("LOGIN_MAX_FAILS", 5)


def ip_max_fails() -> int:
    return _int_env("LOGIN_IP_MAX_FAILS", 20)


def window_seconds() -> int:
    return _int_env("LOGIN_FAIL_WINDOW_MINUTES", 15) * 60


_lock = threading.Lock()
_fails: dict[str, list[float]] = {}  # key -> เวลา (monotonic) ของครั้งที่ผิด


def _recent(key: str, now: float) -> list[float]:
    cutoff = now - window_seconds()
    kept = [t for t in _fails.get(key, []) if t > cutoff]
    if kept:
        _fails[key] = kept
    else:
        _fails.pop(key, None)
    return kept


def _keys(email: str, ip: str | None) -> list[tuple[str, int]]:
    keys = [(f"email:{email.strip().lower()}", max_fails())]
    if ip:
        keys.append((f"ip:{ip}", ip_max_fails()))
    return keys


def check(email: str, ip: str | None) -> None:
    """เรียกก่อนตรวจรหัสผ่าน — ถ้าถูกพักอยู่ โยน 429"""
    now = time.monotonic()
    with _lock:
        for key, limit in _keys(email, ip):
            recent = _recent(key, now)
            if len(recent) >= limit:
                wait = int(recent[0] + window_seconds() - now) + 1
                minutes = max(1, (wait + 59) // 60)
                raise HTTPException(
                    status_code=429,
                    detail=f"กรอกรหัสผ่านผิดหลายครั้งเกินไป กรุณารอประมาณ {minutes} นาทีแล้วลองใหม่ (หรือกด ลืมรหัสผ่าน)",
                    headers={"Retry-After": str(wait)},
                )


def record_failure(email: str, ip: str | None) -> None:
    now = time.monotonic()
    with _lock:
        for key, _ in _keys(email, ip):
            _recent(key, now)
            _fails.setdefault(key, []).append(now)


def record_success(email: str) -> None:
    with _lock:
        _fails.pop(f"email:{email.strip().lower()}", None)


def reset() -> None:
    """ล้างทั้งหมด (ใช้ในเทสต์)"""
    with _lock:
        _fails.clear()
