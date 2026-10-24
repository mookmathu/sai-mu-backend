"""
usage_limit.py
--------------
จำกัดจำนวนข้อความที่ "ต้องเรียก Gemini จริง" ต่อผู้ใช้ต่อวัน เพื่อไม่ให้คนคนเดียวใช้โควตาฟรีของ
Google หมดจนคนอื่น (เช่น อาจารย์ที่ตรวจโครงงาน) ใช้ต่อไม่ได้

- นับเฉพาะครั้งที่เรียก Gemini สำเร็จจริง: คำตอบที่มาจากแคช (ดู gemini_client.AnswerCache) ไม่นับ
- เก็บตัวนับในหน่วยความจำของ process (ง่าย ไม่ต้องมีตารางใหม่) รีเซ็ตทุกวันตามเวลาไทย
  ถ้ารีสตาร์ทเซิร์ฟเวอร์ ตัวนับเริ่มใหม่ — พอสำหรับงานโครงงาน แต่ถ้ารันหลาย worker ต่างคนต่างนับ
- ตั้งเพดานผ่าน .env:  DAILY_CHAT_LIMIT=30   (0 หรือค่าลบ = ไม่จำกัด)
"""

from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta, timezone

DEFAULT_DAILY_LIMIT = 30
WARN_WHEN_REMAINING = 5  # เหลือเท่านี้หรือน้อยกว่า → แจ้งผู้ใช้ล่วงหน้า

_BANGKOK = timezone(timedelta(hours=7))

LIMIT_REACHED_MESSAGE = (
    "วันนี้น้องมูตอบคำถามครบโควตาแล้ว พรุ่งนี้มาคุยกันใหม่ได้เลย "
    "ระหว่างนี้ดูดวงวันนี้ สีมงคล และเลขมงคลจากหน้าหลักได้ตามปกติ"
)


class DailyLimitExceeded(Exception):
    """ผู้ใช้ใช้ครบโควตาข้อความ AI ของวันนี้แล้ว"""


def today_bangkok() -> date:
    return datetime.now(_BANGKOK).date()


def daily_limit() -> int:
    """อ่านทุกครั้งที่เรียก (ไม่ cache) เพื่อให้เปลี่ยนค่าใน .env แล้วรีสตาร์ทมีผล และเทสต์ปรับค่าได้"""
    try:
        return int(os.environ.get("DAILY_CHAT_LIMIT", DEFAULT_DAILY_LIMIT))
    except ValueError:
        return DEFAULT_DAILY_LIMIT


_lock = threading.Lock()
_counts: dict[tuple[int, date], int] = {}


def used_today(user_id: int) -> int:
    with _lock:
        return _counts.get((user_id, today_bangkok()), 0)


def remaining_today(user_id: int) -> int | None:
    """จำนวนครั้งที่เหลือวันนี้ (None = ไม่จำกัด)"""
    limit = daily_limit()
    if limit <= 0:
        return None
    return max(0, limit - used_today(user_id))


def reset_all() -> None:
    """ใช้ในเทสต์"""
    with _lock:
        _counts.clear()


class UsageGuard:
    """ตัวคุมต่อหนึ่ง request — ถูกส่งให้ GeminiClient ผ่าน ContextVar
    before() เรียกก่อนยิง Gemini จริง (โยน DailyLimitExceeded ถ้าครบเพดาน)
    after()  เรียกหลังยิงสำเร็จ (นับ 1 ครั้ง)"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.consumed = False  # request นี้เรียก Gemini จริงไหม (ใช้ตัดสินว่าจะเตือน "เหลือกี่ข้อความ")

    def exhausted(self) -> bool:
        remaining = remaining_today(self.user_id)
        return remaining is not None and remaining <= 0

    def before(self) -> None:
        if self.exhausted():
            raise DailyLimitExceeded()

    def after(self) -> None:
        key = (self.user_id, today_bangkok())
        with _lock:
            # ล้างตัวนับของวันก่อนๆ กันหน่วยความจำโตไปเรื่อยๆ
            for k in [k for k in _counts if k[1] != key[1]]:
                del _counts[k]
            _counts[key] = _counts.get(key, 0) + 1
        self.consumed = True

    def low_remaining_notice(self) -> str | None:
        """ข้อความเตือนเมื่อใกล้ครบเพดาน (เฉพาะ request ที่เพิ่งใช้โควตาไป)"""
        if not self.consumed:
            return None
        remaining = remaining_today(self.user_id)
        if remaining is None or remaining > WARN_WHEN_REMAINING:
            return None
        if remaining == 0:
            return "นี่เป็นคำถามสุดท้ายของวันนี้แล้ว พรุ่งนี้มาคุยกันใหม่ได้เลย"
        return f"วันนี้เหลือโควตาคุยกับน้องมูอีก {remaining} ข้อความ"
