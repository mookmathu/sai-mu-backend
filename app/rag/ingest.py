"""
ingest.py
---------
โหลด data/chunks_clean.json -> สร้าง embedding ด้วย Gemini -> เก็บลง
ChromaDB แบบ persistent (เขียนไฟล์ลงดิสก์ที่ ./chroma_db) ทำครั้งเดียว
(หรือทุกครั้งที่ข้อมูลเปลี่ยน) ไม่ต้องรันซ้ำทุกครั้งที่เปิดโปรแกรม —
retriever_chroma.py แค่เปิดอ่านฐานที่ ingest ไว้แล้ว

รันซ้ำได้อย่างปลอดภัย (resumable): ถ้าเคย ingest ค้างไว้กลางทาง (เช่นโดน
429 rate limit ตอนแบตช์หลังๆ) รันคำสั่งเดิมซ้ำได้เลย จะข้าม chunk ที่ embed
ไปแล้วในคอลเลกชัน ไม่เสียโควตาซ้ำ — ถ้าอยากบังคับ embed ใหม่ทั้งหมด (เช่น
แก้เนื้อหา chunk เดิม ไม่ใช่แค่เพิ่มใหม่) ใช้ `--reset`

⚠️ ไฟล์นี้อยู่ใน package (app.rag) แล้ว รันตรงๆ ด้วย `python ingest.py`
ไม่ได้ (จะเจอ ImportError เพราะ relative import) ต้องรันจาก root ของโปรเจกต์
backend (โฟลเดอร์ที่มี requirements.txt) ด้วย -m แทน:

    python -m app.rag.ingest
    python -m app.rag.ingest --reset   # ล้างของเก่าทิ้งแล้ว embed ใหม่ทั้งหมด
    python -m app.rag.ingest --update-hints   # embed ใหม่เฉพาะ chunk ที่มี search_hint
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv

# โหลด .env ให้ก่อน (สำคัญ: สคริปต์นี้รันแยกจาก main.py โดยตรง ไม่ได้ผ่าน
# main.py เลย ต้องโหลดเองที่นี่อีกที ไม่งั้นจะไม่เห็น GEMINI_API_KEY ที่ตั้งไว้
# ใน .env — หาไฟล์ .env จาก working directory ที่รันคำสั่ง (ต้องรันจาก root
# ของโปรเจกต์ที่มีไฟล์ .env อยู่ ตามที่บอกไว้ด้านบน)
load_dotenv()

from .embeddings import GeminiEmbedder

DATA_PATH = Path(__file__).parent / "data" / "chunks_clean.json"
CHROMA_PATH = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "numerology_chunks"

# แบตช์เล็กลง + เว้นจังหวะระหว่างแบตช์ เพื่อไม่ให้ชน rate limit ของแพ็กเกจฟรี
# ง่ายกว่ายิงยาวรวดเดียวแล้วโดน 429 กลางทาง
BATCH_SIZE = 10
DELAY_BETWEEN_BATCHES_SECONDS = 2


def load_chunks() -> list[dict]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _domain_of(chunk_id: str) -> str:
    """จัดหมวด (domain) ของ chunk จาก prefix ของ id — ใช้กรองไม่ให้ chunk บาง
    ประเภทหลุดเข้ามาปนกับการค้นหาแบบทั่วไป (semantic search) โดยไม่ตั้งใจ
    ปัจจุบันที่ต้องกันไว้คือ:
      - zodiac-* (นิสัยประจำราศี) เพราะพูดถึง "ความรัก"/"การงาน" บ่อยมาก จนไป
        แย่งอันดับกับ chunk เลขศาสตร์ที่ถามเรื่องเดียวกัน ทั้งที่ผู้ใช้ไม่ได้ถามเรื่องราศี
      - taksa-day-* (ตารางหมวดทักษารายวัน) เพราะเป็นข้อมูลเฉพาะที่ไม่มีประโยชน์
        นอกบริบทการเช็คชื่อมงคล
    ทั้งสองแบบนี้ถูกออกแบบให้เข้าถึงได้ผ่านการดึงด้วย id ตรงๆ เท่านั้น (ดู
    rag_service.py: ask_zodiac_traits / ask_name_check) ไม่ใช่ผ่าน semantic search"""
    if chunk_id.startswith("zodiac-"):
        return "zodiac_trait"
    if chunk_id.startswith("taksa-day-"):
        return "taksa_day"
    return "general"


def embed_text_of(chunk: dict) -> str:
    """ข้อความที่ใช้ "สร้างเวกเตอร์" = search_hint (ถ้ามี) + text — hint คือคำถาม/คำพูดที่ผู้ใช้
    มักใช้ ช่วยให้ค้นเจอเมื่อถามอ้อมๆ (เช่น "แฟนเก่าจะกลับมาไหม") แต่ document ที่เก็บ
    และส่งให้ Gemini ยังเป็น text เดิมล้วนๆ ไม่ปนคำ hint เข้าไปในคำตอบ"""
    hint = (chunk.get("search_hint") or "").strip()
    return f"{hint}\n{chunk['text']}" if hint else chunk["text"]


def update_hints(chunks: list[dict]) -> None:
    """--update-hints: embed ใหม่เฉพาะ chunk ที่มี search_hint แล้ว upsert ทับ (ไม่แตะ
    chunk อื่น ใช้โควตาแค่หลักสิบ request)"""
    targets = [c for c in chunks if c.get("search_hint")]
    embedder = GeminiEmbedder()
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    for start in range(0, len(targets), BATCH_SIZE):
        batch = targets[start : start + BATCH_SIZE]
        print(f"  re-embed (hint) {start + 1}-{start + len(batch)} / {len(targets)} ...")
        vectors = embedder.embed_documents([embed_text_of(c) for c in batch])
        collection.upsert(
            ids=[c["id"] for c in batch],
            embeddings=vectors,
            documents=[c["text"] for c in batch],
            metadatas=[
                {"title": c["title"], "number": c.get("number") or 0, "domain": _domain_of(c["id"])}
                for c in batch
            ],
        )
        if start + BATCH_SIZE < len(targets):
            time.sleep(DELAY_BETWEEN_BATCHES_SECONDS)
    print(f"เสร็จ — อัปเดต {len(targets)} chunks (รวมในฐาน {collection.count()})")


def main():
    reset = "--reset" in sys.argv
    if "--update-hints" in sys.argv:
        update_hints(load_chunks())
        return

    chunks = load_chunks()
    print(f"โหลด {len(chunks)} chunks จาก {DATA_PATH.name}")

    embedder = GeminiEmbedder()
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print("ล้างคอลเลกชันเดิมทิ้งแล้ว (--reset)")
        except Exception:
            pass
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # ใช้ cosine similarity ให้ตรงกับที่ retriever ตีความ
        )
    else:
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    already_done = set(collection.get(include=[])["ids"])
    remaining = [c for c in chunks if c["id"] not in already_done]

    if already_done:
        print(f"พบว่า embed ไปแล้ว {len(already_done)} chunks ก่อนหน้านี้ — ข้ามไป")
    if not remaining:
        print(f"ครบแล้ว ไม่มี chunk ที่ต้อง embed เพิ่ม (รวม {collection.count()} chunks)")
        return
    print(f"เหลือต้อง embed อีก {len(remaining)} chunks")

    for start in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[start : start + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        embed_inputs = [embed_text_of(c) for c in batch]

        print(f"  embedding chunk {start + 1}-{start + len(batch)} / {len(remaining)} ...")
        vectors = embedder.embed_documents(embed_inputs)

        collection.add(
            ids=[c["id"] for c in batch],
            embeddings=vectors,
            documents=texts,
            metadatas=[
                {
                    "title": c["title"],
                    "number": c.get("number") or 0,
                    "domain": _domain_of(c["id"]),
                }
                for c in batch
            ],
        )

        if start + BATCH_SIZE < len(remaining):
            time.sleep(DELAY_BETWEEN_BATCHES_SECONDS)

    print(f"เสร็จแล้ว — เก็บรวม {collection.count()} chunks ลง ChromaDB ที่ {CHROMA_PATH}")


if __name__ == "__main__":
    main()

