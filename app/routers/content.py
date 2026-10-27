"""
routers/content.py
--------------------
Endpoint แบบ "อ่านอย่างเดียว" (read-only) สำหรับให้แอป Flutter (ฝั่งผู้ใช้ทั่วไป)
ดึงข้อมูลสีมงคลประจำวันและสถานที่สิ่งศักดิ์สิทธิ์ไปแสดงผล

แยกออกจาก routers/admin_content.py โดยเจตนา — endpoint ที่นี่ไม่ต้องใช้
X-Admin-Key เลย เพราะเป็นข้อมูลสาธารณะที่ผู้ใช้ทุกคนควรอ่านได้ ในขณะที่
admin_content.py มีไว้ให้เฉพาะเจ้าของแอปกรอก/แก้ไขข้อมูลเท่านั้น (ต้องมี
admin key) — ไม่ฝัง admin key ไว้ในตัวแอปมือถือเด็ดขาด เพราะถอด/ดูโค้ดแอป
แล้วเจอ key ได้ง่าย
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from .. import models
from .. import content_crud
from ..content_schemas import DailyColorChartOut, DeityArticleOut, SacredPlaceOut
from ..database import get_db

router = APIRouter(prefix="/content", tags=["content"])


# ---------- สีมงคลประจำวัน (หลักจีน) ----------


@router.get("/daily-colors", response_model=list[DailyColorChartOut])
def list_daily_colors(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """ไม่ระบุ query param เลย = คืนทั้งหมด, ระบุ year/month = กรองเฉพาะเดือนนั้น
    (หน้าแอปปกติจะเรียกแบบระบุปี/เดือนปัจจุบัน เพื่อโชว์เป็นปฏิทินรายเดือน)"""
    query = db.query(models.DailyColorChart)
    if year is not None:
        query = query.filter(models.DailyColorChart.year == year)
    if month is not None:
        query = query.filter(models.DailyColorChart.month == month)
    return query.order_by(
        models.DailyColorChart.year, models.DailyColorChart.month, models.DailyColorChart.day_of_month
    ).all()


@router.get("/daily-colors/today", response_model=DailyColorChartOut, responses={404: {"description": "ไม่พบข้อมูล"}})
def get_today_daily_color(db: Session = Depends(get_db)):
    """คืนแถวของ "วันนี้" ตามวันที่จริงของเซิร์ฟเวอร์ — สะดวกสำหรับการ์ด
    "สีมงคลวันนี้" หน้าแรกของแอป ถ้ายังไม่มีใครกรอกข้อมูลของเดือนนี้ไว้ คืน 404
    (ฝั่งแอปควรจัดการ กรณีนี้ด้วยข้อความ เช่น "ยังไม่มีข้อมูลเดือนนี้")"""
    today = date.today()
    item = (
        db.query(models.DailyColorChart)
        .filter(
            models.DailyColorChart.year == today.year,
            models.DailyColorChart.month == today.month,
            models.DailyColorChart.day_of_month == today.day,
        )
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="ยังไม่มีข้อมูลสีมงคลของวันนี้")
    return item


# ---------- สถานที่สิ่งศักดิ์สิทธิ์ ----------


@router.get("/sacred-places", response_model=list[SacredPlaceOut])
def list_sacred_places(
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(models.SacredPlace)
    if category is not None:
        query = query.filter(models.SacredPlace.category == category)
    return query.order_by(models.SacredPlace.name).all()


@router.get("/sacred-places/{item_id}", response_model=SacredPlaceOut, responses={404: {"description": "ไม่พบข้อมูล"}})
def get_sacred_place(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.SacredPlace, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="ไม่พบสถานที่นี้")
    return item


# ---------- บทความองค์เทพ (คลังบทความ) ----------


class _PublicArticle(DeityArticleOut):
    """ข้อมูลสำหรับแอป — ไม่ส่ง source_note (ที่มาเก็บไว้ฝั่งแอดมินเท่านั้น)"""

    source_note: str | None = None


@router.get("/articles", response_model=list[_PublicArticle])
def list_articles(db: Session = Depends(get_db)):
    items = content_crud.list_deity_articles(db, published_only=True)
    out = []
    for it in items:
        d = DeityArticleOut.model_validate(it).model_dump()
        d["source_note"] = None
        out.append(d)
    return out


@router.get("/images/{image_id}", responses={404: {"description": "ไม่พบรูป"}})
def get_uploaded_image(image_id: int, db: Session = Depends(get_db)):
    """เสิร์ฟรูปที่แอดมินอัปโหลด — เปิดดูได้โดยไม่ต้อง login เพราะแอปใช้ Image.network"""
    img = db.get(models.UploadedImage, image_id)
    if img is None:
        raise HTTPException(status_code=404, detail="ไม่พบรูป")
    return Response(
        content=img.data,
        media_type=img.content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
