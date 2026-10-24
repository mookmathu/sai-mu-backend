"""
content_crud.py
----------------
ฟังก์ชันคุยกับ DB สำหรับเนื้อหาแอดมิน (สีมงคลประจำวันตามหลักจีน / สถานที่
สิ่งศักดิ์สิทธิ์) แยกจาก crud.py หลัก (ซึ่งเป็นของ user/auth/chat) ตามแนวทาง
เดียวกับที่แยก content_schemas.py ออกมาแล้ว
"""

from sqlalchemy.orm import Session

from . import models
from .content_schemas import DailyColorChartIn, DeityArticleIn, SacredPlaceIn

# ---------- สีมงคลประจำวัน (หลักจีน) ----------


def list_daily_color_charts(db: Session) -> list[models.DailyColorChart]:
    return (
        db.query(models.DailyColorChart)
        .order_by(
            models.DailyColorChart.year,
            models.DailyColorChart.month,
            models.DailyColorChart.day_of_month,
        )
        .all()
    )


def get_daily_color_chart(db: Session, item_id: int) -> models.DailyColorChart | None:
    return db.get(models.DailyColorChart, item_id)


def get_daily_color_chart_by_date(
    db: Session, year: int, month: int, day: int
) -> models.DailyColorChart | None:
    """ใช้โดยแชท AI (routers/chat.py) เพื่อตอบคำถาม "สีมงคลวันนี้" ด้วยข้อมูลจริง
    แทนที่จะปล่อยให้ตกไปค้นหาแบบ semantic search ทั่วไปใน ChromaDB ซึ่งไม่มี
    ข้อมูลสีมงคลจริงของแต่ละวันอยู่เลย"""
    return (
        db.query(models.DailyColorChart)
        .filter(
            models.DailyColorChart.year == year,
            models.DailyColorChart.month == month,
            models.DailyColorChart.day_of_month == day,
        )
        .first()
    )


def create_daily_color_chart(db: Session, data: DailyColorChartIn) -> models.DailyColorChart:
    item = models.DailyColorChart(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_daily_color_chart(
    db: Session, item: models.DailyColorChart, data: DailyColorChartIn
) -> models.DailyColorChart:
    for field, value in data.model_dump().items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


def delete_daily_color_chart(db: Session, item: models.DailyColorChart) -> None:
    db.delete(item)
    db.commit()


# ---------- สถานที่สิ่งศักดิ์สิทธิ์ ----------


def list_sacred_places(db: Session) -> list[models.SacredPlace]:
    return db.query(models.SacredPlace).order_by(models.SacredPlace.name).all()


def get_sacred_place(db: Session, item_id: int) -> models.SacredPlace | None:
    return db.get(models.SacredPlace, item_id)


def create_sacred_place(db: Session, data: SacredPlaceIn) -> models.SacredPlace:
    item = models.SacredPlace(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_sacred_place(db: Session, item: models.SacredPlace, data: SacredPlaceIn) -> models.SacredPlace:
    for field, value in data.model_dump().items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


def delete_sacred_place(db: Session, item: models.SacredPlace) -> None:
    db.delete(item)
    db.commit()


# ---------- บทความองค์เทพ ----------


def list_deity_articles(db: Session, published_only: bool = False) -> list[models.DeityArticle]:
    q = db.query(models.DeityArticle)
    if published_only:
        q = q.filter(models.DeityArticle.is_published.is_(True))
    return q.order_by(models.DeityArticle.sort_order, models.DeityArticle.id).all()


def get_deity_article(db: Session, item_id: int) -> models.DeityArticle | None:
    return db.get(models.DeityArticle, item_id)


def get_deity_article_by_slug(db: Session, slug: str) -> models.DeityArticle | None:
    return db.query(models.DeityArticle).filter(models.DeityArticle.slug == slug).first()


def create_deity_article(db: Session, data: DeityArticleIn) -> models.DeityArticle:
    item = models.DeityArticle(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_deity_article(db: Session, item: models.DeityArticle, data: DeityArticleIn) -> models.DeityArticle:
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def delete_deity_article(db: Session, item: models.DeityArticle) -> None:
    db.delete(item)
    db.commit()
