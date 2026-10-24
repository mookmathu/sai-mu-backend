"""
crud.py
-------
ฟังก์ชันคุยกับ DB โดยตรง แยกออกจาก router เพื่อให้ทดสอบและนำกลับมาใช้ง่าย
"""

import json
from datetime import date, datetime, time
from .timeutil import utcnow

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, security, zodiac
from .schemas import BirthFields, ChatSource, RegisterRequest


def get_user_by_email(db: Session, email: str) -> models.User | None:
    # เทียบแบบไม่สนตัวพิมพ์เล็ก/ใหญ่ — อีเมลที่มาจาก Google/Facebook อาจพิมพ์ใหญ่
    # ต่างจากที่ผู้ใช้เคยสมัครไว้ ไม่งั้นจะสร้างบัญชีซ้ำของคนเดียวกัน
    return db.query(models.User).filter(func.lower(models.User.email) == email.strip().lower()).first()


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_provider(db: Session, provider: str, provider_id: str) -> models.User | None:
    column = models.User.google_id if provider == "google" else models.User.facebook_id
    return db.query(models.User).filter(column == provider_id).first()


def link_provider(db: Session, user: models.User, provider: str, provider_id: str) -> None:
    """ผูกบัญชีเดิม (สมัครด้วยอีเมลไว้แล้ว) เข้ากับ Google/Facebook ที่อีเมลตรงกัน"""
    if provider == "google":
        user.google_id = provider_id
    else:
        user.facebook_id = provider_id
    db.commit()
    db.refresh(user)


def set_password(db: Session, user: models.User, new_password: str) -> None:
    user.password_hash = security.hash_password(new_password)
    db.commit()


def create_user(db: Session, data: RegisterRequest) -> models.User:
    return _create_user(
        db,
        username=data.username,
        email=data.email,
        password_hash=security.hash_password(data.password),
        birth=data,
    )


def create_social_user(
    db: Session, *, username: str, email: str, provider: str, provider_id: str, birth: BirthFields
) -> models.User:
    """สร้างบัญชีที่สมัครผ่าน Google/Facebook — ไม่มีรหัสผ่าน (password_hash = NULL)"""
    return _create_user(
        db,
        username=username,
        email=email,
        password_hash=None,
        birth=birth,
        google_id=provider_id if provider == "google" else None,
        facebook_id=provider_id if provider == "facebook" else None,
    )


def _create_user(
    db: Session,
    *,
    username: str,
    email: str,
    password_hash: str | None,
    birth: BirthFields,
    google_id: str | None = None,
    facebook_id: str | None = None,
) -> models.User:
    birth_date = date(birth.birth_year, birth.birth_month, birth.birth_day)

    birth_time_known = birth.birth_hour is not None and birth.birth_minute is not None
    birth_time = time(birth.birth_hour, birth.birth_minute) if birth_time_known else None
    # zodiac.py ใช้ time_frac (สัดส่วนของวัน) ไม่ใช่ hour/minute ตรงๆ —
    # ไม่ทราบเวลาเกิดจริงก็ปล่อยให้ fallback เป็นค่า default (เที่ยงวัน) ของมันเอง
    time_frac = (
        (birth.birth_hour + birth.birth_minute / 60) / 24
        if birth_time_known
        else zodiac.DEFAULT_TIME_FRAC
    )

    user = models.User(
        username=username,
        email=email,
        password_hash=password_hash,
        google_id=google_id,
        facebook_id=facebook_id,
        birth_date=birth_date,
        birth_time=birth_time,
        hide_birth_year=birth.hide_birth_year,
    )
    db.add(user)
    db.flush()  # ให้ user.id ถูก assign ก่อนสร้าง astro_profile ที่อ้างอิงถึง

    profile = models.UserAstroProfile(
        user_id=user.id,
        zodiac_sign=zodiac.calculate_zodiac_sign(birth_date, time_frac),
        zodiac_animal=zodiac.calculate_zodiac_animal(birth_date),
    )
    db.add(profile)

    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> models.User | None:
    user = get_user_by_email(db, email)
    # password_hash เป็น NULL ได้ (บัญชีที่สมัครด้วย Google/Facebook ยังไม่ตั้งรหัสผ่าน)
    # ต้องเช็คก่อนส่งให้ bcrypt ไม่งั้นพัง — ผู้ใช้กลุ่มนี้ตั้งรหัสผ่านได้ผ่าน "ลืมรหัสผ่าน"
    if not user or not user.password_hash or not security.verify_password(password, user.password_hash):
        return None
    return user


