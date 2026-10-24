"""
api/astrology_query.py
-------------------------
POST /api/v1/astrology/query — the end-to-end pipeline from spec section 11:
  parse intent -> build/load chart -> (transit if needed) -> atomic facts ->
  query_builder -> retriever -> reranker -> dedup -> LLM interpreter ->
  guardrail check -> response with source_ids + limitations.

This is new/parallel to the existing POST /chat endpoint (routers/chat.py),
which keeps serving the current numerology + simple zodiac/taksa features
unchanged. This endpoint is where the new strictly-separated
Calculation/RAG/LLM pipeline actually gets exercised end-to-end.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .. import models
from ..astrology.facts import extract_atomic_facts, extract_transit_facts
from ..astrology.schemas import CalculationWarning, WarningLevel
from ..astrology.transit import build_transit_snapshot
from ..llm.interpreter import ReadingInterpreter
from ..llm.schemas import ReadingResponse
from ..rag.citations import source_ids_for
from ..rag.guardrails import GuardrailReport
from ..rag.intent import parse_intent
from ..rag.query_builder import build_query
from ..rag.reranker import deduplicate, rerank
from ..rag.retriever import Retriever
from ..rag.schemas import TimeScopeType, UserContext
from ..routers.auth import get_current_user
from .charts import get_or_build_chart

router = APIRouter(prefix="/api/v1/astrology", tags=["astrology-query"])

_retriever: Retriever | None = None
_interpreter: ReadingInterpreter | None = None


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def _get_interpreter() -> ReadingInterpreter:
    global _interpreter
    if _interpreter is None:
        try:
            _interpreter = ReadingInterpreter()
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ยังไม่ได้ตั้งค่า GEMINI_API_KEY บนเซิร์ฟเวอร์",
            ) from e
    return _interpreter


class AstrologyQueryRequest(BaseModel):
    question: str
    chart_id: str | None = None
    as_of: date | None = None
    relationship_status: str | None = None


class AstrologyQueryResponse(BaseModel):
    reading: ReadingResponse
    source_ids: list[str]
    calculation_warnings: list[str]
    guardrail_ok: bool
    guardrail_notes: list[str] = []


@router.post("/query", response_model=AstrologyQueryResponse)
def query_astrology(
    payload: AstrologyQueryRequest,
    current_user: models.User = Depends(get_current_user),
):
    as_of = payload.as_of or date.today()
    chart = get_or_build_chart(payload.chart_id, current_user)

    user_context = UserContext(relationship_status=payload.relationship_status)
    intent = parse_intent(payload.question, as_of, user_context)

    facts = extract_atomic_facts(chart)
    if intent.requires_transit and intent.time_scope.type != TimeScopeType.NATAL_ONLY:
        try:
            snapshot = build_transit_snapshot(as_of)
            chart.transits.append(snapshot)
            facts.extend(extract_transit_facts(snapshot))
        except Exception as e:  # e.g. FormulaNotVerifiedError for unsupported planets
            chart.calculation_warnings.append(
                CalculationWarning(
                    level=WarningLevel.LIMITATION,
                    code="transit_unavailable",
                    message=str(e),
                )
            )

    rquery = build_query(payload.question, intent, facts)
    try:
        chunks = _get_retriever().retrieve(rquery, top_k=6)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ระบบยังไม่ได้ ingest ข้อมูลเข้า ChromaDB — รัน `python -m app.rag.ingest` ก่อน",
        ) from e
    chunks = deduplicate(rerank(rquery, chunks))

    reading, guardrail_report = _get_interpreter().interpret(
        question=payload.question,
        facts=facts,
        chunks=chunks,
        calculation_warnings=chart.calculation_warnings,
    )

    return AstrologyQueryResponse(
        reading=reading,
        source_ids=source_ids_for(chunks),
        calculation_warnings=[w.message for w in chart.calculation_warnings],
        guardrail_ok=guardrail_report.ok,
        guardrail_notes=[f"[{v.code}] {v.message}" for v in guardrail_report.violations],
    )
