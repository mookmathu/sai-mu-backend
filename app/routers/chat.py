"""
routers/chat.py
-----------------
POST   /chat          — ส่งข้อความ ได้คำตอบกลับ (บันทึกทั้งคู่ลง DB อัตโนมัติ)
GET    /chat/history   — ดึงประวัติสนทนาทั้งหมดของผู้ใช้ปัจจุบัน (โหลดตอนเปิดหน้าแชท)
DELETE /chat/history   — ล้างประวัติสนทนาทั้งหมดทิ้ง (เผื่ออยากเริ่มคุยใหม่)

รับคำถาม -> ค้นหาความรู้ที่เกี่ยวข้องจาก ChromaDB -> ให้ Gemini ตอบ -> คืนคำตอบ
พร้อมแหล่งอ้างอิงที่ใช้ -> บันทึกทั้งข้อความผู้ใช้และคำตอบลง DB

ต้อง login ก่อนถึงจะแชทได้ (ใช้ token เดียวกับที่ได้จาก /auth/login หรือ
/auth/register) — สอดคล้องกับ flow ของแอปที่ต้อง login ก่อนถึงจะเข้าหน้า
Home/Chat ได้อยู่แล้ว
"""

import json
import logging
import time
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from google.genai import errors as genai_errors
from sqlalchemy.orm import Session

from .. import car_color as car_guide, content_crud, crud, daily_fortune, history, models, number_luck, numerology, transit
from ..database import SessionLocal, get_db
from .. import name_suggest, taksa
from ..rag.gemini_client import QuotaExhaustedError, cache_lookup_allowed, conversation_history, usage_guard
from ..rag.rag_service import (
    NumerologyRAG,
    extract_named_zodiac_sign,
    is_ambiguous_fortune_question,
    is_car_color_question,
    is_daily_color_question,
    is_daily_lucky_number_question,
    is_follow_up_question,
    OWN_TOPIC_WORDS,
    is_daily_horoscope_question,
    is_today_report_question,
    is_current_topic_question,
    is_generic_zodiac_question,
)
from ..usage_limit import LIMIT_REACHED_MESSAGE, DailyLimitExceeded, UsageGuard
from ..schemas import ChatHistoryResponse, ChatMessageOut, ChatRequest, ChatResponse, ChatSource
from .auth import get_current_user

_log = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="", tags=["chat"])

# สร้าง NumerologyRAG แค่ครั้งเดียวตอนเรียกใช้ครั้งแรก (lazy singleton) เพราะ
# การสร้างมันโหลด ChromaDB + สร้าง Gemini client ซึ่งมีต้นทุนพอสมควร ไม่อยาก
# ทำซ้ำทุก request — ตัวแปร module-level นี้ปลอดภัยเพราะ FastAPI (ผ่าน
# uvicorn --workers 1 ตอน dev) รันใน process เดียว ถ้าจะ scale เป็นหลาย
# worker/process ทีหลัง ให้ย้ายไปใช้ dependency injection แบบ app.state แทน
_rag_instance: NumerologyRAG | None = None


def _get_rag() -> NumerologyRAG:
    global _rag_instance
    if _rag_instance is None:
        try:
            _rag_instance = NumerologyRAG()
        except FileNotFoundError as e:
            # ChromaDB ยังไม่เคย ingest — แจ้งให้ชัดว่าต้องทำอะไรก่อน แทนที่
            # จะโยน error ดิบๆ ที่เข้าใจยาก
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "ระบบแชทยังไม่พร้อมใช้งาน — ยังไม่ได้ ingest ข้อมูลเข้า ChromaDB "
                    "กรุณารัน `python -m app.rag.ingest` บนเซิร์ฟเวอร์ก่อน"
                ),
            ) from e
    return _rag_instance


_MARKET_WORDS = ("หุ้น", "คริปโต", "บิตคอยน์", "bitcoin", "btc", "ราคาทอง", "ค่าเงิน", "ตลาดหลักทรัพย์", "set index", "กองทุน", "forex", "ฟอเร็กซ์")
_MARKET_ACTION_WORDS = ("ขึ้น", "ลง", "ซื้อ", "ขาย", "ลงทุน", "เข้า", "ออก", "ร่วง", "พุ่ง", "กำไร", "ขาดทุน", "ดีไหม", "ตัวไหน", "ไหม")

