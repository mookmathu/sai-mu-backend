"""
compare_models.py
-----------------
เทียบ "คุณภาพคำตอบ" ของโมเดลตอบแชทหลายตัวบนคำถามชุดเดียวกัน (ก่อนตัดสินใจใช้โมเดลสำรอง/โมเดลหลัก)

ทำงานต่อคำถาม: ค้น chunk จาก ChromaDB ครั้งเดียว → ให้แต่ละโมเดลตอบจากข้อมูลอ้างอิงชุดเดียวกัน
→ ให้กรรมการ (judge.py) ให้คะแนน faithfulness → เก็บคำตอบทั้งหมดไว้ให้ "คนอ่านเทียบกันเอง"
(คะแนนจากกรรมการบอกได้แค่ว่าไม่มั่ว ส่วนความลื่น/ความเป็นกันเอง/ความเข้าใจง่ายต้องให้คนอ่านตัดสิน)

⚠️ หมายเหตุเรื่องความเป็นกลาง: กรรมการเป็น gemini-3.5-flash-lite (JUDGE_MODEL) ซึ่งเป็นหนึ่งในโมเดลที่ถูกเทียบ
อาจเอนเอียงเข้าข้างคำตอบของตัวเองเล็กน้อย — อยากให้เป็นกลางขึ้นให้ตั้ง JUDGE_MODEL เป็นตัวอื่นก่อนรัน

รันซ้ำได้ (resumable) เหมือน run_eval.py: บันทึกความคืบหน้าทีละ (โมเดล, คำถาม) ที่
results/compare_progress.json โดนโควตาหมดกลางทางก็รันคำสั่งเดิมต่อได้

รัน (จาก root ของโปรเจกต์ backend):
    python -m app.rag.eval.compare_models --limit 10
    python -m app.rag.eval.compare_models --models gemini-2.5-flash,gemini-3.5-flash-lite --limit 10
    python -m app.rag.eval.compare_models --limit 10 --reset
ข้อควรรู้: gemini-2.5-flash โควตาฟรีแค่ 20 ครั้ง/วัน (RPD) — ใช้ --limit 8 ถึง 10 ต่อวัน แล้วรันซ้ำวันถัดไปเพื่อเพิ่มจำนวนข้อ
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from ..embeddings import QuotaExhaustedError as EmbedQuotaExhaustedError  # noqa: E402
from ..gemini_client import DEFAULT_MODEL, FALLBACK_MODEL, GeminiClient  # noqa: E402
from ..gemini_client import QuotaExhaustedError as AnswerQuotaExhaustedError  # noqa: E402
from ..retriever_chroma import ChromaRetriever  # noqa: E402
from .judge import Judge  # noqa: E402
from .judge import QuotaExhaustedError as JudgeQuotaExhaustedError  # noqa: E402
from .run_eval import _call_with_minute_retry, load_test_set  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
PROGRESS_PATH = RESULTS_DIR / "compare_progress.json"
QuotaExhausted = (EmbedQuotaExhaustedError, AnswerQuotaExhaustedError, JudgeQuotaExhaustedError)

FORBIDDEN_ENDINGS = re.compile(r"(ค่ะ|คะ|ครับ|จ้ะ|จ๊ะ|จ้า|นะ)\s*($|[.!?\n])")
MARKDOWN = re.compile(r"(\*\*|^[ \t]*[-*•][ \t]+|^[ \t]*\d+\.[ \t]+|^#{1,6}[ \t])", re.MULTILINE)

# หน่วงระหว่างเรียกตาม RPM ของโมเดล (free tier): 2.5-flash = 5 RPM, lite = 15 RPM
SLEEP_AFTER_CALL = {DEFAULT_MODEL: 13, FALLBACK_MODEL: 5}


def style_flags(answer: str) -> dict:
    return {
        "has_markdown": bool(MARKDOWN.search(answer)),
        "has_forbidden_particle": bool(FORBIDDEN_ENDINGS.search(answer)),
        "chars": len(answer),
    }


def _load() -> list[dict]:
    return json.loads(PROGRESS_PATH.read_text(encoding="utf-8")) if PROGRESS_PATH.exists() else []


def _save(rows: list[dict]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    PROGRESS_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _summary(rows: list[dict], models: list[str]) -> None:
    print("=" * 60)
    for m in models:
        mine = [r for r in rows if r["model"] == m]
        if not mine:
            continue
        faith = [r["faithfulness"] for r in mine if r.get("faithfulness") is not None]
        avg_f = f"{sum(faith) / len(faith):.3f}" if faith else "-"
        md = sum(r["style"]["has_markdown"] for r in mine)
        pt = sum(r["style"]["has_forbidden_particle"] for r in mine)
        avg_len = sum(r["style"]["chars"] for r in mine) / len(mine)
        print(f"{m}: {len(mine)} ข้อ | faithfulness เฉลี่ย {avg_f} | มี markdown {md} | มีคำลงท้ายต้องห้าม {pt} | ยาวเฉลี่ย {avg_len:.0f} ตัวอักษร")
    print("=" * 60)
    print(f"คำตอบทั้งหมดเก็บไว้ที่ {PROGRESS_PATH} — เปิดอ่านเทียบกันทีละข้อได้")


def main() -> None:
    parser = argparse.ArgumentParser(description="เทียบคุณภาพคำตอบของโมเดลตอบแชท")
    parser.add_argument("--models", default=f"{DEFAULT_MODEL},{FALLBACK_MODEL}", help="คั่นด้วย ,")
    parser.add_argument("--limit", type=int, default=10, help="จำนวนคำถามแรกจากชุดทดสอบที่จะเทียบ")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    questions = load_test_set()[: args.limit]
    rows = [] if args.reset else _load()
    done = {(r["model"], r["question"]) for r in rows}

    retriever = ChromaRetriever()
    judge = Judge()
    clients = {m: GeminiClient(model=m, use_cache=False) for m in models}

    for qi, case in enumerate(questions, start=1):
        question = case["question"]
        todo = [m for m in models if (m, question) not in done]
        if not todo:
            continue
        print(f"[{qi}/{len(questions)}] {question}")
        try:
            retrieved = retriever.retrieve(question, top_k=args.top_k)
            chunks = [c.text for c, _ in retrieved]
            if not chunks:
                continue
            for m in todo:
                answer = _call_with_minute_retry(clients[m].answer, question, chunks)
                verdict = judge.score_faithfulness(question, answer, chunks)
                score = verdict.score
                rows.append(
                    {
                        "model": m, "question": question, "answer": answer, "faithfulness": score,
                        # เก็บเหตุผลของกรรมการไว้ด้วย จะได้รู้ว่าคะแนนต่ำเพราะแต่งข้อมูลเพิ่มจริง หรือกรรมการเข้มเกินไป
                        "unsupported_claims": verdict.unsupported_claims, "judge_reasoning": verdict.reasoning,
                        "context": chunks,
                        "style": style_flags(answer),
                    }
                )
                _save(rows)
                print(f"    {m}: faithfulness={score:.2f}")
                time.sleep(SLEEP_AFTER_CALL.get(m, 8))
        except QuotaExhausted as e:
            print(f"\n⚠️  {e}\nบันทึกความคืบหน้าไว้แล้ว — รันคำสั่งเดิมซ้ำหลังโควตา reset เพื่อทำต่อ")
            break

    _summary(rows, models)


if __name__ == "__main__":
    main()
