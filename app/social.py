"""
social.py
---------
ตรวจ token ที่แอปได้จาก Google / Facebook ฝั่งเซิร์ฟเวอร์ แล้วแปลงเป็น SocialIdentity
กลาง (ห้ามเชื่อ email/ชื่อที่แอปส่งมาเองเด็ดขาด — ต้องได้จาก token ที่ provider
เซ็นรับรองเท่านั้น ไม่งั้นใครก็ปลอมเป็นคนอื่นได้)
"""

from dataclasses import dataclass

import logging

import requests
from fastapi import HTTPException

from .config import settings


@dataclass
class SocialIdentity:
    provider: str  # "google" | "facebook"
    provider_id: str
    email: str | None
    email_verified: bool
    name: str | None


def verify_google_id_token(id_token: str) -> SocialIdentity:
    allowed = settings.google_client_id_list
    if not allowed:
        raise HTTPException(status_code=503, detail="ระบบยังไม่ได้ตั้งค่าการเข้าสู่ระบบด้วย Google")

    # import ในฟังก์ชัน: ไม่บังคับให้ต้องติดตั้ง google-auth ถ้าไม่ได้ใช้ฟีเจอร์นี้
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    try:
        # audience=None = ให้ไลบรารีตรวจลายเซ็น/issuer/วันหมดอายุ แล้วเราตรวจ aud
        # เองด้านล่าง (รองรับหลาย client id ได้)
        info = google_id_token.verify_oauth2_token(id_token, google_requests.Request(), audience=None)
    except ValueError:
        raise HTTPException(status_code=401, detail="Google token ไม่ถูกต้องหรือหมดอายุ")
    except Exception:  # noqa: BLE001 — เช่น ดึง public key ของ Google ไม่ได้
        raise HTTPException(status_code=502, detail="ตรวจสอบกับ Google ไม่สำเร็จ กรุณาลองใหม่")

    if info.get("aud") not in allowed:
        raise HTTPException(status_code=401, detail="Google token ไม่ได้ออกให้แอปนี้")

    return SocialIdentity(
        provider="google",
        provider_id=str(info["sub"]),
        email=info.get("email"),
        email_verified=bool(info.get("email_verified")),
        name=info.get("name"),
    )


def verify_facebook_access_token(access_token: str) -> SocialIdentity:
    if not (settings.facebook_app_id and settings.facebook_app_secret):
        raise HTTPException(status_code=503, detail="ระบบยังไม่ได้ตั้งค่าการเข้าสู่ระบบด้วย Facebook")

    graph = "https://graph.facebook.com"
    try:
        # 1) ถามว่า token นี้ถูกออกให้แอปเราจริงไหม + ยังใช้ได้ไหม (ใช้ app token
        #    = "app_id|app_secret" ซึ่งอยู่ฝั่งเซิร์ฟเวอร์เท่านั้น)
        dbg = requests.get(
            f"{graph}/debug_token",
            params={
                "input_token": access_token,
                "access_token": f"{settings.facebook_app_id}|{settings.facebook_app_secret}",
            },
            timeout=10,
        ).json()
        data = dbg.get("data") or {}
        if not data.get("is_valid") or str(data.get("app_id")) != settings.facebook_app_id:
            raise HTTPException(status_code=401, detail="Facebook token ไม่ถูกต้องหรือหมดอายุ")

        # 2) ดึงโปรไฟล์ด้วย token เดียวกัน
        me = requests.get(
            f"{graph}/me",
            params={"fields": "id,name,email", "access_token": access_token},
            timeout=10,
        ).json()
    except HTTPException:
        raise
    except (requests.RequestException, ValueError):
        raise HTTPException(status_code=502, detail="ตรวจสอบกับ Facebook ไม่สำเร็จ กรุณาลองใหม่")

    # log เพื่อ debug ว่า Facebook ส่งอะไรกลับมา (ไม่ log token/อีเมลจริง)
    logging.getLogger("uvicorn.error").info(
        "[FB] scopes ที่ได้รับ=%s | มี email ใน /me=%s | error=%s",
        data.get("scopes"), bool(me.get("email")), me.get("error", {}).get("message"),
    )

    if "id" not in me or str(me["id"]) != str(data.get("user_id")):
        raise HTTPException(status_code=401, detail="Facebook token ไม่ถูกต้อง")

    return SocialIdentity(
        provider="facebook",
        provider_id=str(me["id"]),
        email=me.get("email"),
        # Facebook ส่ง email กลับมาเฉพาะอีเมลที่ยืนยันแล้ว
        email_verified=bool(me.get("email")),
        name=me.get("name"),
    )