MARKET_PREDICTION_MESSAGE = (
    "เรื่องราคาหุ้นหรือการลงทุน ดวงบอกไม่ได้ว่าขึ้นหรือลง และไม่ควรใช้ดวงตัดสินใจซื้อขาย\n\n"
    "แต่ถ้าอยากรู้ดวงการเงินของตัวเองวันนี้ ลองถามว่า \"ดวงการเงินวันนี้เป็นยังไง\" ได้เลย"
)


def _is_market_prediction(message: str) -> bool:
    """ถามทำนายราคาตลาด/การลงทุน (หุ้น คริปโต ทอง ฯลฯ) — ดวงตอบไม่ได้ จึงตอบข้อความคงที่ ไม่เรียก AI"""
    m = (message or "").lower()
    return any(w in m for w in _MARKET_WORDS) and any(w in m for w in _MARKET_ACTION_WORDS)


def _detect_topic(message: str):
    """หัวข้อชีวิตของคำถามดวง (ภพที่เกี่ยวข้อง) — ข้ามถ้าเป็นการถามหาวัด/ศาล/สถานที่ไหว้ขอพร
    (เช่น "วัดไหนเหมาะขอพรเรื่องการงาน" ไม่ใช่ดวงหัวข้อการงาน)"""
    topic = transit.detect_topic_house(message)
    if topic and any(w in message for w in ("วัด", "ศาล", "สถานที่")):
        return None
    return topic


