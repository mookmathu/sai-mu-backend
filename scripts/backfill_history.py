"""
ย้ายแชทเดิมใน chat_messages เข้าตาราง history_entries (รันครั้งเดียวหลังอัปเดต ทำซ้ำได้ปลอดภัย)

    python -m scripts.backfill_history
"""
from app.database import SessionLocal
from app.history import backfill_from_chat


def main() -> None:
    db = SessionLocal()
    try:
        print(f"ย้ายเข้าประวัติแล้ว {backfill_from_chat(db)} รายการ")
    finally:
        db.close()


if __name__ == "__main__":
    main()