def save_chat_message(
    db: Session,
    user_id: int,
    role: str,
    content: str,
    sources: list[ChatSource] | None = None,
) -> models.ChatMessage:
    message = models.ChatMessage(
        user_id=user_id,
        role=role,
        content=content,
        # เก็บเป็น JSON string ในคอลัมน์เดียว ง่ายกว่าแยกตาราง sources ต่างหาก
        # เพราะ sources เป็นแค่ข้อมูลประกอบการแสดงผล ไม่ได้ query แยกเป็นรายการ
        sources=json.dumps([s.model_dump() for s in sources], ensure_ascii=False) if sources else None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_chat_history(db: Session, user_id: int, limit: int = 100) -> list[models.ChatMessage]:
    """คืนประวัติแชทของ user เรียงจากเก่าไปใหม่ (ตามลำดับที่ควรแสดงในหน้าจอ)
    limit จำกัดจำนวนข้อความล่าสุดที่ดึงมา กันโหลดประวัติยาวเกินไปทีเดียว"""
    messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == user_id)
        # id เป็นตัวตัดสินเมื่อเวลาเท่ากัน: Windows นาฬิกาละเอียดแค่ ~15 มิลลิวินาที ข้อความผู้ใช้กับ
        # คำตอบ AI ที่บันทึกพร้อมกันจึงอาจได้ created_at เท่ากัน ถ้าไม่มี id ลำดับจะสลับได้
        .order_by(models.ChatMessage.created_at.desc(), models.ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(messages))  # กลับเป็นเก่า→ใหม่ หลัง query แบบใหม่→เก่ามา


def get_recent_exchanges(db: Session, user_id: int, max_pairs: int = 3, max_age_minutes: int = 60):
    """คู่ (คำถามผู้ใช้, คำตอบ AI) ล่าสุดไม่เกิน max_pairs คู่ เรียงเก่า→ใหม่ เฉพาะที่เพิ่งคุยกัน
    ไม่เกิน max_age_minutes นาที — ใช้เป็นประวัติการคุยให้ Gemini เชื่อมคำถามต่อเนื่องได้"""
    from datetime import datetime, timedelta

    msgs = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == user_id)
        .order_by(models.ChatMessage.created_at.desc(), models.ChatMessage.id.desc())
        .limit(max_pairs * 2)
        .all()
    )
    msgs.reverse()  # เก่า→ใหม่
    cutoff = utcnow() - timedelta(minutes=max_age_minutes)
    pairs = []
    i = 0
    while i < len(msgs) - 1:
        u, a = msgs[i], msgs[i + 1]
        if u.role == "user" and a.role == "assistant" and a.created_at >= cutoff:
            pairs.append((u.content, a.content))
            i += 2
        else:
            i += 1
    return pairs


def get_last_exchange(db: Session, user_id: int, max_age_minutes: int = 60):
    """คู่ถาม-ตอบล่าสุดคู่เดียว (หรือ None) — ใช้ตัดสินข้อมูลทะเบียน/เบอร์ที่ต้องตอบต่อ"""
    pairs = get_recent_exchanges(db, user_id, max_pairs=1, max_age_minutes=max_age_minutes)
    return pairs[-1] if pairs else None


def clear_chat_history(db: Session, user_id: int) -> None:
    db.query(models.ChatMessage).filter(models.ChatMessage.user_id == user_id).delete()
    db.commit()


def update_profile(db: Session, user: models.User, data) -> models.User:
    """แก้ชื่อผู้ใช้/วันเกิด/เวลาเกิด แล้วคำนวณราศี-ปีนักษัตรใหม่ให้ตรงกับข้อมูลล่าสุด
    (data = UpdateProfileRequest) — เช็คชื่อซ้ำที่ router ก่อนเรียกฟังก์ชันนี้"""
    birth_date = date(data.birth_year, data.birth_month, data.birth_day)
    known = data.birth_hour is not None and data.birth_minute is not None
    time_frac = (data.birth_hour + data.birth_minute / 60) / 24 if known else zodiac.DEFAULT_TIME_FRAC

    user.username = data.username
    user.birth_date = birth_date
    user.birth_time = time(data.birth_hour, data.birth_minute) if known else None
    user.hide_birth_year = data.hide_birth_year

    profile = user.astro_profile
    if profile is None:
        profile = models.UserAstroProfile(user_id=user.id, zodiac_sign="", zodiac_animal="")
        db.add(profile)
    profile.zodiac_sign = zodiac.calculate_zodiac_sign(birth_date, time_frac)
    profile.zodiac_animal = zodiac.calculate_zodiac_animal(birth_date)
    profile.calculated_at = utcnow()

    db.commit()
    db.refresh(user)
    return user
