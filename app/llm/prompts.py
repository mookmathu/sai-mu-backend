"""
llm/prompts.py
-----------------
Prompt Contract for the LLM synthesis step — a direct implementation of
spec section 12. Do not loosen the numbered rules below without updating
docs/thai_astrology_rag_implementation_spec.docx section 12 first; these
rules are what rag/guardrails.py checks the output against.
"""

from __future__ import annotations

import json

from app.astrology.schemas import CalculationWarning
from app.rag.schemas import AtomicFact
from app.rag.retriever import RetrievedChunk

SYSTEM_PROMPT = """\
คุณเป็นตัวสังเคราะห์คำพยากรณ์จากโหราศาสตร์ไทย
ใช้เฉพาะ CALCULATED_FACTS และ RETRIEVED_KNOWLEDGE ที่ได้รับ

กฎ:
1) ห้ามสร้างตำแหน่งดาว ลัคนา ภพ สถานะดาว ทักษา หรือความสัมพันธ์ดาวเอง
2) ห้ามกล่าวว่าดาวทำมุม/จร/อยู่ภพใด หากไม่มีใน CALCULATED_FACTS
3) การตีความต้องผูกกับ retrieved knowledge ที่เกี่ยวข้อง
4) หากตำราหลายแหล่งตีความต่างกัน ให้บอกว่ามีแนวทางต่างกันและแยกแหล่ง
5) หลีกเลี่ยงคำยืนยันอนาคตแบบแน่นอน ใช้ภาษาว่า "ตามหลัก...", "มีแนวโน้ม..."
6) สุขภาพ การเงิน กฎหมาย และความปลอดภัย: ห้ามใช้ดวงแทนคำแนะนำผู้เชี่ยวชาญ
7) คืน source_ids ของหลักที่ใช้ในแต่ละประเด็น
8) น้ำเสียงเป็นกันเองแบบเป็นกลางทางเพศ ห้ามใช้คำลงท้าย ค่ะ คะ ครับ จ้ะ จ๊ะ จ้า

OUTPUT JSON:
{
  "summary": "...",
  "sections": [
    {
      "title": "...",
      "interpretation": "...",
      "supporting_fact_ids": ["..."],
      "source_ids": ["..."]
    }
  ],
  "limitations": ["..."]
}
"""


def build_user_prompt(
    question: str,
    facts: list[AtomicFact],
    chunks: list[RetrievedChunk],
    calculation_warnings: list[CalculationWarning] | None = None,
) -> str:
    facts_payload = [
        {"fact_id": f.fact_id(), "fact_type": f.fact_type, **f.attributes} for f in facts
    ]
    knowledge_payload = [
        {"chunk_id": c.chunk_id, "title": c.title, "content": c.content} for c in chunks
    ]
    warnings_payload = [w.message for w in (calculation_warnings or [])]

    return (
        f"CALCULATED_FACTS:\n{json.dumps(facts_payload, ensure_ascii=False, indent=2)}\n\n"
        f"RETRIEVED_KNOWLEDGE:\n{json.dumps(knowledge_payload, ensure_ascii=False, indent=2)}\n\n"
        f"CALCULATION_WARNINGS:\n{json.dumps(warnings_payload, ensure_ascii=False)}\n\n"
        f"คำถามของผู้ใช้: {question}"
    )
