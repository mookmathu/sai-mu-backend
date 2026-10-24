"""คำนวณราศี/ปีนักษัตรใหม่ให้ทุกบัญชี ด้วยสูตรสุริยยาตร์ปัจจุบัน

รันจากโฟลเดอร์ backend:
    python -m scripts.recalc_zodiac            # ดูก่อน (ไม่แก้ฐานข้อมูล)
    python -m scripts.recalc_zodiac --apply    # แก้จริง
"""
import sys

from app import models, zodiac
from app.database import SessionLocal


def main(apply: bool) -> None:
    db = SessionLocal()
    changed = 0
    try:
        for p in db.query(models.UserAstroProfile).all():
            u = p.user
            t = u.birth_time
            frac = (t.hour + t.minute / 60) / 24 if t else zodiac.DEFAULT_TIME_FRAC
            sign = zodiac.calculate_zodiac_sign(u.birth_date, frac)
            animal = zodiac.calculate_zodiac_animal(u.birth_date)
            if (sign, animal) != (p.zodiac_sign, p.zodiac_animal):
                print(f"{u.email}: {p.zodiac_sign}/{p.zodiac_animal} -> {sign}/{animal}")
                p.zodiac_sign, p.zodiac_animal = sign, animal
                changed += 1
        if apply:
            db.commit()
            print(f"แก้แล้ว {changed} บัญชี")
        else:
            db.rollback()
            print(f"จะแก้ {changed} บัญชี (ยังไม่ได้แก้ — ใส่ --apply เพื่อแก้จริง)")
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
