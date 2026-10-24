"""
judge.py
--------
"LLM-as-judge" — ใช้ Gemini อีกครั้งเป็นกรรมการให้คะแนนว่าคำตอบที่ RAG สร้าง
มา "อิงตามข้อมูลอ้างอิงจริง" (faithfulness / groundedness) แค่ไหน ไม่ใช่คะแนน
ว่าคำตอบถูกหรือผิดตามหลักเลขศาสตร์ (นั่นไม่มีใครเถียงได้ว่า "ถูก" จริง) แต่คือ
คะแนนว่า **สิ่งที่ตอบมามีอยู่ในข้อมูลอ้างอิงที่ค้นมาได้จริงไหม ไม่ได้มั่วเพิ่ม**

ใช้ response_mime_type="application/json" ให้ Gemini ตอบเป็น JSON ที่ parse
ได้ตรงๆ แทนการ parse ข้อความอิสระ (แม่นยำกว่า ไม่ต้องเดา regex)

⚠️ ตั้งใจใช้ JUDGE_MODEL คนละตัวกับโมเดลที่ตอบแชทจริง (gemini-2.5-flash ใน
gemini_client.py) เพราะ Gemini free tier มี**โควตารายวันแยกตามโมเดล**
(quota นี้ reset ทุกเที่ยงคืน ไม่ใช่ rate limit ต่อนาทีที่รอสักพักแล้วลองใหม่
ได้) ถ้าใช้โมเดลเดียวกันทั้งตอบแชทและตอน judge จะไปแย่งโควตาก้อนเดียวกัน
รันทดสอบ 20 คำถามก็ใช้ไป 40 request (20 ตอบ + 20 judge) ชนโควตาไวมาก
"""

from __future__ import annotations

import json
import os
import time

from google import genai
from google.genai import errors, types

# (เดิมใช้ gemini-2.0-flash-lite) รุ่น lite: โควตารายวันสูงกว่า gemini-2.5-flash มาก (free tier)
# และเป็นคนละ quota pool กับโมเดลที่ใช้ตอบแชทจริง เหมาะกับงาน judge ที่ไม่ได้
# ต้องการความสามารถระดับสูงสุด แค่เทียบข้อความกับ context ให้คะแนน
# gemini-2.0-flash-lite ถูกยกเลิกแล้ว (404) — ใช้รุ่น lite ตัวใหม่ และเปลี่ยนได้ผ่าน env
# JUDGE_MODEL โดยไม่ต้องแก้โค้ด เช่น  set JUDGE_MODEL=gemini-2.5-flash-lite
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash-lite")
MAX_RETRIES = 2

JUDGE_PROMPT_TEMPLATE = """\
คุณเป็นกรรมการตรวจสอบความถูกต้องของคำตอบจากระบบ RAG (Retrieval-Augmented
Generation) หน้าที่ของคุณคือเช็คว่า "คำตอบ" ด้านล่างนี้ทุกประโยคมีหลักฐาน
รองรับอยู่ใน "ข้อมูลอ้างอิง" ที่ให้มาจริงหรือไม่ ไม่ใช่ตัดสินว่าคำตอบถูกต้อง
ตามหลักเลขศาสตร์หรือไม่ — เช็คแค่ว่า "มั่ว/แต่งเพิ่มเติมนอกเหนือจากข้อมูล
อ้างอิงหรือเปล่า"

ข้อมูลอ้างอิง:
{context}

คำถาม: {question}

คำตอบที่ต้องตรวจสอบ:
{answer}

ให้คะแนน faithfulness_score เป็นตัวเลข 0.0-1.0:
- 1.0 = ทุกข้อความในคำตอบมีหลักฐานรองรับในข้อมูลอ้างอิงครบถ้วน
- 0.5 = มีบางส่วนที่มีหลักฐานรองรับ บางส่วนไม่มี
- 0.0 = คำตอบแทบไม่มีส่วนไหนอิงจากข้อมูลอ้างอิงเลย

ตอบกลับเป็น JSON เท่านั้น ตามรูปแบบนี้:
{{"faithfulness_score": <ตัวเลข 0.0-1.0>, "unsupported_claims": [<ประโยคที่ไม่มีหลักฐานรองรับ ถ้ามี>], "reasoning": "<เหตุผลสั้นๆ>"}}
"""


class QuotaExhaustedError(Exception):
    """โควตารายวันหมด (ไม่ใช่ rate limit ต่อนาที) — รอ/ลองใหม่ไม่ช่วย ต้องรอ
    ถึงรอบ reset (เที่ยงคืนตามเขตเวลาของ Google) หรือเปิด billing เท่านั้น"""


class FaithfulnessResult:
    def __init__(self, score: float, unsupported_claims: list[str], reasoning: str):
        self.score = score
        self.unsupported_claims = unsupported_claims
        self.reasoning = reasoning


class Judge:
    def __init__(self, api_key: str | None = None):
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("ไม่พบ GEMINI_API_KEY กรุณาตั้งค่า environment variable")
        self.client = genai.Client(api_key=api_key)

    def score_faithfulness(
        self, question: str, answer: str, context_chunks: list[str]
    ) -> FaithfulnessResult:
        context = "\n\n---\n\n".join(context_chunks)
        prompt = JUDGE_PROMPT_TEMPLATE.format(context=context, question=question, answer=answer)

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=JUDGE_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,  # อยากได้คะแนนสม่ำเสมอ ไม่ต้องการความหลากหลาย
                        response_mime_type="application/json",
                    ),
                )
                data = json.loads(response.text)
                return FaithfulnessResult(
                    score=float(data.get("faithfulness_score", 0.0)),
                    unsupported_claims=data.get("unsupported_claims", []),
                    reasoning=data.get("reasoning", ""),
                )
            except (errors.ClientError, errors.ServerError) as e:
                code = getattr(e, "code", None)
                if code == 429 and "PerDay" in str(e):
                    # โควตารายวันหมด — retry ไม่ช่วยอะไรเลย หยุดทันทีแทนเสียเวลารอฟรีๆ
                    raise QuotaExhaustedError(
                        f"โควตารายวันของโมเดล {JUDGE_MODEL} หมดแล้ว — รอ reset "
                        "รอบถัดไป (เที่ยงคืนตามเขตเวลา Google) หรือเปิด billing "
                        "ในโปรเจกต์ Google Cloud เพื่อเพิ่มโควตา"
                    ) from e
                is_retryable = code in (429, 503)
                if not is_retryable or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(3 * (attempt + 1))
        raise RuntimeError("judge ไม่สำเร็จหลังลองซ้ำครบจำนวนแล้ว")  # ไม่ควรมาถึงบรรทัดนี้