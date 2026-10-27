"""
routers/admin_content.py
-------------------------
CRUD API สำหรับเนื้อหาที่จัดการผ่านหน้าเว็บแอดมิน (static/admin/index.html):
- /admin/content/daily-colors    สีมงคลประจำวันตามหลักจีน (ผูกกับปี/เดือน/วันที่จริง)
- /admin/content/sacred-places   สถานที่สิ่งศักดิ์สิทธิ์
- /admin/content/articles        บทความองค์เทพในคลังบทความ

ป้องกันด้วย header "X-Admin-Key" เทียบกับ settings.admin_api_key (ตั้งค่าใน .env)
เลือกวิธีนี้แทนระบบ login/role เต็มรูปแบบเพราะตอนนี้มีแค่เจ้าของแอปคนเดียวที่ต้อง
เข้าถึง — ถ้าในอนาคตมีทีมงานหลายคนต้องเข้าใช้ ค่อยเปลี่ยนไปทำระบบ role จริงทีหลัง
"""

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .. import content_crud as crud
from .. import models
from ..avatars import _detect_extension
from ..config import settings
from ..content_schemas import (
    DailyColorChartIn,
    DailyColorChartOut,
    DeityArticleIn,
    DeityArticleOut,
    SacredPlaceIn,
    SacredPlaceOut,
)
from ..database import get_db


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """เทียบ header X-Admin-Key กับค่าใน .env — ไม่ตรง/ไม่ส่งมาก็ 401 ทันที
    ใช้เป็น dependency ระดับ router เลย ไม่ต้องแปะซ้ำทุก endpoint"""
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key ไม่ถูกต้อง")


_MSG_ITEM_NOT_FOUND = "ไม่พบรายการนี้"
_MSG_NOT_FOUND = "ไม่พบข้อมูล"

router = APIRouter(
    prefix="/admin/content",
    tags=["admin-content"],
    dependencies=[Depends(require_admin_key)],
)


# ---------- สีมงคลประจำวัน (หลักจีน) ----------


@router.get("/daily-colors", response_model=list[DailyColorChartOut])
def list_daily_colors(db: Session = Depends(get_db)):
    return crud.list_daily_color_charts(db)


@router.post("/daily-colors", response_model=DailyColorChartOut, status_code=status.HTTP_201_CREATED)
def create_daily_color(data: DailyColorChartIn, db: Session = Depends(get_db)):
    return crud.create_daily_color_chart(db, data)


@router.put("/daily-colors/{item_id}", response_model=DailyColorChartOut, responses={404: {"description": _MSG_NOT_FOUND}})
def update_daily_color(item_id: int, data: DailyColorChartIn, db: Session = Depends(get_db)):
    item = crud.get_daily_color_chart(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=_MSG_ITEM_NOT_FOUND)
    return crud.update_daily_color_chart(db, item, data)


@router.delete("/daily-colors/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"description": _MSG_NOT_FOUND}})
def delete_daily_color(item_id: int, db: Session = Depends(get_db)):
    item = crud.get_daily_color_chart(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=_MSG_ITEM_NOT_FOUND)
    crud.delete_daily_color_chart(db, item)


# ---------- สถานที่สิ่งศักดิ์สิทธิ์ ----------


@router.get("/sacred-places", response_model=list[SacredPlaceOut])
def list_sacred_places(db: Session = Depends(get_db)):
    return crud.list_sacred_places(db)


@router.post("/sacred-places", response_model=SacredPlaceOut, status_code=status.HTTP_201_CREATED)
def create_sacred_place(data: SacredPlaceIn, db: Session = Depends(get_db)):
    return crud.create_sacred_place(db, data)


@router.put("/sacred-places/{item_id}", response_model=SacredPlaceOut, responses={404: {"description": _MSG_NOT_FOUND}})
def update_sacred_place(item_id: int, data: SacredPlaceIn, db: Session = Depends(get_db)):
    item = crud.get_sacred_place(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=_MSG_ITEM_NOT_FOUND)
    return crud.update_sacred_place(db, item, data)


@router.delete("/sacred-places/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"description": _MSG_NOT_FOUND}})
def delete_sacred_place(item_id: int, db: Session = Depends(get_db)):
    item = crud.get_sacred_place(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=_MSG_ITEM_NOT_FOUND)
    crud.delete_sacred_place(db, item)


# ---------- บทความองค์เทพ (คลังบทความ) ----------


@router.get("/articles", response_model=list[DeityArticleOut])
def list_articles(db: Session = Depends(get_db)):
    return crud.list_deity_articles(db)


@router.post("/articles", response_model=DeityArticleOut, status_code=status.HTTP_201_CREATED, responses={409: {"description": "ข้อมูลซ้ำหรือขัดแย้งกับที่มีอยู่"}})
def create_article(data: DeityArticleIn, db: Session = Depends(get_db)):
    if crud.get_deity_article_by_slug(db, data.slug) is not None:
        raise HTTPException(status_code=409, detail="รหัสบทความ (slug) นี้มีอยู่แล้ว")
    return crud.create_deity_article(db, data)


@router.put("/articles/{item_id}", response_model=DeityArticleOut, responses={404: {"description": _MSG_NOT_FOUND}, 409: {"description": "ข้อมูลซ้ำหรือขัดแย้งกับที่มีอยู่"}})
def update_article(item_id: int, data: DeityArticleIn, db: Session = Depends(get_db)):
    item = crud.get_deity_article(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=_MSG_ITEM_NOT_FOUND)
    other = crud.get_deity_article_by_slug(db, data.slug)
    if other is not None and other.id != item.id:
        raise HTTPException(status_code=409, detail="รหัสบทความ (slug) นี้มีอยู่แล้ว")
    return crud.update_deity_article(db, item, data)


@router.delete("/articles/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"description": _MSG_NOT_FOUND}})
def delete_article(item_id: int, db: Session = Depends(get_db)):
    item = crud.get_deity_article(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=_MSG_ITEM_NOT_FOUND)
    crud.delete_deity_article(db, item)


# ---------- อัปโหลดรูป (รูปบทความ / รูปสัญลักษณ์) ----------

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB
_IMAGE_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


@router.post(
    "/images",
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "ไฟล์ไม่ใช่รูปที่รองรับ"}, 413: {"description": "รูปใหญ่เกินไป"}},
)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """รับไฟล์รูป เก็บลงฐานข้อมูล แล้วคืน path สำหรับเสิร์ฟ (/content/images/<id>)"""
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="ไม่พบไฟล์รูป")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="รูปใหญ่เกินไป (สูงสุด 2 MB)")
    ext = _detect_extension(data)  # ดูจาก magic bytes ไม่เชื่อ Content-Type ที่ส่งมา
    if ext is None:
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์รูป JPG, PNG หรือ WEBP")
    img = models.UploadedImage(content_type=_IMAGE_TYPES[ext], data=data)
    db.add(img)
    db.commit()
    db.refresh(img)
    return {"id": img.id, "path": f"/content/images/{img.id}"}
