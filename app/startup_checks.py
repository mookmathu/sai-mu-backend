"""
startup_checks.py
-----------------
ตรวจค่าตั้งสำคัญตอนเซิร์ฟเวอร์สตาร์ท (เฉพาะ "มีค่าหรือยัง/ปลอดภัยไหม" ไม่แสดงค่าความลับออกมาเลย)

- ENVIRONMENT=development (ดีฟอลต์): แค่พิมพ์คำเตือนลง log ไม่ขัดขวางการรันในเครื่อง
- ENVIRONMENT=production: ถ้ามีข้อผิดพลาดร้ายแรง (ใช้ค่า default ของ JWT/แอดมิน, ยังไม่ตั้ง SMTP,
  ใช้ sqlite) จะ raise ให้เซิร์ฟเวอร์ไม่สตาร์ท แทนที่จะขึ้นระบบแบบเปราะบางโดยไม่รู้ตัว
"""

from __future__ import annotations

import logging

_log = logging.getLogger("uvicorn.error")

_DEFAULT_JWT = "CHANGE_ME_IN_PRODUCTION"
_DEFAULT_ADMIN = "CHANGE_ME_ADMIN_KEY"


def collect(settings) -> tuple[list[str], list[str]]:
    """คืน (errors, warnings) เป็นข้อความภาษาไทย"""
    errors: list[str] = []
    warnings: list[str] = []

    if settings.jwt_secret == _DEFAULT_JWT or len(settings.jwt_secret) < 32:
        errors.append("JWT_SECRET ยังเป็นค่า default หรือสั้นเกินไป (ควรสุ่ม ≥ 32 ตัวอักษร: python -c \"import secrets; print(secrets.token_hex(32))\")")
    if settings.admin_api_key == _DEFAULT_ADMIN or len(settings.admin_api_key) < 16:
        errors.append("ADMIN_API_KEY ยังเป็นค่า default หรือสั้นเกินไป (ใครก็เข้าหน้าแอดมินได้)")
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        errors.append("ยังไม่ได้ตั้ง SMTP_HOST/SMTP_USER/SMTP_PASSWORD — รหัส OTP จะไปโผล่ใน log แทนที่จะส่งถึงผู้ใช้")
    if settings.database_url.startswith("sqlite"):
        errors.append("DATABASE_URL ยังเป็น sqlite (ไฟล์ในเครื่อง) — ขึ้นจริงควรใช้ PostgreSQL/Supabase")
    if not settings.login_otp_required:
        warnings.append("LOGIN_OTP_REQUIRED=false — ล็อกอินไม่ต้องใช้ OTP (ปลอดภัยน้อยลง)")
    if settings.cors_origin_list == ["*"]:
        warnings.append("CORS_ORIGINS เป็น * (ทุกโดเมน) — ขึ้นจริงควรระบุโดเมนของเว็บแอป")
    if not settings.google_client_id_list:
        warnings.append("ยังไม่ได้ตั้ง GOOGLE_CLIENT_IDS — ปุ่ม Google ใช้ไม่ได้")
    if not settings.facebook_app_id or not settings.facebook_app_secret:
        warnings.append("ยังไม่ได้ตั้ง FACEBOOK_APP_ID/FACEBOOK_APP_SECRET — ปุ่ม Facebook ใช้ไม่ได้")
    return errors, warnings


def run(settings) -> None:
    errors, warnings = collect(settings)
    if settings.is_production:
        for w in warnings:
            _log.warning("[config] %s", w)
        if errors:
            for e in errors:
                _log.error("[config] %s", e)
            raise RuntimeError(
                "ค่าตั้งสำหรับ production ยังไม่พร้อม:\n- " + "\n- ".join(errors)
            )
    else:
        # dev: เตือนสั้นๆ ให้รู้ว่าอะไรยังไม่พร้อมก่อนขึ้นจริง (ไม่รกเกินไป — รวมเป็นบรรทัดเดียว)
        todo = len(errors) + len(warnings)
        if todo:
            _log.info("[config] โหมด development: ยังมี %d รายการที่ต้องตั้งก่อนขึ้นจริง (ตั้ง ENVIRONMENT=production เพื่อดูรายละเอียด)", todo)
