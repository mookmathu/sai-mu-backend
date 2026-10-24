"""
otp.py
------
ออก/ตรวจรหัส OTP 6 หลัก

ความปลอดภัย:
- เก็บเฉพาะ HMAC-SHA256(jwt_secret, email:purpose:code) ไม่เก็บรหัสจริง
- รหัส 6 หลักเดาสุ่มได้ง่ายถ้าไม่จำกัดจำนวนครั้ง จึงจำกัดกรอกผิดได้
  otp_max_attempts ครั้ง/รหัส + หมดอายุใน otp_expire_minutes นาที + ใช้ได้ครั้งเดียว
- ขอรหัสใหม่ถี่เกินไปไม่ได้ (cooldown) กันคนยิงอีเมลขยะใส่ผู้อื่น
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from .timeutil import utcnow

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models
from .config import settings

PURPOSE_SIGNUP = "signup"
PURPOSE_RESET = "reset"
PURPOSE_LOGIN = "login"
VALID_PURPOSES = (PURPOSE_SIGNUP, PURPOSE_RESET, PURPOSE_LOGIN)

INVALID_MSG = "รหัส OTP ไม่ถูกต้องหรือหมดอายุ กรุณาขอรหัสใหม่"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_code(email: str, purpose: str, code: str) -> str:
    msg = f"{normalize_email(email)}:{purpose}:{code}".encode("utf-8")
    return hmac.new(settings.jwt_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def issue_otp(db: Session, email: str, purpose: str) -> str:
    """สร้าง OTP ใหม่แล้วคืนรหัสจริง (ให้ผู้เรียกส่งอีเมล) — โยน 429 ถ้าขอถี่เกิน"""
    email = normalize_email(email)
    now = utcnow()

    latest = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.email == email, models.OtpCode.purpose == purpose)
        .order_by(models.OtpCode.id.desc())
        .first()
    )
    if latest is not None:
        wait = settings.otp_resend_cooldown_seconds - (now - latest.created_at).total_seconds()
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail=f"ขอรหัสถี่เกินไป กรุณารออีก {int(wait) + 1} วินาที",
            )

    # รหัสเก่าที่ยังไม่ถูกใช้ทั้งหมดใช้ไม่ได้อีกเมื่อมีรหัสใหม่
    db.query(models.OtpCode).filter(
        models.OtpCode.email == email,
        models.OtpCode.purpose == purpose,
        models.OtpCode.used.is_(False),
    ).update({"used": True})

    code = f"{secrets.randbelow(10**6):06d}"
    db.add(
        models.OtpCode(
            email=email,
            purpose=purpose,
            code_hash=_hash_code(email, purpose, code),
            expires_at=now + timedelta(minutes=settings.otp_expire_minutes),
        )
    )
    db.commit()
    return code


def verify_otp(db: Session, email: str, purpose: str, code: str) -> None:
    """ตรวจรหัส — สำเร็จ = mark used แล้วคืน None, ไม่สำเร็จ = โยน HTTPException 400"""
    email = normalize_email(email)
    record = (
        db.query(models.OtpCode)
        .filter(
            models.OtpCode.email == email,
            models.OtpCode.purpose == purpose,
            models.OtpCode.used.is_(False),
        )
        .order_by(models.OtpCode.id.desc())
        .first()
    )
    if record is None:
        raise HTTPException(status_code=400, detail=INVALID_MSG)

    if record.expires_at < utcnow():
        record.used = True
        db.commit()
        raise HTTPException(status_code=400, detail=INVALID_MSG)

    if record.attempts >= settings.otp_max_attempts:
        record.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="กรอกรหัสผิดเกินกำหนด กรุณาขอรหัสใหม่")

    record.attempts += 1
    if not hmac.compare_digest(record.code_hash, _hash_code(email, purpose, code.strip())):
        remaining = settings.otp_max_attempts - record.attempts
        if remaining <= 0:
            record.used = True
        db.commit()
        detail = (
            f"รหัส OTP ไม่ถูกต้อง (เหลืออีก {remaining} ครั้ง)"
            if remaining > 0
            else "กรอกรหัสผิดเกินกำหนด กรุณาขอรหัสใหม่"
        )
        raise HTTPException(status_code=400, detail=detail)

    record.used = True
    db.commit()
