"""
retriever_chroma.py
--------------------
แทนที่ retriever.py เดิม (TF-IDF ในหน่วยความจำ) ด้วยการ query จาก ChromaDB
ที่ ingest.py สร้างไว้แล้ว — ต้องรัน `python3 ingest.py` อย่างน้อยหนึ่งครั้ง
ก่อนใช้ตัวนี้ (เช็คให้อัตโนมัติ ถ้ายังไม่เจอฐานข้อมูลจะแจ้งเตือนชัดเจน)

Interface เดียวกับ NumerologyRetriever เดิมทุกอย่าง (.retrieve(query, top_k)
คืน [(Chunk, score), ...]) เพื่อให้ main.py ใช้แทนกันได้โดยแทบไม่ต้องแก้โค้ด
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb

from .embeddings import GeminiEmbedder

CHROMA_PATH = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "numerology_chunks"


@dataclass
class Chunk:
    id: str
    title: str
    number: int | None
    text: str


class ChromaRetriever:
    def __init__(self, chroma_path: Path | str = CHROMA_PATH):
        self.chroma_path = Path(chroma_path)
        # หมายเหตุ: แค่เช็คว่าโฟลเดอร์ chroma_db มีอยู่ไม่พอ — PersistentClient
        # สร้างไฟล์ภายในโฟลเดอร์นี้ได้เองแม้ยังไม่เคย ingest เลยก็ตาม ต้อง
        # เช็คตรงๆ ว่า "collection" ที่ ingest.py สร้างไว้มีอยู่จริงหรือยัง
        self.client = chromadb.PersistentClient(path=str(self.chroma_path))
        try:
            self.collection = self.client.get_collection(COLLECTION_NAME)
        except Exception as e:
            raise FileNotFoundError(
                f"ไม่พบ collection '{COLLECTION_NAME}' ใน ChromaDB ที่ {self.chroma_path} — "
                "รัน `python -m app.rag.ingest` (หรือ `python ingest.py` ถ้าใช้แบบสแตนด์อโลน) "
                "ก่อนเพื่อสร้างฐานข้อมูลจาก chunks_clean.json"
            ) from e

        self.embedder = GeminiEmbedder()

    def retrieve(
        self, query: str, top_k: int = 4, exclude_domains: list[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        """exclude_domains: กันไม่ให้ chunk บางโดเมนหลุดเข้ามาปนกับคำถามทั่วไปโดย
        ไม่ตั้งใจ (เช่น chunk นิสัยราศี zodiac-* ที่พูดถึง "ความรัก"/"การงาน" บ่อยมาก
        จนไปแย่งอันดับกับ chunk เลขศาสตร์ที่พูดเรื่องเดียวกัน) — ใช้ตอนเรียกจาก
        NumerologyRAG.ask() (คำถามทั่วไป) เท่านั้น ส่วนเมธอดที่ดึงด้วย id ตรงๆ
        (เช่น ask_zodiac_traits) ไม่ผ่านฟังก์ชันนี้อยู่แล้วเลยไม่กระทบ"""
        query_vector = self.embedder.embed_query(query)

        where = {"domain": {"$nin": exclude_domains}} if exclude_domains else None

        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where,
        )

        chunks_with_scores = []
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]  # cosine distance, ยิ่งน้อยยิ่งใกล้เคียง

        for id_, doc, meta, distance in zip(ids, docs, metas, distances):
            chunk = Chunk(
                id=id_,
                title=meta["title"],
                number=meta["number"] or None,
                text=doc,
            )
            similarity = 1 - distance  # แปลงเป็นสเกล "ยิ่งมากยิ่งใกล้เคียง" ให้เข้าใจง่ายเหมือนตัวเดิม
            chunks_with_scores.append((chunk, similarity))

        return chunks_with_scores

    def get_by_ids(self, ids: list[str]) -> list[Chunk]:
        """ดึง chunk ตาม id ตรงๆ (ไม่ผ่าน semantic search) — ใช้ตอนรู้แน่ชัดอยู่แล้วว่า
        ต้องการ chunk ไหนจากการคำนวณ (เช่น "house-3" ที่ได้จาก
        transit.calculate_transit_house() สำหรับฟีเจอร์ดวงประจำวัน) ไม่ต้องเสี่ยงให้
        semantic search เลือกผิดตัว"""
        if not ids:
            return []

        results = self.collection.get(ids=ids)

        chunks = []
        for id_, doc, meta in zip(results["ids"], results["documents"], results["metadatas"]):
            chunks.append(
                Chunk(id=id_, title=meta["title"], number=meta["number"] or None, text=doc)
            )
        return chunks


if __name__ == "__main__":
    # ทดสอบเร็วๆ ว่า retrieval ทำงาน (ต้อง ingest แล้วและมี GEMINI_API_KEY)
    retriever = ChromaRetriever()
    for chunk, score in retriever.retrieve("เลข 5 ความหมายอะไร", top_k=3):
        print(f"[{score:.3f}] {chunk.id} - {chunk.title}")
