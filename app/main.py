"""
main.py
-------
รันด้วย: uvicorn app.main:app --reload
เปิดเอกสาร API ทดสอบได้ที่ http://localhost:8000/docs
"""

from dotenv import load_dotenv

# โหลดค่าจาก .env เข้า os.environ ให้ก่อนอย่างอื่นทั้งหมด (สำคัญ: ต้องมาก่อน
# import ตัวอื่นที่อ่าน os.environ ตอน import เช่น app.rag ที่อ่าน
# GEMINI_API_KEY) ไม่ต้องมานั่ง export/$env: เองใน terminal ทุกครั้งอีกแล้ว
load_dotenv()

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import avatars, models, startup_checks
from .config import settings
from .api import astrology_query, charts
from .database import Base, engine
from .routers import admin_content, auth, chat, content, daily, history, name_numerology

# ตรวจค่าตั้งก่อนเริ่มทำงาน: dev = เตือน, ENVIRONMENT=production = ค่าไม่ปลอดภัยจะไม่ยอมสตาร์ท
startup_checks.run(settings)

# สร้างตารางอัตโนมัติถ้ายังไม่มี (สำหรับ dev — โปรดักชันแนะนำใช้ alembic migration แทน)
Base.metadata.create_all(bind=engine)


_VARCHAR_255 = "VARCHAR(255)"


def _ensure_sacred_place_columns() -> None:
    """create_all ไม่เพิ่มคอลัมน์ให้ตารางเดิม — เติมคอลัมน์รายละเอียดสถานที่ (ต.ค. 2026) ให้อัตโนมัติ
    รันซ้ำได้ ถ้ามีอยู่แล้วจะข้าม (ไฟล์ SQL เทียบเท่าอยู่ที่ docs/migrations/2026-10-22_sacred_place_details.sql)"""
    from sqlalchemy import inspect, text

    cols = {
        "travel_info": "TEXT",
        "worship_steps": "TEXT",
        "offerings": "TEXT",
        "etiquette": "TEXT",
        "opening_hours": _VARCHAR_255,
        "best_time": _VARCHAR_255,
        "wish_tags": _VARCHAR_255,
        "chants": "TEXT",
    }
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("sacred_places")}
        with engine.begin() as conn:
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE sacred_places ADD COLUMN {name} {ddl}"))
    except Exception as e:  # noqa: BLE001 — ไม่ให้เซิร์ฟเวอร์ล้มเพราะขั้นตอนนี้ (รัน SQL ใน docs/migrations เองได้)
        print(f"[warn] เพิ่มคอลัมน์ sacred_places ไม่สำเร็จ: {e}")


_ensure_sacred_place_columns()

app = FastAPI(title="Sai Mu / Mutelove API")

# จำเป็นเมื่อรัน Flutter บนเว็บ (Chrome) — เบราว์เซอร์บล็อก request ข้าม origin
# โดยดีฟอลต์ ถ้าไม่เปิด CORS ตรงนี้ ฝั่ง Flutter web จะเจอ error แบบ
# "Failed to fetch" แม้ backend จะรันอยู่และ URL ถูกต้องแล้วก็ตาม
# allow_origins=["*"] สะดวกตอน dev — ก่อนขึ้นโปรดักชันจริงควรระบุโดเมนจริง
# ของแอปแทน (เช่น ["https://mutelove.app"]) ไม่ใช้ "*" ตอน production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(charts.router)
app.include_router(astrology_query.router)
app.include_router(admin_content.router)
app.include_router(content.router)
app.include_router(daily.router)
app.include_router(history.router)
app.include_router(name_numerology.router)

# หน้าเว็บแอดมิน (จัดการเสื้อสีมงคล/สถานที่สิ่งศักดิ์สิทธิ์) — เป็นไฟล์ HTML/JS/CSS
# ธรรมดา ไม่มีขั้นตอน build ใดๆ เข้าถึงได้ที่ /admin/ เมื่อรัน backend อยู่
# (เช่น http://localhost:8000/admin/) ต้องกรอก Admin Key ในหน้านั้นให้ตรงกับ
# ADMIN_API_KEY ที่ตั้งไว้ใน .env ก่อนถึงจะเรียก API ผ่านได้
_admin_static_dir = Path(__file__).parent / "static" / "admin"
app.mount("/admin", StaticFiles(directory=_admin_static_dir, html=True), name="admin-ui")


# รูปโปรไฟล์ผู้ใช้ (app/avatars.py) — เปิดดูได้โดยไม่ต้อง login เพราะ Image.network
# ฝั่งแอปไม่แนบ token; ชื่อไฟล์เดายาก (id-เวลา) และเป็นรูปโปรไฟล์ซึ่งตั้งใจให้แสดงอยู่แล้ว
avatars.AVATAR_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/avatars", StaticFiles(directory=avatars.AVATAR_DIR), name="avatars")


@app.get("/health")
def health_check():
    return {"status": "ok"}
