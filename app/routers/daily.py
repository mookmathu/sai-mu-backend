"""
routers/daily.py
----------------
GET /daily/fortune — ดวงประจำวันแบบสั้น (คำทำนายคร่าว ๆ + สีแนะนำ + เลขประจำวัน)
สำหรับการ์ดหน้า Home ต้อง login (ใช้ราศีกำเนิดและวันเกิดของผู้ใช้) ดู app/daily_fortune.py
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import daily_fortune, history, models
from ..database import get_db
from .auth import get_current_user

router = APIRouter(prefix="/daily", tags=["daily"])


class ColorOut(BaseModel):
    name: str
    hex: str | None = None


class CategoryOut(BaseModel):
    key: str
    label: str
    score: int  # 1-5
    level: str  # high / mid / low
    level_label: str
    text: str
    tip: str


class FactorOut(BaseModel):
    key: str
    title: str
    text: str
    sources: list[str] = []


class LunarPhaseOut(BaseModel):
    name: str
    waxing: bool
    text: str


class DailyFortuneOut(BaseModel):
    date: str
    weekday: str
    zodiac_sign: str
    moon_house_no: int
    moon_house_name: str
    focus: str
    headline: str
    summary: str
    tip: str
    colors: list[ColorOut]
    color_note: str
    avoid_colors: list[ColorOut] = []
    numbers: list[int]
    # ฟิลด์ด้านล่างเพิ่มใหม่ (แอปเวอร์ชันเก่าไม่ต้องใช้ก็ได้)
    categories: list[CategoryOut] = []
    factors: list[FactorOut] = []
    birth_time_known: bool | None = None
    lunar_phase: LunarPhaseOut | None = None
    best_key: str | None = None
    caution_key: str | None = None


@router.get("/fortune", response_model=DailyFortuneOut, responses={400: {"description": "ข้อมูลที่ส่งมาไม่ถูกต้อง"}})
def get_daily_fortune(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    profile = current_user.astro_profile
    if profile is None or not profile.zodiac_sign:
        raise HTTPException(status_code=400, detail="ยังไม่มีข้อมูลราศีของบัญชีนี้ กรุณาแก้ไขโปรไฟล์ให้ครบ")

    today = daily_fortune.today_thai()
    chart = (
        db.query(models.DailyColorChart)
        .filter(
            models.DailyColorChart.year == today.year,
            models.DailyColorChart.month == today.month,
            models.DailyColorChart.day_of_month == today.day,
        )
        .first()
    )
    try:
        fortune = daily_fortune.build_daily_fortune(
            zodiac_sign=profile.zodiac_sign,
            birth_date=current_user.birth_date,
            today=today,
            color_chart=chart,
            birth_time=current_user.birth_time,
        )
        history.record_daily(db, current_user.id, fortune)  # วันละ 1 รายการในหน้าประวัติ
        return fortune
    except KeyError:
        # ชื่อราศีที่เก็บไว้ไม่อยู่ในตาราง (ข้อมูลเก่าจากสูตรเดิม) — รัน scripts.recalc_zodiac แก้ได้
        raise HTTPException(status_code=400, detail="ข้อมูลราศีของบัญชีนี้ไม่ถูกต้อง กรุณาแก้ไขโปรไฟล์เพื่อคำนวณใหม่")
