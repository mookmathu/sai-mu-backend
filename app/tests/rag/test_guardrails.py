"""
Spec section 16: "Hallucination test: ถ้า facts ไม่มีดาวศุกร์จร ห้าม output
อ้างดาวศุกร์จร" and "Citation test: ทุก section ของคำทำนายต้องมี source_ids
เมื่อมีการตีความจากตำรา".
"""

from app.llm.schemas import ReadingResponse, ReadingSection
from app.rag.guardrails import check_response
from app.rag.retriever import RetrievedChunk
from app.rag.schemas import AtomicFact


def _fact(**attrs) -> AtomicFact:
    return AtomicFact(fact_type="planet_in_house", attributes=attrs)


def test_hallucinated_planet_is_flagged():
    facts = [_fact(planet="jandra", house=7)]  # only Moon in house 7, no Venus at all
    response = ReadingResponse(
        summary="s",
        sections=[
            ReadingSection(
                title="love",
                interpretation="ดาวศุกร์จรเข้าภพนี้ทำให้ดวงความรักดี",
                supporting_fact_ids=[facts[0].fact_id()],
                source_ids=[],
            )
        ],
    )
    report = check_response(response, facts, [])
    codes = {v.code for v in report.violations}
    assert "unsupported_planet_mention" in codes


def test_grounded_claim_passes():
    facts = [_fact(planet="jandra", house=7)]
    response = ReadingResponse(
        summary="s",
        sections=[
            ReadingSection(
                title="love",
                interpretation="ดาวจันทร์อยู่ภพที่ 7",
                supporting_fact_ids=[facts[0].fact_id()],
                source_ids=["chunk-1"],
            )
        ],
    )
    known_chunks = [RetrievedChunk(chunk_id="chunk-1", title="t", content="c", similarity=1.0, metadata={})]
    report = check_response(response, facts, known_chunks)
    assert report.ok


def test_unknown_fact_id_is_flagged():
    facts = [_fact(planet="jandra", house=7)]
    response = ReadingResponse(
        summary="s",
        sections=[
            ReadingSection(
                title="love",
                interpretation="text",
                supporting_fact_ids=["made-up-fact-id"],
                source_ids=[],
            )
        ],
    )
    report = check_response(response, facts, [])
    codes = {v.code for v in report.violations}
    assert "unknown_fact_id" in codes
