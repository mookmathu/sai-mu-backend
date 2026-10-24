"""
routers/history.py
------------------
GET    /history              รายการประวัติคำทำนายของผู้ใช้ (กรองหมวด/บันทึกไว้/ค้นหา/เรียง/แบ่งหน้า)
PATCH  /history/{id}/saved   กดบันทึก/ยกเลิกบันทึก (ซิงก์ข้ามเครื่อง)
DELETE /history/{id}         ลบ 1 รายการ
DELETE /history              ล้างประวัติ (ไม่แตะรายการที่บันทึกไว้ ถ้าส่ง ?keep_saved=true)
ทุก endpoint เห็นเฉพาะรายการของผู้ใช้ที่ login อยู่เท่านั้น
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import history as history_service
from .. import models
from ..database import get_db
from ..schemas import HistoryEntryOut, HistoryListOut, HistorySavedRequest
from .auth import get_current_user

router = APIRouter(prefix="/history", tags=["history"])


def _own(db: Session, user, entry_id: int) -> models.HistoryEntry:
    entry = (
        db.query(models.HistoryEntry)
        .filter(models.HistoryEntry.id == entry_id, models.HistoryEntry.user_id == user.id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการนี้")
    return entry


@router.get("", response_model=HistoryListOut)
def list_history(
    category: Literal["daily", "zodiac", "numerology", "color", "general"] | None = None,
    saved: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    sort: Literal["new", "old"] = "new",
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.HistoryEntry).filter(models.HistoryEntry.user_id == current_user.id)
    if category:
        query = query.filter(models.HistoryEntry.category == category)
    if saved is not None:
        query = query.filter(models.HistoryEntry.is_saved.is_(saved))
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(models.HistoryEntry.title.ilike(like), models.HistoryEntry.content.ilike(like)))
    total = query.count()
    order = models.HistoryEntry.created_at.desc() if sort == "new" else models.HistoryEntry.created_at.asc()
    items = query.order_by(order, models.HistoryEntry.id.desc()).offset(offset).limit(limit).all()
    return HistoryListOut(items=[HistoryEntryOut.model_validate(i) for i in items], total=total)


@router.patch("/{entry_id}/saved", response_model=HistoryEntryOut)
def set_saved(entry_id: int, body: HistorySavedRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    entry = _own(db, current_user, entry_id)
    entry.is_saved = body.saved
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, current_user, entry_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(keep_saved: bool = False, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(models.HistoryEntry).filter(models.HistoryEntry.user_id == current_user.id)
    if keep_saved:
        query = query.filter(models.HistoryEntry.is_saved.is_(False))
    query.delete(synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
