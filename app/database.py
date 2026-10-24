"""
database.py
-----------
ตั้งค่า SQLAlchemy engine + session สำหรับ PostgreSQL (หรือ sqlite ตอน dev)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

# SQLAlchemy รุ่นใหม่บางรุ่นเลือก psycopg (v3) เป็นไดรเวอร์เริ่มต้นเมื่อ URL ขึ้นต้นด้วย postgresql://
# แต่เราติดตั้ง psycopg2 — ระบุไดรเวอร์ให้ชัดเพื่อให้ทำงานเหมือนกันทุกเครื่อง (รวมถึงบน Render)
_db_url = settings.database_url
if _db_url.startswith("postgresql://"):
    _db_url = "postgresql+psycopg2://" + _db_url[len("postgresql://"):]
elif _db_url.startswith("postgres://"):
    _db_url = "postgresql+psycopg2://" + _db_url[len("postgres://"):]

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

# pool_pre_ping=True: เช็คว่า connection ที่หยิบมาจาก pool ยังใช้ได้จริงก่อน
# ใช้งานทุกครั้ง (ยิง SELECT 1 เบาๆ ก่อน) ถ้าตายแล้วจะสร้างใหม่ให้อัตโนมัติ
# — จำเป็นมากกับ Supabase/Postgres แบบ pooled เพราะฝั่งเซิร์ฟเวอร์จะปิด
# connection ที่ไม่ได้ใช้งานนานๆ เอง (ทำให้เจอ "server closed the connection
# unexpectedly" ถ้าไม่เช็คก่อน) pool_recycle=300 รีไซเคิล connection ที่เก่า
# เกิน 5 นาทีทิ้งเชิงป้องกันไว้อีกชั้น ไม่มีผลกับ sqlite (ไม่ใช้ pool แบบนี้)
engine_kwargs = {"connect_args": connect_args}
if not settings.database_url.startswith("sqlite"):
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(_db_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — เปิด session ต่อ request แล้วปิดให้อัตโนมัติ"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
