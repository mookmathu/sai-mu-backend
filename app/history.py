# -*- coding: utf-8 -*-
"""
history.py
----------
บันทึก/ค้นหา "ประวัติคำทำนาย" ของผู้ใช้ (ตาราง history_entries) สำหรับหน้า "ประวัติ"

หลักสำคัญ: การบันทึกประวัติเป็น "ส่วนเสริม" — ถ้าบันทึกไม่สำเร็จ (DB error ฯลฯ) ต้องไม่ทำให้
endpoint หลัก (แชท ดวงประจำวัน ฯลฯ) พัง จึงทุกฟังก์ชัน record_* กลืน error แล้ว log ไว้
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from .timeutil import utcnow

from sqlalchemy.orm import Session

from . import models, number_luck

log = logging.getLogger(__name__)

CATEGORIES = ("daily", "zodiac", "numerology", "color", "general")

# เก็บประวัติที่ "ไม่ได้บันทึกไว้" ของผู้ใช้แต่ละคนไม่เกินเท่านี้ (เก่าสุดถูกตัดทิ้ง) กัน DB โตไม่จำกัด
MAX_UNSAVED_PER_USER = 500

_NUMEROLOGY_WORDS = ["เบอร์", "ทะเบียน", "ป้าย", "เลขศาสตร์", "เลขชื่อ", "เลขมงคล", "เลข"]
_COLOR_WORDS = ["สี"]
_DAILY_WORDS = ["วันนี้", "ประจำวัน", "ช่วงนี้", "สัปดาห์นี้", "เดือนนี้"]
_ZODIAC_WORDS = ["ราศี", "ดวง", "ความรัก", "การงาน", "การเงิน"]


def classify(question: str) -> str:
    """จัดหมวดจากคำถาม — กติกาเดียวกับที่ฝั่งแอปเคยใช้ (features/history/models/history_entry.dart)"""
    def has(words):
        return any(w in question for w in words)

    if has(_NUMEROLOGY_WORDS):
        return "numerology"
    if has(_COLOR_WORDS):
        return "color"
    if has(_DAILY_WORDS):
        return "daily"
    if has(_ZODIAC_WORDS):
        return "zodiac"
    return "general"


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # ความยาวรวม "…" ต้องไม่เกิน n (คอลัมน์ VARCHAR ของ Postgres จะ error ถ้าเกิน แต่ SQLite ไม่เช็ก)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _prune(db: Session, user_id: int) -> None:
    ids = [
        r[0]
        for r in db.query(models.HistoryEntry.id)
        .filter(models.HistoryEntry.user_id == user_id, models.HistoryEntry.is_saved.is_(False))
        .order_by(models.HistoryEntry.created_at.desc())
        .offset(MAX_UNSAVED_PER_USER)
        .all()
    ]
    if ids:
        db.query(models.HistoryEntry).filter(models.HistoryEntry.id.in_(ids)).delete(synchronize_session=False)


def _add(
    db: Session, user_id: int, *, kind: str, category: str, title: str, content: str,
    ref_key: str | None = None, created_at: datetime | None = None,
) -> models.HistoryEntry | None:
    """เพิ่มรายการ ถ้ามี ref_key เดิมอยู่แล้วให้ปรับเนื้อหาของแถวเดิม (ไม่เพิ่มซ้ำ)"""
    try:
        entry = None
        if ref_key:
            entry = (
                db.query(models.HistoryEntry)
                .filter(models.HistoryEntry.user_id == user_id, models.HistoryEntry.ref_key == ref_key)
                .first()
            )
        if entry is None:
            entry = models.HistoryEntry(user_id=user_id, kind=kind, ref_key=ref_key)
            if created_at:
                entry.created_at = created_at
            db.add(entry)
        elif kind != "daily":
            entry.created_at = utcnow()  # ถามซ้ำ = ขยับขึ้นบนสุด
        entry.category = category
        entry.title = _clip(title, 200)
        entry.summary = _clip(content, 300)
        entry.content = content
        db.flush()
        _prune(db, user_id)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception:  # noqa: BLE001 — ประวัติเป็นส่วนเสริม ห้ามทำให้ endpoint หลักพัง
        log.exception("บันทึกประวัติไม่สำเร็จ")
        db.rollback()
        return None


def record_chat(db: Session, user_id: int, question: str, answer: str, category: str | None = None):
    cat = category if category in CATEGORIES else classify(question)
    return _add(db, user_id, kind="chat", category=cat, title=_clip(question, 64), content=answer)


def record_daily(db: Session, user_id: int, fortune: dict):
    """ดวงประจำวัน — วันละ 1 รายการต่อผู้ใช้ (เปิดการ์ดซ้ำทั้งวันก็ไม่เพิ่ม)"""
    colors = ", ".join(c["name"] for c in fortune.get("colors", []))
    numbers = ", ".join(str(n) for n in fortune.get("numbers", []))
    content = (
        f"{fortune['headline']}\n{fortune['summary']}\n"
        f"คำแนะนำ: {fortune['tip']}\n"
        f"สีแนะนำ: {colors or '-'}\nเลขนำโชค: {numbers or '-'}"
    )
    return _add(
        db, user_id, kind="daily", category="daily",
        title=f"ดวงประจำวัน{fortune['weekday']} · {fortune['focus']}",
        content=content, ref_key=f"daily:{fortune['date']}",
    )


_TAG_LABEL = {
    "good": "กลุ่มดี", "middle": "กลุ่มกลาง",
    "caution_female": "ระวังเรื่องความรัก", "caution_male": "ระวังเรื่องครอบครัว/การงาน",
}
_LEVEL_LABEL = {"great": "กลุ่มดี", "fair": "กลุ่มกลาง", "poor": "กลุ่มควรระวัง", "unknown": "ไม่อยู่ในกลุ่มที่ระบุ"}


def record_name(db: Session, user_id: int, analysis: dict, gender: str | None):
    parts = []
    for key, label in (("first", "ชื่อ"), ("last", "นามสกุล"), ("full", "รวม")):
        p = analysis[key]
        if key == "last" and not p["text"]:
            continue
        tags = ", ".join(_TAG_LABEL.get(t, t) for t in p["tags"]) or "ไม่อยู่ในกลุ่มที่ระบุ"
        parts.append(f"{label} {p['text']} = {p['total']} ({tags})")
    name = f"{analysis['first']['text']} {analysis['last']['text']}".strip()
    return _add(
        db, user_id, kind="name", category="numerology",
        title=f"เลขศาสตร์ชื่อ: {name}", content="\n".join(parts),
        ref_key=f"name:{analysis['first']['text']}|{analysis['last']['text']}|{gender or ''}",
    )


def record_number(db: Session, user_id: int, analysis: dict):
    content = (
        f"ผลรวม {analysis['total']} ({_LEVEL_LABEL[analysis['level']]})\n{analysis['note']}"
    )
    return _add(
        db, user_id, kind="number", category="numerology",
        title=f"เลขศาสตร์เบอร์/ทะเบียน: {analysis['input']}", content=content,
        ref_key=f"number:{analysis['input']}",
    )


def backfill_from_chat(db: Session, user_id: int | None = None) -> int:
    """ย้ายคู่คำถาม-คำตอบเดิมใน chat_messages เข้า history_entries (ทำซ้ำได้ ไม่ซ้ำรายการ)"""
    q = db.query(models.ChatMessage).order_by(models.ChatMessage.user_id, models.ChatMessage.created_at)
    if user_id is not None:
        q = q.filter(models.ChatMessage.user_id == user_id)
    added, pending = 0, {}
    for m in q.all():
        if m.role == "user":
            pending[m.user_id] = m
        elif m.role == "assistant" and m.user_id in pending:
            ques = pending.pop(m.user_id)
            key = f"chatmsg:{ques.id}"
            exists = (
                db.query(models.HistoryEntry.id)
                .filter(models.HistoryEntry.user_id == m.user_id, models.HistoryEntry.ref_key == key)
                .first()
            )
            if exists:
                continue
            db.add(models.HistoryEntry(
                user_id=m.user_id, kind="chat", category=classify(ques.content),
                title=_clip(ques.content, 64), summary=_clip(m.content, 300), content=m.content,
                ref_key=key, created_at=ques.created_at,
            ))
            added += 1
    db.commit()
    return added