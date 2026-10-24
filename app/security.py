"""
security.py
------------
แฮชรหัสผ่านด้วย bcrypt โดยตรง (ไม่ผ่าน passlib) และออก/ตรวจ JWT token

หมายเหตุ: เดิมตั้งใจใช้ passlib[bcrypt] แต่ passlib เวอร์ชันล่าสุดที่ยังคง
maintain อยู่ (1.7.4) เข้ากันไม่ได้กับ bcrypt >= 4.1 (เอา __about__ ออก ทำให้
passlib ตรวจเวอร์ชัน backend พังและโยน error ตอน hash) จึงเรียก bcrypt ตรงๆ
แทน — เสถียรกว่าและ dependency น้อยกว่าด้วย
"""

from datetime import datetime, timedelta
from .timeutil import utcnow

import bcrypt
from jose import JWTError, jwt

from .config import settings


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    expire = utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_registration_token(provider: str, provider_id: str, email: str, name: str | None) -> str:
    """token ชั่วคราวของผู้ใช้ social ที่ provider ยืนยันตัวตนแล้วแต่ยังไม่มีบัญชี —
    ถือไว้ระหว่างกรอกวันเกิด/ชื่อผู้ใช้ แล้วส่งกลับมาที่ /auth/social/complete
    เซ็นด้วย jwt_secret จึงปลอม/แก้ email ไม่ได้ และไม่ใช่ access token (ไม่มี "sub")
    ใช้เข้า API อื่นไม่ได้"""
    expire = utcnow() + timedelta(minutes=settings.registration_token_expire_minutes)
    payload = {"typ": "social_reg", "prov": provider, "pid": provider_id, "email": email, "name": name, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_registration_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "social_reg":
        return None
    return payload


RESET_TOKEN_EXPIRE_MINUTES = 10


def create_reset_token(user_id: int) -> str:
    """token อายุสั้นที่ออกให้หลังยืนยัน OTP ของ "ลืมรหัสผ่าน" สำเร็จ — ใช้ได้กับ
    /auth/password/reset เท่านั้น (typ ต่างจาก access token และไม่มี "sub"
    จึงเอาไปเข้าถึง API อื่นไม่ได้)"""
    expire = utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    payload = {"typ": "pw_reset", "uid": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_reset_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("typ") != "pw_reset":
            return None
        return int(payload["uid"])
    except (JWTError, KeyError, ValueError):
        return None


def decode_access_token(token: str) -> int | None:
    """คืนค่า user_id ถ้า token ถูกต้อง ไม่งั้นคืน None"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None
