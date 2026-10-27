"""
content_schemas.py
-------------------
Pydantic schema สำหรับเนื้อหาที่จัดการผ่านหน้าเว็บแอดมิน (admin/index.html):
สีมงคลประจำวันตามหลักจีน (daily color charts) และสถานที่สิ่งศักดิ์สิทธิ์ (sacred places)

แยกไฟล์ออกจาก schemas.py หลัก (ซึ่งเป็นของฝั่งผู้ใช้ทั่วไป/auth/chat) เพราะ
เป็นคนละส่วนของระบบ ไม่อยากปนกันจนไฟล์เดียวยาวเกินไป
"""

import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DailyColorChartIn(BaseModel):
    """ใช้ทั้งตอนสร้างใหม่และตอนแก้ไข (PUT) — ฟิลด์เหมือนกันทุกอย่าง

    ผูกกับปี/เดือน/วันที่จริง (year/month/day_of_month) เพราะธาตุประจำวันและ
    วันในสัปดาห์จริงเปลี่ยนไปตามปีจริง ไม่ใช่วันซ้ำทุกปี — ไม่ตรวจสอบว่าวันที่นั้น
    มีจริงในเดือนนั้นหรือไม่ (เช่น 30 ก.พ.) เพื่อความง่าย ฝั่งแอดมินควรกรอกให้
    ถูกต้องเอง วันในสัปดาห์คำนวณฝั่งหน้าเว็บจาก year/month/day_of_month เอง
    ไม่ต้องเก็บซ้ำในฐานข้อมูล"""

    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    day_of_month: int = Field(ge=1, le=31)
    element_name: str | None = Field(None, max_length=50)
    help_colors: str | None = Field(None, max_length=255)
    love_colors: str | None = Field(None, max_length=255)
    luck_colors: str | None = Field(None, max_length=255)
    problem_colors: str | None = Field(None, max_length=255)
    zodiac_note: str | None = Field(None, max_length=255)
    source_note: str | None = Field(None, max_length=255)


class DailyColorChartOut(DailyColorChartIn):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SacredPlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(None, max_length=50)
    province: str = Field(default="กรุงเทพมหานคร", max_length=100)
    district: str | None = Field(None, max_length=100)
    highlight: str | None = Field(None, max_length=255)
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    image_url: str | None = Field(None, max_length=500)
    source_note: str | None = None
    # รายละเอียดแยกหมวด: หลายบรรทัด = หลายรายการ (บรรทัดเขียน "หัวข้อ | รายละเอียด" ได้)
    travel_info: str | None = None
    worship_steps: str | None = None
    offerings: str | None = None
    etiquette: str | None = None
    opening_hours: str | None = Field(None, max_length=255)
    best_time: str | None = Field(None, max_length=255)
    wish_tags: str | None = Field(None, max_length=255)
    # บทสวด/คาถา: ข้อความ JSON ของ list [{"title": ..., "text": ..., "note": ...}]
    chants: str | None = None

    @field_validator("chants")
    @classmethod
    def _check_chants(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            data = json.loads(v)
        except ValueError as e:
            raise ValueError("chants ต้องเป็น JSON") from e
        if not isinstance(data, list) or len(data) > 50:
            raise ValueError("chants ต้องเป็นรายการ (ไม่เกิน 50 บท)")
        clean = []
        for it in data:
            if not isinstance(it, dict):
                raise ValueError("chants แต่ละรายการต้องเป็นออบเจ็กต์")
            clean.append({
                "title": str(it.get("title") or "")[:200],
                "text": str(it.get("text") or "")[:5000],
                "note": str(it.get("note") or "")[:300],
            })
        return json.dumps(clean, ensure_ascii=False)


class SacredPlaceOut(SacredPlaceIn):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- บทความองค์เทพ (คลังบทความ) ----------

ARTICLE_TOPICS = ("wisdom", "wealth", "love", "success", "protection", "change")


class DeityArticleIn(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(None, max_length=300)
    summary: str | None = None
    topics: str | None = Field(None, max_length=255)  # คั่นจุลภาค
    image_url: str | None = Field(None, max_length=500)
    sections: str | None = None  # JSON list [{"heading","body","image"?}]
    mantra: str | None = Field(None, max_length=500)
    mantra_note: str | None = Field(None, max_length=500)
    source_note: str | None = None
    is_published: bool = True
    sort_order: int = 0

    @field_validator("topics")
    @classmethod
    def _check_topics(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        items = [t.strip() for t in v.split(",") if t.strip()]
        bad = [t for t in items if t not in ARTICLE_TOPICS]
        if bad:
            raise ValueError("topics ไม่ถูกต้อง: " + ", ".join(bad))
        return ",".join(dict.fromkeys(items))

    @field_validator("sections")
    @classmethod
    def _check_sections(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            data = json.loads(v)
        except ValueError as e:
            raise ValueError("sections ต้องเป็น JSON") from e
        if not isinstance(data, list) or len(data) > 30:
            raise ValueError("sections ต้องเป็นรายการ (ไม่เกิน 30 หัวข้อ)")
        clean = []
        for it in data:
            if not isinstance(it, dict):
                raise ValueError("sections แต่ละรายการต้องเป็นออบเจ็กต์")
            entry = {
                "heading": str(it.get("heading") or "")[:200],
                "body": str(it.get("body") or "")[:8000],
            }
            image = str(it.get("image") or "").strip()[:1000]
            if image.startswith(("https://", "http://")):  # รับเฉพาะลิงก์เว็บ (กันค่าแปลกปลอม)
                entry["image"] = image
            clean.append(entry)
        return json.dumps(clean, ensure_ascii=False)


class DeityArticleOut(DeityArticleIn):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