@router.post("/chat", response_model=ChatResponse)
def chat(
    data: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t0 = time.perf_counter()
    rag = _get_rag()

    # เช็คเจตนาของคำถามเรียงตามลำดับความเฉพาะเจาะจง แล้วเลือกทางตอบที่ "คำนวณจริง
    # เฉพาะบุคคล" แทนการค้นหาแบบ semantic search ทั่วไปเมื่อทำได้ — ถ้าไม่มีข้อมูลที่
    # จำเป็น (เช่น ไม่มี astro_profile ซึ่งไม่ควรเกิดขึ้นในทางปฏิบัติ เพราะสมัครสมาชิก
    # บังคับกรอกวันเกิดอยู่แล้ว) ก็ตกไปตอบแบบทั่วไปแทน ไม่ error
    zodiac_sign = current_user.astro_profile.zodiac_sign if current_user.astro_profile else None
    named_rasi = extract_named_zodiac_sign(data.message)
    name_to_check = taksa.extract_name_to_check(data.message)

    if _is_market_prediction(data.message):
        return ChatResponse(answer=MARKET_PREDICTION_MESSAGE, sources=[])

    topic_match = _detect_topic(data.message)

    # เบอร์โทรที่กรอกมาไม่ครบ 10 หลัก: เตือนทันที ไม่เรียก AI และไม่นับโควตา
    phone_warning = numerology.phone_digit_warning(data.message)
    if phone_warning:
        return ChatResponse(answer=phone_warning, sources=[])

    phone_or_plate_digits = None
    if numerology.is_phone_or_plate_question(data.message):
        phone_or_plate_digits = numerology.extract_phone_or_plate_query(data.message)

    # เบอร์/ทะเบียนที่ผู้ใช้ "ระบุชัด" (มีคำว่า เบอร์/ทะเบียน/ป้าย ฯลฯ) ต้องชนะหัวข้อชีวิต เช่น
    # "เบอร์ 0623941583 เรื่องความรักดีไหม" ไม่งั้นจะหลุดไปตอบดวงจันทร์เรื่องความรักทั่วไปแทน
    number_text = None
    if any(kw in data.message for kw in numerology.PHONE_OR_PLATE_KEYWORDS):
        number_text = number_luck.extract_plate(data.message) or phone_or_plate_digits
    car_color = number_luck.extract_car_color(data.message) if number_text else None

    # ประวัติการคุย: แนบคู่ถาม-ตอบล่าสุด (สูงสุด 3 คู่ ไม่เกิน 60 นาที) ให้ Gemini ทุกครั้ง แล้วให้
    # โมเดลตัดสินเองว่าคำถามใหม่ต่อเนื่องหรือเปลี่ยนเรื่อง (เหมือนคุยกับ AI ทั่วไป)
    recent = crud.get_recent_exchanges(db, current_user.id)
    conversation_history.set(recent)

    # ส่วนที่ต้องตัดสินด้วยกฎ: ถ้าเป็นคำถามสั้นๆ ต่อเนื่อง และเรื่องก่อนหน้าเป็นทะเบียน/เบอร์ ให้ตอบต่อ
    # ในกรอบเลขศาสตร์ของทะเบียนนั้น (เว้นแต่ข้อความใหม่มีคำของหัวข้ออื่นชัดเจน เช่น "ดวง" "วันนี้")
    follow_up_of = recent[-1] if recent and is_follow_up_question(data.message) else None
    if follow_up_of and not number_text and not any(w in data.message for w in OWN_TOPIC_WORDS):
        prev_q = follow_up_of[0]
        prev_number = number_luck.extract_plate(prev_q) or (
            numerology.extract_phone_or_plate_query(prev_q)
            if numerology.is_phone_or_plate_question(prev_q)
            else None
        )
        if prev_number and any(kw in prev_q for kw in numerology.PHONE_OR_PLATE_KEYWORDS):
            number_text = prev_number
            car_color = number_luck.extract_car_color(data.message) or number_luck.extract_car_color(prev_q)

    _log.info(
        "chat route: history_pairs=%d follow_up=%s number_text=%s car_color=%s",
        len(recent), bool(follow_up_of), number_text, car_color,
    )

    # จำกัดจำนวนข้อความที่ต้องเรียก Gemini จริงต่อคนต่อวัน (แคชไม่นับ) — ครบแล้วตอบข้อความเป็นมิตรทันที
    # โดยยังไม่ต้องเสียโควตา embedding/Gemini ของส่วนกลางเพิ่ม
    guard = UsageGuard(current_user.id)
    usage_guard.set(guard)
    # คำถามต่อเนื่องต้องอิงบทสนทนาของคนนั้น จึงไม่อ่านจากแคชคำตอบที่ใช้ร่วมกัน
    cache_lookup_allowed.set(follow_up_of is None)
    if guard.exhausted():
        return ChatResponse(answer=LIMIT_REACHED_MESSAGE, sources=[])

    try:
        result = _dispatch_to_rag(
            rag, data, current_user, zodiac_sign, named_rasi, name_to_check, topic_match,
            phone_or_plate_digits, db, number_text=number_text, car_color=car_color,
            follow_up_of=follow_up_of,
        )
    except DailyLimitExceeded:
        return ChatResponse(answer=LIMIT_REACHED_MESSAGE, sources=[])
    except QuotaExhaustedError as e:
        # โควตารายวันของ Gemini API หมด — retry ไม่ช่วย ต้องรอ reset หรือเปิด billing
        # แจ้งผู้ใช้ตรงๆ แทนที่จะปล่อยให้ crash เป็น 500 ดิบๆ
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="ระบบแชทใช้งานเกินโควตาประจำวันแล้ว กรุณาลองใหม่พรุ่งนี้ หรือติดต่อผู้ดูแลระบบ",
        ) from e
    except (genai_errors.ServerError, genai_errors.ClientError) as e:
        # ครอบคลุมทั้ง 503 (Gemini โหลดสูงชั่วคราว, เช่น "high demand") และ 429
        # (rate limit ต่อนาที) ที่ retry ในตัว gemini_client.py ลองแล้วแต่ยังไม่สำเร็จ
        # ให้ตอบเป็นข้อความสุภาพที่ฝั่ง Flutter เอาไปแสดงได้เลย แทนที่จะโชว์
        # traceback ดิบๆ ให้ผู้ใช้เห็น
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ขณะนี้ระบบ AI มีผู้ใช้งานหนาแน่น กรุณาลองใหม่อีกครั้งในอีกสักครู่",
        ) from e

    t1 = time.perf_counter()
    sources = [ChatSource(**s) for s in result["sources"]]

    # บันทึกลง DB "หลังส่งคำตอบกลับไปแล้ว" (background) — การเขียน 3 รายการไปที่ Supabase
    # ใช้เวลารวมราว 1.5–2 วินาที ไม่ควรให้ผู้ใช้ต้องรอ ถ้าเรียก rag.ask() error ก่อนถึงตรงนี้
    # จะไม่มีการบันทึก (ไม่มีข้อความค้างครึ่งๆ กลางๆ)
    background_tasks.add_task(
        _persist_chat,
        current_user.id, data.message, result["answer"], sources,
        "numerology" if number_text else None,
    )

    t2 = time.perf_counter()
    _log.info("chat timing: rag+gemini=%.2fs enqueue=%.2fs total=%.2fs", t1 - t0, t2 - t1, t2 - t0)
    answer_out = result["answer"]
    notice = guard.low_remaining_notice()  # เหลือไม่กี่ข้อความ → เตือนล่วงหน้า (ไม่บันทึกลงประวัติ)
    if notice:
        answer_out = f"{answer_out}\n\n{notice}"
    return ChatResponse(answer=answer_out, sources=sources)


