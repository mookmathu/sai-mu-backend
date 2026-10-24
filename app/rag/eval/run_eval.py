"""
run_eval.py
-----------
รันชุดคำถามทดสอบ (test_set.json) ผ่านระบบ RAG จริงทั้งหมด แล้ววัด 2 อย่าง:

1. Retrieval quality — chunk ที่ค้นเจอ (top-k จาก ChromaDB) ตรงกับ chunk ที่
   ควรจะเจอจริง (expected_chunk_id ที่ระบุไว้ในชุดทดสอบ) หรือไม่
   - Hit Rate@k: สัดส่วนคำถามที่เจอ chunk ที่ถูกต้องอยู่ใน top-k กี่เปอร์เซ็นต์
   - MRR (Mean Reciprocal Rank): เฉลี่ยของ 1/อันดับที่เจอ (ยิ่งเจอไวยิ่งดี
     เจออันดับ 1 = 1.0, อันดับ 2 = 0.5, ไม่เจอเลย = 0)

2. Faithfulness — คำตอบที่ Gemini สร้างจาก context ที่ค้นมา มั่วเพิ่มเติม
   นอกเหนือจากข้อมูลอ้างอิงไหม (ให้ Gemini อีกตัวเป็นกรรมการ ดู judge.py)

บันทึกผลละเอียดเป็นไฟล์ JSON ไว้แนบเป็นหลักฐานในรายงาน/เล่มโปรเจกต์ได้ พร้อม
สรุปผลรวมพิมพ์ออกทาง terminal

⚠️ รันซ้ำได้อย่างปลอดภัย (resumable): Gemini free tier มีโควตา**รายวัน**ต่ำ
มาก (บางบัญชีแค่ 20 request/วัน/โมเดล) ชุดทดสอบ 20 ข้อ + judge อาจชนโควตา
กลางทางได้ง่าย — สคริปต์นี้บันทึกความคืบหน้าทีละคำถามไว้ที่
results/progress.json ถ้าโดนโควตาหมดกลางทาง (ขึ้นข้อความแจ้งชัดเจน ไม่ใช่
Traceback ยาวๆ) แค่รันคำสั่งเดิมซ้ำได้เลย (รอถึงรอบ reset เที่ยงคืนก่อน) จะ
ข้ามคำถามที่ทำสำเร็จไปแล้ว ไม่เสียโควตาซ้ำ

รัน (จาก root ของโปรเจกต์ backend):
    python -m app.rag.eval.run_eval
    python -m app.rag.eval.run_eval --top-k 6      # ปรับจำนวน chunk ที่ดึงมา
    python -m app.rag.eval.run_eval --skip-judge    # ข้ามขั้น faithfulness (เร็วกว่า ประหยัดโควตา)
    python -m app.rag.eval.run_eval --reset         # ล้างความคืบหน้าเดิมทิ้งแล้วเริ่มใหม่ทั้งหมด
"""

from __future__ import annotations

import argparse
import os
import re
import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # โหลด GEMINI_API_KEY จาก .env เหมือนกับ ingest.py

from ..embeddings import QuotaExhaustedError as EmbedQuotaExhaustedError
from ..gemini_client import DEFAULT_MODEL, GeminiClient
from ..gemini_client import QuotaExhaustedError as AnswerQuotaExhaustedError
from ..retriever_chroma import ChromaRetriever
from .judge import Judge
from .judge import QuotaExhaustedError as JudgeQuotaExhaustedError

TEST_SET_PATH = Path(__file__).parent / "test_set.json"
RESULTS_DIR = Path(__file__).parent / "results"
PROGRESS_PATH = RESULTS_DIR / "progress.json"  # ถูกเปลี่ยนใน main() ถ้าใช้ --test-set อื่น

QuotaExhausted = (EmbedQuotaExhaustedError, AnswerQuotaExhaustedError, JudgeQuotaExhaustedError)


