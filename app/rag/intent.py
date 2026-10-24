"""
rag/intent.py
---------------
Intent Parser (spec section 8). Consolidates the scattered heuristics
currently spread across rag_service.py / chat.py / taksa.py / transit.py
(is_daily_horoscope_question, is_generic_zodiac_question, detect_topic_house,
etc.) into one function returning a validated Intent object.

Per spec: "Intent parser สามารถใช้ LLM ได้ แต่ output ต้อง validate ด้วย JSON
Schema/Pydantic และห้ามให้ parser สร้าง calculated astrology facts."
i.e. this module may call an LLM to *classify* the question, but the
result is always passed through Intent(**raw) before use, and this module
must never itself invent a planet position, house, or any astrology fact.

STATUS: keyword-heuristic implementation below is a direct, non-breaking
port of the legacy dispatch logic in routers/chat.py — good enough to
route today's supported topics (name_check, numerology, zodiac/overview,
daily/period transit questions). An LLM-backed classifier can replace the
body of `parse_intent` later without changing its signature or the
Intent contract.
"""

from __future__ import annotations

from datetime import date, timedelta

from .schemas import Intent, Topic, TimeScope, TimeScopeType, UserContext

_LOVE_KEYWORDS = ["ความรัก", "แฟน", "คู่ครอง", "แต่งงาน"]
_CAREER_KEYWORDS = ["งาน", "อาชีพ", "การงาน"]
_FINANCE_KEYWORDS = ["เงิน", "การเงิน", "ทรัพย์"]
_HEALTH_KEYWORDS = ["สุขภาพ", "โรค", "ป่วย"]
_FAMILY_KEYWORDS = ["ครอบครัว", "พ่อแม่", "ญาติ"]
_TRAVEL_KEYWORDS = ["เดินทาง", "ย้ายถิ่น", "ต่างประเทศ"]

_TOPIC_KEYWORDS: list[tuple[Topic, list[str]]] = [
    (Topic.LOVE, _LOVE_KEYWORDS),
    (Topic.CAREER, _CAREER_KEYWORDS),
    (Topic.FINANCE, _FINANCE_KEYWORDS),
    (Topic.HEALTH, _HEALTH_KEYWORDS),
    (Topic.FAMILY, _FAMILY_KEYWORDS),
    (Topic.TRAVEL, _TRAVEL_KEYWORDS),
]

_PERIOD_KEYWORDS = {
    "วันนี้": 1,
    "สัปดาห์นี้": 7,
    "เดือนนี้": 30,
    "3 เดือน": 90,
    "ปีนี้": 365,
}


def _detect_time_scope(question: str, as_of: date) -> TimeScope:
    for kw, days in _PERIOD_KEYWORDS.items():
        if kw in question:
            return TimeScope(
                type=TimeScopeType.FUTURE_RANGE,
                start=as_of,
                end=as_of + timedelta(days=days),
            )
    return TimeScope(type=TimeScopeType.NATAL_ONLY)


def _detect_topic(question: str) -> Topic:
    for topic, keywords in _TOPIC_KEYWORDS:
        if any(kw in question for kw in keywords):
            return topic
    return Topic.OVERVIEW


def parse_intent(question: str, as_of: date, user_context: UserContext | None = None) -> Intent:
    topic = _detect_topic(question)
    time_scope = _detect_time_scope(question, as_of)
    return Intent(
        topic=topic,
        time_scope=time_scope,
        requires_natal=True,
        requires_transit=time_scope.type != TimeScopeType.NATAL_ONLY,
        requires_taksa=False,
        requires_maha_taksa=False,
        user_context=user_context or UserContext(),
    )