def _persist_chat(user_id: int, question: str, answer: str, sources, category) -> None:
    """บันทึกแชท + ประวัติ ด้วย session ของตัวเอง (session ของ request ถูกปิดไปแล้วตอนนี้)

    - ข้อความผู้ใช้ + คำตอบ บันทึกใน transaction เดียว (commit ครั้งเดียว): สำเร็จทั้งคู่หรือไม่ลงเลย
      ไม่เกิดกรณีมีแต่คำถามไม่มีคำตอบ และเร็วกว่าแยก commit
    - ถ้าพลาด (เช่น Supabase ตัดการเชื่อมต่อ) ลองใหม่อีก 2 ครั้งด้วย session ใหม่
    """
    t = time.perf_counter()
    saved = False
    for attempt in range(3):
        db = SessionLocal()
        try:
            db.add(models.ChatMessage(user_id=user_id, role="user", content=question))
            db.flush()  # ให้คำถามได้ id ก่อนคำตอบเสมอ
            db.add(models.ChatMessage(
                user_id=user_id, role="assistant", content=answer,
                sources=json.dumps([s.model_dump() for s in sources], ensure_ascii=False) if sources else None,
            ))
            db.commit()
            saved = True
            break
        except Exception:  # noqa: BLE001 — ห้ามให้ error ตรงนี้กระทบคำตอบที่ส่งไปแล้ว
            db.rollback()
            _log.warning("บันทึกแชทไม่สำเร็จ (ครั้งที่ %d/3)", attempt + 1, exc_info=True)
            time.sleep(0.5 * (attempt + 1))
        finally:
            db.close()
    if not saved:
        _log.error("บันทึกแชทลงฐานข้อมูลไม่สำเร็จหลังลองครบ 3 ครั้ง user_id=%s", user_id)

    # ลงหน้า "ประวัติ" ด้วย (แยกจาก chat_messages — กดเริ่มแชทใหม่แล้วประวัติยังอยู่)
    # history.record_chat จัดการ error ของตัวเองอยู่แล้ว
    db = SessionLocal()
    try:
        history.record_chat(db, user_id, question, answer, category=category)
    finally:
        db.close()
    _log.info("chat persisted in background: %.2fs (saved=%s)", time.perf_counter() - t, saved)