def load_test_set() -> list[dict]:
    with open(TEST_SET_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_progress() -> list[dict]:
    if not PROGRESS_PATH.exists():
        return []
    with open(PROGRESS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_progress(results: list[dict]):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def compute_retrieval_metrics(retrieved_ids: list[str], expected_id: str) -> dict:
    """คืนค่า hit (เจอไหม) และ reciprocal_rank (1/อันดับที่เจอ, 0 ถ้าไม่เจอ)"""
    if expected_id in retrieved_ids:
        rank = retrieved_ids.index(expected_id) + 1  # อันดับเริ่มที่ 1 ไม่ใช่ 0
        return {"hit": True, "rank": rank, "reciprocal_rank": 1 / rank}
    return {"hit": False, "rank": None, "reciprocal_rank": 0.0}


def _call_with_minute_retry(fn, *a, retries: int = 4):
    """429 แบบรายนาที (PerMinute) ไม่ใช่โควตารายวัน → รอตามเวลาที่ Google บอกแล้วลองใหม่"""
    for attempt in range(retries + 1):
        try:
            return fn(*a)
        except Exception as e:
            msg = str(e)
            if "429" in msg and "PerMinute" in msg and attempt < retries:
                m = re.search(r"retry in ([\d.]+)s", msg)
                wait = float(m.group(1)) + 2 if m else 30
                print(f"    ชนโควตารายนาที รอ {wait:.0f} วินาทีแล้วลองใหม่...")
                time.sleep(wait)
                continue
            if ("503" in msg or "UNAVAILABLE" in msg) and attempt < retries:
                wait = 20 * (attempt + 1)
                print(f"    โมเดลคนใช้เยอะ (503) รอ {wait} วินาทีแล้วลองใหม่...")
                time.sleep(wait)
                continue
            raise


def main():
    parser = argparse.ArgumentParser(description="ประเมินคุณภาพระบบ RAG")
    parser.add_argument("--top-k", type=int, default=4, help="จำนวน chunk ที่ retrieve ต่อคำถาม")
    parser.add_argument("--skip-judge", action="store_true", help="ข้ามขั้นตอน faithfulness scoring")
    parser.add_argument("--test-set", default=None, help="ไฟล์ชุดทดสอบใน eval/ เช่น test_set_balanced.json (ค่าเริ่มต้น test_set.json) — แยกไฟล์ progress ให้อัตโนมัติ")
    parser.add_argument("--reset", action="store_true", help="ล้างความคืบหน้าเดิมทิ้งแล้วเริ่มใหม่ทั้งหมด")
    args = parser.parse_args()

    global TEST_SET_PATH, PROGRESS_PATH
    if args.test_set:
        TEST_SET_PATH = Path(__file__).parent / args.test_set
        PROGRESS_PATH = RESULTS_DIR / f"progress_{TEST_SET_PATH.stem}.json"
    test_set = load_test_set()
    print(f"โหลดชุดคำถามทดสอบ {len(test_set)} ข้อ จาก {TEST_SET_PATH.name}")

    results = [] if args.reset else load_progress()
    done_questions = {r["question"] for r in results}
    if done_questions:
        print(f"พบความคืบหน้าเดิม {len(done_questions)} ข้อ — จะข้ามคำถามที่ทำไปแล้ว\n")
    else:
        print()

    remaining = [c for c in test_set if c["question"] not in done_questions]
    if not remaining:
        print("ทำครบทุกข้อแล้ว ไม่มีคำถามที่ต้องรันเพิ่ม")
        _print_summary(results, args.top_k)
        _save_final_snapshot(results, args.top_k)
        return

    retriever = ChromaRetriever()
    # eval ต้องวัดจากโมเดล "ตัวเดียวคงที่" และไม่ใช้แคช ไม่งั้นผลปนกันระหว่างโมเดลหลัก/สำรอง
    # ค่าเริ่มต้นคือโมเดลหลักของแอป (gemini-2.5-flash) เปลี่ยนได้ด้วย  set EVAL_ANSWER_MODEL=...
    eval_model = os.environ.get("EVAL_ANSWER_MODEL", DEFAULT_MODEL)
    print(f"โมเดลตอบสำหรับ eval: {eval_model} (ไม่สลับโมเดลสำรอง ไม่ใช้แคช)")
    gemini = GeminiClient(model=eval_model, use_cache=False)
    judge = None if args.skip_judge else Judge()

    for i, case in enumerate(remaining, start=1):
        question = case["question"]
        expected_id = case["expected_chunk_id"]
        print(f"[{i}/{len(remaining)}] {question}")

        try:
            retrieved = retriever.retrieve(question, top_k=args.top_k)
            retrieved_ids = [chunk.id for chunk, _ in retrieved]
            retrieval_metrics = compute_retrieval_metrics(retrieved_ids, expected_id)

            context_chunks = [chunk.text for chunk, _ in retrieved]
            answer = _call_with_minute_retry(gemini.answer, question, context_chunks) if context_chunks else ""

            result = {
                "question": question,
                "category": case.get("category"),
                "expected_chunk_id": expected_id,
                "retrieved_chunk_ids": retrieved_ids,
                "retrieval": retrieval_metrics,
                "answer": answer,
            }

            if judge is not None and context_chunks:
                faithfulness = judge.score_faithfulness(question, answer, context_chunks)
                result["faithfulness"] = {
                    "score": faithfulness.score,
                    "unsupported_claims": faithfulness.unsupported_claims,
                    "reasoning": faithfulness.reasoning,
                }
            # free tier ของโมเดลตอบจำกัด 5 request/นาที → เว้น ~13 วินาทีต่อข้อ
            time.sleep(13)
        except QuotaExhausted as e:
            print(f"\n⚠️  {e}")
            print(
                f"บันทึกความคืบหน้าไว้แล้ว ({len(results)}/{len(test_set)} ข้อ) — "
                "รันคำสั่งเดิมซ้ำได้เลยหลังโควตา reset จะทำต่อจากจุดนี้ ไม่ต้องเริ่มใหม่"
            )
            return  # ออกจากโปรแกรมทันที ไม่ print summary (ยังทำไม่ครบ)

        results.append(result)
        save_progress(results)  # บันทึกทันทีทุกข้อ กันเสีย progress ถ้าโดนขัดจังหวะ

        hit_label = f"เจออันดับ {retrieval_metrics['rank']}" if retrieval_metrics["hit"] else "ไม่เจอ"
        faith_label = f", faithfulness={result['faithfulness']['score']:.2f}" if "faithfulness" in result else ""
        print(f"    retrieval: {hit_label}{faith_label}\n")

    _print_summary(results, args.top_k)
    _save_final_snapshot(results, args.top_k)


def _print_summary(results: list[dict], top_k: int):
    n = len(results)
    if n == 0:
        return
    hit_rate = sum(1 for r in results if r["retrieval"]["hit"]) / n
    mrr = sum(r["retrieval"]["reciprocal_rank"] for r in results) / n

    print("=" * 50)
    print(f"สรุปผล ({n} คำถาม, top_k={top_k})")
    print(f"  Retrieval Hit Rate@{top_k}: {hit_rate:.1%}")
    print(f"  Retrieval MRR:             {mrr:.3f}")

    faith_scores = [r["faithfulness"]["score"] for r in results if "faithfulness" in r]
    if faith_scores:
        avg_faith = sum(faith_scores) / len(faith_scores)
        print(f"  Faithfulness เฉลี่ย:        {avg_faith:.3f}")
        low_faith = [r for r in results if "faithfulness" in r and r["faithfulness"]["score"] < 0.7]
        if low_faith:
            print(f"  ⚠️  พบ {len(low_faith)} คำถามที่ faithfulness ต่ำกว่า 0.7 — ดูรายละเอียดในไฟล์ผลลัพธ์")
    cats = sorted({r.get("category") for r in results if r.get("category")})
    if cats:
        print("  แยกตามหมวด:")
        for c in cats:
            rs = [r for r in results if r.get("category") == c]
            h = sum(1 for r in rs if r["retrieval"]["hit"]) / len(rs)
            fs = [r["faithfulness"]["score"] for r in rs if "faithfulness" in r]
            f = f"{sum(fs) / len(fs):.2f}" if fs else "-"
            print(f"    {c:<14} n={len(rs)}  hit={h:.0%}  faithfulness={f}")
    print("=" * 50)


def _save_final_snapshot(results: list[dict], top_k: int):
    """เมื่อรันครบทุกข้อแล้ว บันทึกสำเนานิ่ง (มีวันที่-เวลากำกับ) แยกไว้ต่างหาก
    จาก progress.json เพื่อใช้แนบรายงาน/เล่มโปรเจกต์ — progress.json เองยังคง
    ไว้เป็น cache เผื่อรันเพิ่มคำถามใหม่ทีหลัง"""
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"eval_{timestamp}.json"

    n = len(results)
    summary = {
        "hit_rate": sum(1 for r in results if r["retrieval"]["hit"]) / n,
        "mrr": sum(r["retrieval"]["reciprocal_rank"] for r in results) / n,
        "top_k": top_k,
        "num_questions": n,
    }
    faith_scores = [r["faithfulness"]["score"] for r in results if "faithfulness" in r]
    if faith_scores:
        summary["avg_faithfulness"] = sum(faith_scores) / len(faith_scores)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": results}, f, ensure_ascii=False, indent=2)

    print(f"\nบันทึกผลละเอียดไว้ที่: {out_path}")


if __name__ == "__main__":
    main()
