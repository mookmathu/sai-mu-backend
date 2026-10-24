"""
embeddings.py
-------------
เรียก Gemini embedding API (gemini-embedding-001) เพื่อแปลงข้อความเป็นเวกเตอร์
ใช้ทั้งตอน ingest (สร้าง embedding ของแต่ละ chunk) และตอน query (สร้าง
embedding ของคำถามผู้ใช้) — แยก task_type ให้ถูกต้องตามเอกสาร Gemini เพราะ
โมเดลนี้ปรับเวกเตอร์ตามว่าเป็น "เอกสารที่จะถูกค้นเจอ" หรือ "คำค้นหา" ต่างกัน

มี retry แบบ exponential backoff เฉพาะตอนเจอ 429 (RESOURCE_EXHAUSTED)
เพราะแพ็กเกจฟรีของ Gemini มี rate limit ต่ำ ยิงรัวๆ ติดกันจะโดนบล็อกง่าย

⚠️ แยก retry policy ระหว่าง ingest กับ query โดยตั้งใจ:
- ingest (embed_documents): รันครั้งเดียวตอน setup ไม่มีใครรออยู่หน้าจอ
  ทนรอนานได้ ใช้ retry นานสุด (5 ครั้ง, รวมสูงสุด ~155 วินาที)
- query (embed_query): ผู้ใช้กำลังรอคำตอบอยู่หน้าแอปจริงๆ ถ้ารอนานเท่า
  ingest จะเกิน timeout ฝั่ง Flutter (chat_api.dart ตั้งไว้ 45 วินาที) ทำให้
  ผู้ใช้เห็น "เซิร์ฟเวอร์ตอบช้าเกินไป" ทั้งที่จริงแล้ว backend ยังทำงานอยู่
  เบื้องหลัง (แค่กำลัง retry ค้างอยู่) จึงตั้ง retry ของ query ให้สั้นกว่ามาก
"""

from __future__ import annotations

import os
import time

from google import genai
from google.genai import errors, types

EMBEDDING_MODEL = "gemini-embedding-001"

_QUERY_CACHE_MAX = 1000
_query_vector_cache: dict[str, list[float]] = {}
INGEST_MAX_RETRIES = 5  # 5s, 10s, 20s, 40s, 80s
QUERY_MAX_RETRIES = 2  # 3s, 6s — ต้องไม่เกิน timeout ฝั่ง Flutter


class QuotaExhaustedError(Exception):
    """โควตารายวันหมด (ไม่ใช่ rate limit ต่อนาที) — retry ไม่ช่วย ต้องรอ reset
    (เที่ยงคืนตามเขตเวลา Google) หรือเปิด billing เท่านั้น"""


class GeminiEmbedder:
    def __init__(self, api_key: str | None = None):
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "ไม่พบ GEMINI_API_KEY กรุณาตั้งค่า environment variable "
                "หรือส่ง api_key เข้ามาตอนสร้าง GeminiEmbedder"
            )
        self.client = genai.Client(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """embed ข้อความที่จะถูกเก็บลง vector DB (ตอน ingest) — ทนรอได้นาน"""
        return self._embed(texts, task_type="RETRIEVAL_DOCUMENT", max_retries=INGEST_MAX_RETRIES, base_wait=5)

    def embed_query(self, text: str) -> list[float]:
        """embed คำถามของผู้ใช้ (ตอน retrieve) — ต้องตอบเร็ว ไม่ให้ผู้ใช้รอนาน
        จำเวกเตอร์ของคำถามที่เคยถามแล้วไว้ (คำถามเดิม = เวกเตอร์เดิมเสมอ จึงไม่กระทบคุณภาพการค้นหาเลย)
        ช่วยประหยัดโควตา embedding เมื่อมีคนกดคำถามแนะนำซ้ำๆ"""
        cached = _query_vector_cache.get(text)
        if cached is not None:
            return cached
        vector = self._embed([text], task_type="RETRIEVAL_QUERY", max_retries=QUERY_MAX_RETRIES, base_wait=3)[0]
        _query_vector_cache[text] = vector
        if len(_query_vector_cache) > _QUERY_CACHE_MAX:
            _query_vector_cache.pop(next(iter(_query_vector_cache)))  # ทิ้งตัวเก่าสุด (dict เรียงตามลำดับที่ใส่)
        return vector

    def _embed(
        self, texts: list[str], task_type: str, max_retries: int, base_wait: int
    ) -> list[list[float]]:
        for attempt in range(max_retries):
            try:
                result = self.client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=texts,
                    config=types.EmbedContentConfig(task_type=task_type),
                )
                return [e.values for e in result.embeddings]
            except (errors.ClientError, errors.ServerError) as e:
                code = getattr(e, "code", None)
                if code == 429 and "PerDay" in str(e):
                    raise QuotaExhaustedError(
                        f"โควตารายวันของโมเดล {EMBEDDING_MODEL} หมดแล้ว — รอ reset รอบถัดไป "
                        "(เที่ยงคืนตามเขตเวลา Google) หรือเปิด billing เพื่อเพิ่มโควตา"
                    ) from e
                is_retryable = code in (429, 503)
                if not is_retryable or attempt == max_retries - 1:
                    raise
                wait_seconds = 2**attempt * base_wait
                reason = "rate limit (429)" if code == 429 else "เซิร์ฟเวอร์ Gemini โหลดสูง (503)"
                print(
                    f"    โดน {reason} — รอ {wait_seconds} วินาทีแล้วลองใหม่ "
                    f"(ครั้งที่ {attempt + 1}/{max_retries}) ..."
                )
                time.sleep(wait_seconds)
        raise RuntimeError("embed ไม่สำเร็จหลังลองซ้ำครบจำนวนแล้ว")  # ไม่ควรมาถึงบรรทัดนี้

