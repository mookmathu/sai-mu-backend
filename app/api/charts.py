"""
api/charts.py
----------------
POST /api/v1/charts                       — สร้าง natal chart จากผู้ใช้ที่ login อยู่
POST /api/v1/charts/{chart_id}/transits   — เพิ่ม transit snapshot ให้ chart ที่มีอยู่
GET  /api/v1/charts/{chart_id}            — ดึง chart ที่เคยสร้างไว้ (in-memory เท่านั้น — ดู NOTE)

NOTE (ความจงใจ ไม่ใช่ของที่ลืมทำ): chart ยังไม่ persist ลง PostgreSQL ตามที่สเปกข้อ 15
แนะนำ — เก็บไว้ใน in-memory dict ระดับ process เพื่อให้ endpoint ครบตามข้อ 13 ก่อน,
ส่วนตาราง `charts`/`chart_snapshots` จริงเป็นงานถัดไป (chart หายเมื่อ restart server)
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .. import models
from ..astrology.chart_builder import build_natal_chart
from ..astrology.schemas import GeoLocation, NatalChart
from ..astrology.transit import build_transit_snapshot
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api/v1/charts", tags=["charts"])

# Process-local cache — see NOTE above.
_CHART_STORE: dict[str, NatalChart] = {}


class ChartCreateRequest(BaseModel):
    # ทั้งหมด optional — ถ้าไม่ส่งมา จะใช้ข้อมูลเกิดของผู้ใช้ที่ login อยู่แทน
    birth_date: date | None = None
    birth_time: str | None = None  # "HH:MM"
    lat: float | None = None
    lon: float | None = None
    place_name: str | None = None


@router.post("", response_model=NatalChart)
def create_chart(
    payload: ChartCreateRequest,
    current_user: models.User = Depends(get_current_user),
):
    birth_date = payload.birth_date or current_user.birth_date
    birth_time = current_user.birth_time
    if payload.birth_time:
        h, m = map(int, payload.birth_time.split(":"))
        from datetime import time as _time

        birth_time = _time(h, m)

    location = None
    if payload.lat is not None and payload.lon is not None:
        location = GeoLocation(lat=payload.lat, lon=payload.lon, place_name=payload.place_name)

    chart = build_natal_chart(birth_date=birth_date, birth_time=birth_time, location=location)
    _CHART_STORE[str(chart.chart_id)] = chart
    return chart


@router.get("/{chart_id}", response_model=NatalChart)
def get_chart(chart_id: str, current_user: models.User = Depends(get_current_user)):
    chart = _CHART_STORE.get(chart_id)
    if chart is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบ chart นี้ (อาจถูกล้างไปแล้วเพราะยังไม่ persist ลง DB — ดู docstring ของไฟล์นี้)",
        )
    return chart


class TransitRequest(BaseModel):
    as_of: date


@router.post("/{chart_id}/transits", response_model=NatalChart)
def add_transit(
    chart_id: str,
    payload: TransitRequest,
    current_user: models.User = Depends(get_current_user),
):
    chart = _CHART_STORE.get(chart_id)
    if chart is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบ chart นี้")

    snapshot = build_transit_snapshot(payload.as_of)
    chart.transits.append(snapshot)
    return chart


def get_or_build_chart(chart_id: str | None, current_user: models.User) -> NatalChart:
    """Helper for astrology_query.py: reuse a cached chart if given, else
    build a fresh one from the logged-in user's birth data."""
    if chart_id and chart_id in _CHART_STORE:
        return _CHART_STORE[chart_id]
    chart = build_natal_chart(birth_date=current_user.birth_date, birth_time=current_user.birth_time)
    _CHART_STORE[str(chart.chart_id)] = chart
    return chart
