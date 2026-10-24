"""
mailer.py
---------
ส่งอีเมลผ่าน SMTP (ใช้ส่งรหัส OTP) — ใช้ smtplib มาตรฐาน ไม่เพิ่ม dependency

ถ้ายังไม่ได้ตั้ง SMTP_HOST ใน .env จะเข้าโหมด dev: พิมพ์เนื้อหา/รหัส OTP ลง log
ของเซิร์ฟเวอร์แทนการส่งจริง ลองระบบทั้ง flow ได้เลยโดยไม่ต้องมีอีเมลจริง
(ห้ามปล่อยไว้แบบนี้ตอน deploy จริง เพราะรหัสจะไปโผล่ใน log แทนที่จะถึงผู้ใช้)
"""

import logging
from pathlib import Path
import smtplib

import requests
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from .config import settings

logger = logging.getLogger("uvicorn.error")


_LOGO_PATH = Path(__file__).parent / "assets" / "mutelove_logo.png"


def _load_logo() -> bytes | None:
    try:
        return _LOGO_PATH.read_bytes()
    except OSError:
        return None


def _html_body(code: str, action: str, minutes: int, logo_cid: str | None = None) -> str:
    digits = "".join(
        f'<td style="width:42px;height:54px;text-align:center;background:#FFF5F8;border:1.5px solid #F4C6D3;'
        f'border-radius:12px;font-size:28px;font-weight:bold;color:#7A2E42;font-family:Tahoma,Arial,sans-serif;">{d}</td>'
        f'<td style="width:6px;"></td>'
        for d in code
    )
    logo = (
        f'<img src="cid:{logo_cid}" width="72" height="72" alt="Mutelove" '
        'style="display:block;margin:0 auto;border-radius:36px;border:3px solid #ffffff;">'
        if logo_cid
        else '<div style="font-size:28px;font-weight:bold;color:#ffffff;">Mutelove</div>'
    )
    return f"""\
<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#FBEFF2;font-family:Tahoma,'Segoe UI',Arial,sans-serif;color:#4A2A33;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FBEFF2;padding:28px 12px;">
<tr><td align="center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:440px;background:#ffffff;border-radius:24px;overflow:hidden;box-shadow:0 6px 24px rgba(122,46,66,0.10);">

    <!-- ส่วนหัวสีชมพู -->
    <tr><td align="center" style="background:#E58AA5;background-image:linear-gradient(135deg,#F4A7C0 0%,#D97A93 100%);padding:32px 24px 26px;">
      {logo}
      <div style="margin-top:12px;font-size:24px;font-weight:bold;color:#ffffff;letter-spacing:0.5px;">Mutelove</div>
      <div style="margin-top:2px;font-size:13px;color:#FFE9F0;">ดูดวงกับน้องมู</div>
    </td></tr>

    <!-- เนื้อหา -->
    <tr><td align="center" style="padding:30px 28px 8px;">
      <div style="font-size:18px;font-weight:bold;color:#7A2E42;">รหัสยืนยันของคุณ</div>
      <div style="margin-top:6px;font-size:14px;color:#8A6470;">ใช้สำหรับ{action}</div>
    </td></tr>

    <tr><td align="center" style="padding:20px 12px 6px;">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>{digits}</tr></table>
    </td></tr>

    <tr><td align="center" style="padding:16px 28px 6px;">
      <span style="display:inline-block;background:#FFF3D6;color:#8A6A1E;font-size:13px;padding:6px 14px;border-radius:999px;">
        &#9201; ใช้ได้ภายใน {minutes} นาที และใช้ได้เพียงครั้งเดียว
      </span>
    </td></tr>

    <tr><td style="padding:22px 28px 6px;"><div style="border-top:1px solid #F3E7EA;"></div></td></tr>

    <!-- คำเตือนความปลอดภัย -->
    <tr><td style="padding:10px 28px 26px;font-size:13px;line-height:1.8;color:#6B4A54;">
      <b style="color:#7A2E42;">เพื่อความปลอดภัยของบัญชีคุณ</b><br>
      &bull; กรุณาอย่าบอกรหัสนี้กับใคร ทีมงานจะไม่ขอรหัสนี้จากคุณ<br>
      &bull; หากคุณไม่ได้เป็นผู้ขอรหัส ไม่ต้องทำอะไร ปล่อยผ่านได้เลยค่ะ
    </td></tr>

    <!-- ท้ายอีเมล -->
    <tr><td align="center" style="background:#FFF9FA;padding:16px 24px;font-size:12px;color:#A07884;line-height:1.7;">
      อีเมลนี้ส่งอัตโนมัติจากแอป Mutelove
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""


def _send_via_brevo(to_email: str, code: str, action: str, minutes: int) -> None:
    """ส่งผ่าน Brevo HTTPS API (พอร์ต 443) — ใช้บนโฮสต์ที่บล็อก SMTP ไม่โยน exception ออกไป"""
    sender_email = settings.brevo_sender or settings.smtp_user
    text = (
        "สวัสดีค่ะ จาก Mutelove\n\n"
        f"รหัสสำหรับ{action}ของคุณคือ\n\n    {code}\n\n"
        f"รหัสนี้ใช้ได้ {minutes} นาที และใช้ได้เพียงครั้งเดียว\n"
        "เพื่อความปลอดภัย กรุณาอย่าบอกรหัสนี้กับใคร ทีมงานจะไม่ขอรหัสนี้จากคุณ\n"
        "หากคุณไม่ได้เป็นผู้ขอรหัส ไม่ต้องทำอะไร ปล่อยผ่านได้เลยค่ะ\n\n"
        "Mutelove - ดูดวงกับน้องมู\n"
    )
    payload = {
        "sender": {"name": "Mutelove", "email": sender_email},
        "to": [{"email": to_email}],
        "replyTo": {"email": sender_email},
        "subject": f"{code} คือรหัสยืนยันของคุณ - Mutelove",
        "htmlContent": _html_body(code, action, minutes, None),
        "textContent": text,
    }
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
            timeout=15,
        )
        if r.status_code >= 300:
            logger.error("Brevo ส่ง OTP ไปที่ %s ไม่สำเร็จ: HTTP %s %s", to_email, r.status_code, r.text[:300])
    except Exception:  # noqa: BLE001
        logger.exception("ส่งอีเมล OTP (Brevo) ไปที่ %s ไม่สำเร็จ", to_email)


def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    """ส่ง OTP ไปที่ to_email — ไม่โยน exception ออกไป (ถ้าส่งไม่ได้แค่ log ไว้
    ผู้ใช้กด "ส่งรหัสอีกครั้ง" ได้) เพราะฟังก์ชันนี้รันใน background task
    หลังตอบ request ไปแล้ว ไม่มีที่ให้ส่ง error กลับไปหาผู้ใช้อยู่ดี"""
    if not settings.smtp_host and not settings.brevo_api_key:
        logger.warning("[DEV] SMTP ไม่ได้ตั้งค่า — OTP สำหรับ %s (%s) คือ %s", to_email, purpose, code)
        return

    action = {
        "signup": "ยืนยันอีเมลเพื่อสมัครสมาชิก",
        "login": "ยืนยันการเข้าสู่ระบบ",
    }.get(purpose, "ตั้งรหัสผ่านใหม่")
    minutes = settings.otp_expire_minutes

    if settings.brevo_api_key:
        _send_via_brevo(to_email, code, action, minutes)
        return

    msg = EmailMessage()
    msg["Subject"] = f"{code} คือรหัสยืนยันของคุณ - Mutelove"
    # ชื่อผู้ส่งที่ผู้ใช้เห็นในกล่องจดหมายคือ "Mutelove" (ถ้า SMTP_FROM ตั้งชื่อมาเองแล้วจะใช้ตามนั้น)
    sender = settings.smtp_from or settings.smtp_user
    msg["From"] = sender if parseaddr(sender)[0] else formataddr(("Mutelove", sender))
    msg["To"] = to_email
    msg["Reply-To"] = settings.smtp_user

    msg.set_content(
        "สวัสดีค่ะ จาก Mutelove\n\n"
        f"รหัสสำหรับ{action}ของคุณคือ\n\n"
        f"    {code}\n\n"
        f"รหัสนี้ใช้ได้ {minutes} นาที และใช้ได้เพียงครั้งเดียว\n"
        "เพื่อความปลอดภัย กรุณาอย่าบอกรหัสนี้กับใคร ทีมงานจะไม่ขอรหัสนี้จากคุณ\n"
        "หากคุณไม่ได้เป็นผู้ขอรหัส ไม่ต้องทำอะไร ปล่อยผ่านได้เลยค่ะ\n\n"
        "Mutelove - ดูดวงกับน้องมู\n"
    )
    logo_cid = make_msgid(domain="mutelove.app")[1:-1]
    logo_bytes = _load_logo()
    msg.add_alternative(_html_body(code, action, minutes, logo_cid if logo_bytes else None), subtype="html")
    if logo_bytes:  # ฝังโลโก้ไว้ในตัวอีเมล (ไม่ต้องพึ่งลิงก์ภายนอก จึงไม่โดนบล็อกรูป)
        msg.get_payload()[1].add_related(logo_bytes, "image", "png", cid=f"<{logo_cid}>", disposition="inline")

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
    except Exception:  # noqa: BLE001 — ครอบทุกกรณี (เครือข่าย/รหัสผิด/โดนบล็อก) แล้ว log
        logger.exception("ส่งอีเมล OTP ไปที่ %s ไม่สำเร็จ", to_email)
