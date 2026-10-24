"""
rag/guardrails.py
--------------------
Post-generation hallucination check (spec section 11, step 11: "ตรวจ output
ว่ามี claim ทางโหราศาสตร์ที่ไม่มี supporting fact/context หรือไม่", and section
16: "Hallucination test: ถ้า facts ไม่มีดาวศุกร์จร ห้าม output อ้างดาวศุกร์จร").

This is intentionally cheap/structural rather than another LLM call:
1. every section's supporting_fact_ids/source_ids must reference ids that
   were actually given to the model (catches invented citations outright)
2. every section must have at least one supporting_fact_id when it makes
   an astrology claim (a section with prose but zero grounding is a strong
   hallucination signal)
3. a lightweight lexical check: any known planet name mentioned in a
   section's interpretation must correspond to a fact_id used by that same
   section (catches "ดาวศุกร์จร..." appearing with no venus-transit fact
   behind it, per the spec's own example)

This is a safety net, not a substitute for good prompting — it can have
false positives on generic prose; callers should surface violations as
`limitations`/warnings rather than silently discarding the whole answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.schemas import ReadingResponse
from app.rag.schemas import AtomicFact
from app.rag.retriever import RetrievedChunk

_PLANET_THAI_NAMES = {
    "อาทิตย์": "suriya",
    "จันทร์": "jandra",
    "อังคาร": "angkarn",
    "พุธ": "puth",
    "พฤหัสบดี": "pruhasbodi",
    "ศุกร์": "suk",
    "เสาร์": "sao",
    "ราหู": "rahu",
    "เกตุ": "ketu",
}


@dataclass
class GuardrailViolation:
    section_title: str
    code: str
    message: str


@dataclass
class GuardrailReport:
    violations: list[GuardrailViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def check_response(
    response: ReadingResponse,
    known_facts: list[AtomicFact],
    known_chunks: list[RetrievedChunk],
) -> GuardrailReport:
    known_fact_ids = {f.fact_id() for f in known_facts}
    known_chunk_ids = {c.chunk_id for c in known_chunks}
    facts_by_id = {f.fact_id(): f for f in known_facts}

    report = GuardrailReport()

    for section in response.sections:
        unknown_facts = set(section.supporting_fact_ids) - known_fact_ids
        for fid in unknown_facts:
            report.violations.append(
                GuardrailViolation(
                    section.title, "unknown_fact_id",
                    f"cites fact_id '{fid}' that was never provided to the model",
                )
            )

        unknown_sources = set(section.source_ids) - known_chunk_ids
        for sid in unknown_sources:
            report.violations.append(
                GuardrailViolation(
                    section.title, "unknown_source_id",
                    f"cites source_id '{sid}' that was never retrieved",
                )
            )

        if not section.supporting_fact_ids:
            report.violations.append(
                GuardrailViolation(
                    section.title, "no_supporting_facts",
                    "section makes an interpretation with zero supporting_fact_ids",
                )
            )

        used_planets = set()
        for fid in section.supporting_fact_ids:
            fact = facts_by_id.get(fid)
            if fact and "planet" in fact.attributes:
                used_planets.add(fact.attributes["planet"])

        for thai_name, planet_id in _PLANET_THAI_NAMES.items():
            if thai_name in section.interpretation and planet_id not in used_planets:
                report.violations.append(
                    GuardrailViolation(
                        section.title, "unsupported_planet_mention",
                        f"mentions '{thai_name}' with no supporting fact for planet={planet_id}",
                    )
                )

    return report
