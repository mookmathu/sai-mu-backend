"""
eval_retrieval.py
-----------------
วัดประสิทธิภาพ "การค้นคืน (retrieval)" ของ RAG ด้วยตัวชี้วัดแบบระบบแนะนำ
(Recommender / IR metrics) แล้วหาค่า K และ Threshold ที่เหมาะสมที่สุด

ตัวชี้วัด (คำนวณที่ K = 1..K_MAX แล้วเฉลี่ยทุกคำถามที่มีคำตอบถูก = macro average)
  Precision@K = (จำนวน chunk ที่เกี่ยวข้องใน top-K) / K
  Recall@K    = (จำนวน chunk ที่เกี่ยวข้องใน top-K) / (จำนวน chunk ที่เกี่ยวข้องทั้งหมด)
  F1@K        = 2PR / (P+R)
  NDCG@K      = DCG@K / IDCG@K  โดย gain = 2^grade - 1, discount = 1/log2(rank+1)
                (grade: 2 = ตรงที่สุด, 1 = เกี่ยวข้องรอง, 0 = ไม่เกี่ยว)

การหา Threshold สำหรับใช้งานจริง (2 ส่วน)
  1) K ที่เหมาะสม  = K ที่ให้ F1@K สูงสุด (เสมอกัน เลือก K เล็กกว่า เพื่อลด context/โทเค็น)
  2) similarity threshold (τ) = ค่าตัดคะแนนความคล้าย (1 - cosine distance) ที่ให้
     F1 สูงสุดเมื่อเก็บเฉพาะ chunk ใน top-K ที่ได้คะแนน >= τ
     และถ้ามีคำถามนอกขอบเขต (relevant = {}) จะบังคับให้ τ ปฏิเสธคำถามเหล่านั้นได้
     อย่างน้อย --min-reject (ค่าเริ่มต้น 0.8) — ใช้เทียบกับ SCOPE_SIMILARITY_THRESHOLD
     ใน rag_service.py

ชุดทดสอบ: test_set_ranking.json  รูปแบบ
  {"question": "...", "relevant": {"chunk-id": 2, "chunk-id-อื่น": 1}}   # grade 2/1
  {"question": "...", "relevant": {}}                                    # นอกขอบเขต

⚠️ ควรทบทวน/แก้ "relevant" ในชุดทดสอบให้ตรงกับความเห็นของผู้ออกแบบระบบก่อนนำตัวเลข
ไปรายงาน — ground truth คือสิ่งที่กำหนดผลทั้งหมด

ใช้ Gemini เฉพาะ embed คำถาม (1 request/คำถาม) ไม่เรียกโมเดลตอบ/กรรมการ จึงประหยัด
โควตา และ cache ผลค้นคืนไว้ที่ results/retrieval_cache.json (รันซ้ำไม่เสียโควตา)

รัน (จาก root ของโปรเจกต์ backend):
    python -m app.rag.eval.eval_retrieval
    python -m app.rag.eval.eval_retrieval --k-max 10 --min-reject 0.8
    python -m app.rag.eval.eval_retrieval --production   # ใช้การกรองโดเมนแบบแชทจริง
    python -m app.rag.eval.eval_retrieval --reset        # ลบ cache แล้วค้นใหม่
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).parent
TEST_SET = HERE / "test_set_ranking.json"
RESULTS = HERE / "results"
CACHE = RESULTS / "retrieval_cache.json"


# ---------------------------------------------------------------- metrics
def prf(retrieved: list[str], relevant: dict[str, int]) -> tuple[float, float, float]:
    hit = sum(1 for r in retrieved if relevant.get(r, 0) > 0)
    p = hit / len(retrieved) if retrieved else 0.0
    r = hit / len(relevant) if relevant else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def ndcg(retrieved: list[str], relevant: dict[str, int]) -> float:
    def dcg(grades):
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))

    got = dcg([relevant.get(r, 0) for r in retrieved])
    ideal = dcg(sorted(relevant.values(), reverse=True)[: len(retrieved)])
    return got / ideal if ideal else 0.0


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def evaluate(items: list[dict], k_max: int, min_reject: float, tau_step: float = 0.02, k_prod: int = 4):
    """items: [{question, relevant, ranked: [[id, score], ...]}]"""
    inscope = [x for x in items if x["relevant"]]
    oos = [x for x in items if not x["relevant"]]

    by_k = []
    for k in range(1, k_max + 1):
        rows = []
        for x in inscope:
            ids = [i for i, _ in x["ranked"][:k]]
            p, r, f = prf(ids, x["relevant"])
            rows.append((p, r, f, ndcg(ids, x["relevant"])))
        by_k.append({
            "k": k,
            "precision": mean(r[0] for r in rows), "recall": mean(r[1] for r in rows),
            "f1": mean(r[2] for r in rows), "ndcg": mean(r[3] for r in rows),
        })
    best_k_f1 = max(by_k, key=lambda r: (round(r["f1"], 6), -r["k"]))
    best_k_ndcg = max(by_k, key=lambda r: (round(r["ndcg"], 6), -r["k"]))

    # threshold sweep (ใช้ K ที่ F1 สูงสุดเป็นเพดานจำนวน chunk)
    kk = best_k_f1["k"]
    sweep = []
    steps = int(round((0.95 - 0.20) / tau_step))
    for s in range(steps + 1):
        tau = round(0.20 + s * tau_step, 4)
        rows = []
        for x in inscope:
            ids = [i for i, sc in x["ranked"][:kk] if sc >= tau]
            p, r, f = prf(ids, x["relevant"])
            rows.append((p, r, f, ndcg(ids, x["relevant"])))
        rej = mean(1.0 if not x["ranked"] or x["ranked"][0][1] < tau else 0.0 for x in oos) if oos else None
        sweep.append({
            "tau": tau,
            "precision": mean(r[0] for r in rows), "recall": mean(r[1] for r in rows),
            "f1": mean(r[2] for r in rows), "ndcg": mean(r[3] for r in rows),
            "oos_reject_rate": rej,
        })
    ok = [r for r in sweep if r["oos_reject_rate"] is None or r["oos_reject_rate"] >= min_reject]
    pool = ok or sweep
    top = max(round(r["f1"], 6) for r in pool)
    plateau = [r for r in pool if round(r["f1"], 6) == top]
    best_tau = plateau[len(plateau) // 2]  # F1 เท่ากันหลายค่า → เลือกค่ากลางของช่วง (ทนต่อความแกว่งมากกว่าขอบช่วง)
    # relative-margin sweep: เก็บ chunk ใน top-k_prod ที่คะแนน >= (คะแนนอันดับ 1 - δ)
    delta_sweep = []
    for d in [x / 100 for x in range(0, 16)]:
        rows = []
        for x in inscope:
            ranked = x["ranked"][:k_prod]
            top = ranked[0][1] if ranked else 0
            ids = [i for i, sc in ranked if sc >= top - d]
            p, r, f = prf(ids, x["relevant"])
            rows.append((p, r, f, ndcg(ids, x["relevant"]), len(ids)))
        delta_sweep.append({
            "delta": d, "precision": mean(r[0] for r in rows), "recall": mean(r[1] for r in rows),
            "f1": mean(r[2] for r in rows), "ndcg": mean(r[3] for r in rows),
            "avg_chunks": mean(r[4] for r in rows),
        })
    best_delta = max(delta_sweep, key=lambda r: (round(r["f1"], 6), -r["delta"]))
    return {
        "delta_sweep": delta_sweep, "best_delta": best_delta, "k_prod": k_prod,
        "n_inscope": len(inscope), "n_out_of_scope": len(oos),
        "by_k": by_k, "best_k_by_f1": best_k_f1, "best_k_by_ndcg": best_k_ndcg,
        "k_used_for_threshold": kk, "threshold_sweep": sweep, "best_threshold": best_tau,
        "constraint_met": bool(ok),
    }


# ---------------------------------------------------------------- retrieval
def retrieve_all(questions: list[str], k_max: int, production: bool) -> dict[str, list]:
    from dotenv import load_dotenv

    load_dotenv()
    from ..retriever_chroma import ChromaRetriever

    exclude = None
    if production:
        from ..rag_service import GENERIC_SEARCH_EXCLUDE_DOMAINS as exclude  # noqa: N811

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    key = lambda q: f"{'prod' if production else 'all'}|{k_max}|{q}"  # noqa: E731
    retr = None
    for i, q in enumerate(questions, 1):
        if key(q) in cache:
            continue
        retr = retr or ChromaRetriever()
        print(f"[{i}/{len(questions)}] ค้น: {q}")
        res = retr.retrieve(q, top_k=k_max, exclude_domains=exclude)
        cache[key(q)] = [[c.id, round(s, 4)] for c, s in res]
        RESULTS.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {q: cache[key(q)] for q in questions}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k-max", type=int, default=10)
    ap.add_argument("--min-reject", type=float, default=0.8)
    ap.add_argument("--production", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--test-set", default=str(TEST_SET))
    a = ap.parse_args()

    if a.reset and CACHE.exists():
        CACHE.unlink()
    tests = json.loads(Path(a.test_set).read_text(encoding="utf-8"))
    ranked = retrieve_all([t["question"] for t in tests], a.k_max, a.production)
    items = [{**t, "ranked": ranked[t["question"]]} for t in tests]
    out = evaluate(items, a.k_max, a.min_reject)

    print(f"\nคำถามที่มีคำตอบ {out['n_inscope']} ข้อ | นอกขอบเขต {out['n_out_of_scope']} ข้อ\n")
    print(f"{'K':>3} {'Precision':>10} {'Recall':>8} {'F1':>7} {'NDCG':>7}")
    for r in out["by_k"]:
        print(f"{r['k']:>3} {r['precision']:>10.3f} {r['recall']:>8.3f} {r['f1']:>7.3f} {r['ndcg']:>7.3f}")
    b, n = out["best_k_by_f1"], out["best_k_by_ndcg"]
    print(f"\nK ที่ F1 สูงสุด   = {b['k']}  (P={b['precision']:.3f} R={b['recall']:.3f} F1={b['f1']:.3f} NDCG={b['ndcg']:.3f})")
    print(f"K ที่ NDCG สูงสุด = {n['k']}  (NDCG={n['ndcg']:.3f})")
    t = out["best_threshold"]
    print(f"\nThreshold (similarity) ที่เหมาะสม = {t['tau']:.2f} ที่ K={out['k_used_for_threshold']}")
    print(f"  P={t['precision']:.3f} R={t['recall']:.3f} F1={t['f1']:.3f} NDCG={t['ndcg']:.3f}"
          + (f"  ปฏิเสธนอกขอบเขตได้ {t['oos_reject_rate']:.0%}" if t["oos_reject_rate"] is not None else ""))
    if not out["constraint_met"]:
        print("  ⚠️ ไม่มีค่า τ ที่ปฏิเสธนอกขอบเขตได้ตามเกณฑ์ --min-reject จึงเลือกจาก F1 อย่างเดียว")

    bd = out["best_delta"]
    print(f"\nเกณฑ์สัมพัทธ์ (เก็บ chunk ที่คะแนนไม่ต่ำกว่าอันดับ 1 เกิน δ) ที่ K={out['k_prod']}:")
    print(f"{'δ':>5} {'P':>6} {'R':>6} {'F1':>6} {'NDCG':>6} {'chunk เฉลี่ย':>12}")
    for r in out["delta_sweep"]:
        print(f"{r['delta']:>5.2f} {r['precision']:>6.3f} {r['recall']:>6.3f} {r['f1']:>6.3f} {r['ndcg']:>6.3f} {r['avg_chunks']:>12.2f}")
    print(f"δ ที่ F1 สูงสุด = {bd['delta']:.2f} (F1={bd['f1']:.3f}, R={bd['recall']:.3f}, chunk เฉลี่ย {bd['avg_chunks']:.2f})")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "retrieval_metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, rows in (("metrics_by_k.csv", out["by_k"]), ("threshold_sweep.csv", out["threshold_sweep"]), ("delta_sweep.csv", out["delta_sweep"])):
        with open(RESULTS / name, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"\nบันทึกผลที่ {RESULTS}")


if __name__ == "__main__":
    main()