def _dispatch_to_rag(
    rag, data, current_user, zodiac_sign, named_rasi, name_to_check, topic_match,
    phone_or_plate_digits, db, number_text=None, car_color=None, follow_up_of=None,
):
    """แยกลอจิกเลือกทางตอบทั้งหมดออกมาเป็นฟังก์ชันย่อย เพื่อให้ครอบด้วย try/except
    เดียวใน chat() ได้สะดวก (ทุกทางตอบในนี้เรียก Gemini API ในที่สุด ซึ่งอาจโดน
    503/429 จากฝั่ง Google ได้เหมือนกันหมด ไม่อยากดักแยกทีละ branch)"""
    # ตำราสีรถตามวันเกิด — ใช้ทั้งตอบ "สีรถ" ตรงๆ และตอนถามต่อเรื่องสีหลังคุยเรื่องทะเบียน
    car_facts = None
    asked_color = car_color or number_luck.extract_car_color(data.message)
    if current_user.birth_date and (is_car_color_question(data.message) or (number_text and ("สี" in data.message or asked_color))):
        day_key = car_guide.astro_day_key(current_user.birth_date, getattr(current_user, "birth_time", None))
        car_facts = car_guide.facts_text(day_key, asked_color, current_user.birth_date)

    if number_text:
        birth = current_user.birth_date
        weekday_color = weekday_name = None
        if birth:
            weekday_color = daily_fortune.WEEKDAY_COLORS[birth.weekday()]
            weekday_name = daily_fortune.WEEKDAY_NAMES[birth.weekday()]
        result = rag.ask_number_luck(
            data.message, number_text,
            topic_keyword=topic_match[0] if topic_match else None,
            car_color=car_color,
            birth_weekday_color=weekday_color,
            birth_weekday_name=weekday_name,
            car_color_facts=car_facts,
        )
    elif car_facts and is_car_color_question(data.message):
        result = rag.ask_car_color(data.message, car_facts)
    elif name_suggest.is_name_suggest_question(data.message):
        # ขอให้แนะนำชื่อ (ไม่ได้ระบุชื่อมาเช็ค) — เช็คก่อน branch เช็คชื่อ เพราะมีคำว่า "ตั้งชื่อ" ซ้อนกัน
        result = rag.ask_name_suggest(data.message, current_user.birth_date)
    elif is_daily_color_question(data.message):
        # ถามสีมงคลประจำวัน/สีเสื้อมงคล — เช็คก่อนทุก branch อื่นเพราะเป็นคำถามที่
        # เจาะจงชัดเจนมาก ไม่อยากให้หลุดไปโดน branch ดวง/ราศีทั่วไปก่อน ดึงข้อมูลจริง
        # จากตาราง daily_color_charts ของวันนี้มาตอบ แทนการค้นหาแบบ semantic search
        # ทั่วไปใน ChromaDB ซึ่งไม่มีข้อมูลสีมงคลจริงอยู่เลย
        today = date.today()
        color_row = content_crud.get_daily_color_chart_by_date(db, today.year, today.month, today.day)
        result = rag.ask_daily_color(data.message, color_row)
    elif is_daily_lucky_number_question(data.message):
        # ถามเลขมงคล/เลขนำโชคของวันนี้ — ตอบด้วยเลขที่คำนวณจริง ชุดเดียวกับการ์ดเสี่ยงทาย
        result = rag.ask_daily_lucky_numbers(data.message, current_user.birth_date)
    elif zodiac_sign and current_user.birth_date and not named_rasi and is_today_report_question(data.message):
        # ดวง "วันนี้" (รวม/เจาะหมวด) — ใช้ผลคำนวณหลายหมวดชุดเดียวกับการ์ดในแอป
        result = rag.ask_daily_report(
            data.message, zodiac_sign, current_user.birth_date, getattr(current_user, "birth_time", None)
        )
    elif (
        zodiac_sign and current_user.birth_date and topic_match and not named_rasi
        and is_current_topic_question(data.message)
    ):
        # ถามเจาะหมวดทั่วไป/ช่วงนี้ (เช่น "ดวงคนมีแฟนเป็นยังไง") — ใช้ผลคำนวณหลายหมวด
        # ชุดเดียวกับการ์ดดวงวันนี้ ให้คำตอบอิงข้อมูลผู้ใช้จริง ไม่เป็นข้อความทั่วไป
        result = rag.ask_daily_report(
            data.message, zodiac_sign, current_user.birth_date,
            getattr(current_user, "birth_time", None), general=True,
        )
    elif zodiac_sign and topic_match and not named_rasi:
        # ถามเจาะจงหัวข้อชีวิต เช่น "ดวงความรักช่วงนี้" หรือ "ความรักฉันจะเป็นไง" —
        # คำนวณมุมสัมพันธ์กับภพของหัวข้อนั้นตรงๆ แทนที่จะบอกแค่ภพรวมของวันนี้ (ซึ่ง
        # อาจไม่เกี่ยวกับหัวข้อที่ถามเลยก็ได้) ตั้งใจ "ไม่บังคับ" ให้ต้องมีคำว่า "ดวง"
        # หรือคำบอกช่วงเวลาด้วย (ต่างจากเดิม) เพราะพบว่าคนถามหัวข้อแบบนี้ลอยๆ โดยไม่มี
        # คำว่า "ดวง" เลยบ่อยมาก (เช่น "งานช่วงนี้เป็นไงบ้าง") ถ้าบังคับไว้จะตกไปตอบแบบ
        # ทั่วไปที่เสี่ยงหลุดไปเจอเนื้อหาไม่เกี่ยวข้อง หรือโดนกลไกปฏิเสธนอกขอบเขตเข้าใจผิด
        # ถ้าคำถามเอ่ยชื่อราศีอื่นตรงๆ (named_rasi) ให้ข้ามไปตอบตามราศีนั้นแทน ไม่ใช้
        # การคำนวณ transit ของราศีผู้ใช้เอง เพราะจะไม่ตรงกับราศีที่ถามถึง
        topic_keyword, topic_house_number = topic_match
        result = rag.ask_daily_horoscope_topic(
            data.message, zodiac_sign, topic_keyword, topic_house_number
        )
    elif zodiac_sign and is_daily_horoscope_question(data.message):
        result = rag.ask_daily_horoscope(data.message, zodiac_sign)
    elif named_rasi:
        # ถามเจาะจงราศีใดราศีหนึ่งตรงๆ (เช่น "ราศีตุลย์นิสัยเป็นไง") — ดึงด้วย id
        # ตรงๆ เสมอ ไม่ใช้ราศีของผู้ใช้เอง เพราะผู้ใช้อาจถามถึงราศีคนอื่นก็ได้
        result = rag.ask_zodiac_traits(data.message, named_rasi)
    elif zodiac_sign and is_generic_zodiac_question(data.message):
        result = rag.ask_zodiac_traits(data.message, zodiac_sign)
    elif phone_or_plate_digits:
        # ถามเลขศาสตร์เบอร์โทร/ทะเบียนรถจริง (เช่น "เบอร์ 0812345678 ดีไหม") —
        # เช็คก่อนเช็คชื่อมงคล/ดวงกำกวม เพราะเป็นคำถามที่ระบุชัดเจนด้วยตัวเลขจริง
        # ไม่ต้องเดาเจตนา
        result = rag.ask_number_sequence(data.message, phone_or_plate_digits)
    elif name_to_check and numerology.is_name_numerology_question(data.message):
        # ถามเลขศาสตร์ชื่อ (ผลรวมตัวอักษรเป็นตัวเลข) — คนละระบบกับการเช็คชื่อมงคล
        # ตามทักษาด้านล่าง (taksa.is_name_check_question) แม้จะพูดถึง "ชื่อ" เหมือนกัน
        # จึงต้องเช็คแยกก่อน โดยดูจากคำสำคัญที่เจาะจงกว่า เช่น "เลขชื่อ"
        result = rag.ask_name_numerology(data.message, name_to_check)
    elif current_user.birth_date and numerology.is_birthdate_numerology_question(data.message):
        # ถามเลขศาสตร์วันเกิด (เช่น "เลขของฉันคืออะไร") — ดึง birth_date ที่มีอยู่แล้ว
        # ในโปรไฟล์มาคำนวณตรงๆ ไม่ต้องให้ผู้ใช้พิมพ์วันเดือนปีเกิดซ้ำในแชท เช็คหลังเช็ค
        # เบอร์โทร/ทะเบียนและเลขชื่อ เพราะถ้าผู้ใช้ระบุเบอร์/ชื่อมาชัดเจนแล้วต้องใช้อันนั้น
        # ก่อนเสมอ กรณีนี้ไว้ดักคำถามกำกวมที่ไม่ได้ให้ข้อมูลอะไรมาเลยเท่านั้น
        result = rag.ask_birthdate_numerology(data.message, current_user.birth_date)
    elif current_user.birth_date and name_to_check and taksa.is_name_check_question(data.message):
        result = rag.ask_name_check(data.message, name_to_check, current_user.birth_date)
    elif zodiac_sign and is_ambiguous_fortune_question(data.message):
        # คำถาม "ดวง" กว้างๆ ที่ไม่ได้ระบุว่าจะเอาเลขศาสตร์หรือราศี (เช่น "ดวงความรัก
        # ของฉัน") — ตอบรวมทั้งสองมุมในคำตอบเดียว แทนที่จะเดาว่าผู้ใช้หมายถึงระบบไหน
        result = rag.ask_combined(data.message, zodiac_sign)
    else:
        result = rag.ask(data.message, follow_up_of=follow_up_of)

    return result


@router.get("/chat/history", response_model=ChatHistoryResponse)
def get_history(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    messages = crud.get_chat_history(db, current_user.id)
    return ChatHistoryResponse(
        messages=[
            ChatMessageOut(
                role=m.role,
                content=m.content,
                sources=[ChatSource(**s) for s in json.loads(m.sources)] if m.sources else None,
                created_at=m.created_at,
            )
            for m in messages
        ]
    )


@router.delete("/chat/history", status_code=status.HTTP_204_NO_CONTENT)
def delete_history(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    crud.clear_chat_history(db, current_user.id)
