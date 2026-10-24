"""
routers/name_numerology.py
--------------------------
POST /numerology/name — โหราเลขศาสตร์ชื่อ (ตารางมหามงคล) ดู app/name_numerology.py
ไม่เก็บชื่อที่ส่งมา คำนวณแล้วตอบกลับเลย
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import birth_match, history, name_numerology, number_luck
from ..database import get_db
from .. import taksa
from .auth import get_current_user, get_optional_user

router = APIRouter(prefix="/numerology", tags=["numerology"])


class NameRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(default="", max_length=60)
    gender: Literal["male", "female"] | None = None


class DigitProfileOut(BaseModel):
    number: int
    role: str
    planet: str
    element: str = ""
    personality: str = ""
    strengths: str = ""
    cautions: str = ""
    fits: str = ""
    good_colors: str = ""
    bad_colors: str = ""
    gem: str = ""
    friends: str = ""
    enemies: str = ""


class MeaningOut(BaseModel):
    number: int
    from_total: int
    title: str
    overview: str
    strengths: str
    cautions: str
    careers: str = ""
    extra: str = ""
    profiles: list[DigitProfileOut] = []


class PartOut(BaseModel):
    text: str
    total: int
    weight: int
    tags: list[str]
    reverse_total: int
    reverse_tags: list[str]
    notes: list[str]
    meaning: MeaningOut | None = None


class BirthMatchOut(BaseModel):
    birth_day_name: str
    birth_number: int
    birth_planet: str
    name_number: int
    name_planet: str
    relation: Literal["same", "friend", "enemy", "neutral"]
    headline: str
    text: str


class NameOut(BaseModel):
    first: PartOut
    last: PartOut
    full: PartOut
    personal: BirthMatchOut | None = None  # เทียบกับวันเกิดผู้ใช้ (เฉพาะที่ login และมีวันเกิด)
    source: str


@router.post("/name", response_model=NameOut, responses={400: {"description": "ข้อมูลที่ส่งมาไม่ถูกต้อง"}})
def analyze_name(body: NameRequest, user=Depends(get_optional_user), db: Session = Depends(get_db)):
    try:
        result = name_numerology.analyze_name(body.first_name, body.last_name, body.gender)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if user is not None:  # login อยู่ -> บันทึกลงหน้าประวัติให้ (ไม่ login ก็ใช้ได้ แค่ไม่บันทึก)
        history.record_name(db, user.id, result, body.gender)
        result["personal"] = birth_match.match_with_birth(result["full"]["total"], getattr(user, "birth_date", None))
    return result


class NumberRequest(BaseModel):
    text: str = Field(min_length=1, max_length=40)


class LetterOut(BaseModel):
    char: str
    value: int


class NumberOut(BaseModel):
    input: str
    digit_sum: int
    letters: list[LetterOut]
    letter_sum: int
    total: int
    level: Literal["great", "fair", "poor", "unknown"]
    note: str
    meaning: MeaningOut | None = None
    personal: BirthMatchOut | None = None
    source: str


@router.post("/number", response_model=NumberOut, responses={400: {"description": "ข้อมูลที่ส่งมาไม่ถูกต้อง"}})
def analyze_number(body: NumberRequest, user=Depends(get_optional_user), db: Session = Depends(get_db)):
    """เบอร์โทร / ทะเบียนรถ เช่น 0812345678 หรือ 5กก-1555"""
    try:
        result = number_luck.analyze_number(body.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if user is not None:
        history.record_number(db, user.id, result)
        result["personal"] = birth_match.match_with_birth(result["total"], getattr(user, "birth_date", None))
    return result



class LetterCategoryOut(BaseModel):
    name: str
    meaning: str
    letters: list[str]
    avoid: bool


class NameLettersOut(BaseModel):
    day_name: str
    categories: list[LetterCategoryOut]
    note: str


@router.get("/name-letters", response_model=NameLettersOut)
def name_letters(user=Depends(get_current_user)):
    """อักษรต้นชื่อ 8 หมวดตามทักษา ของวันเกิดผู้ใช้ (ต้อง login) — ใช้ประกอบการตั้งชื่อ"""
    data = taksa.suggest_first_letters(user.birth_date)
    data["note"] = (
        "ตำรากำหนดเพียงว่าอักษรต้นชื่อควรเลี่ยงหมวดกาลกิณี ส่วนหมวดอื่นเลือกตามเรื่องที่อยากเสริม "
        "เป็นความเชื่อตามตำรา ไม่ใช่การกำหนดชะตา"
    )
    return data
