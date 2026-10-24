"""ความหมายรายเลข 0-100 ในหน้าเลขศาสตร์: ข้อมูลครบทุกเลข และผลรวมเกิน 100 ถูกลดทอนถูกต้อง"""
import json
from pathlib import Path

from app import name_numerology, number_luck, number_meanings


def test_every_number_0_to_100_has_complete_meaning():
    data = json.loads((Path(number_meanings._PATH)).read_text(encoding="utf-8"))
    assert sorted(int(k) for k in data) == list(range(0, 101))
    for k, v in data.items():
        assert v["title"] and v["overview"], k
        assert v["strengths"] or v["cautions"], k  # อย่างน้อยหนึ่งด้านต้องมีเนื้อหา
        assert "```" not in v["overview"] and "**" not in v["overview"], k  # ไม่มี markdown


def test_get_meaning_reduces_totals_over_100():
    assert number_meanings.get_meaning(15)["number"] == 15
    m = number_meanings.get_meaning(105)  # 101-109 -> หลักร้อย+หน่วย
    assert m["number"] == 15 and m["from_total"] == 105
    assert number_meanings.get_meaning(124)["number"] == 24  # ตั้งแต่ 110 -> หลักสิบ+หน่วย
    assert number_meanings.get_meaning(-1) is None


def test_name_and_number_results_include_meaning():
    r = name_numerology.analyze_name("สมชาย", "ใจดี", "male")
    assert r["full"]["meaning"]["number"] == r["full"]["total"]
    n = number_luck.analyze_number("5532")
    assert n["total"] == 15 and n["meaning"]["number"] == 15


def test_meaning_includes_digit_profiles():
    from app.number_meanings import get_meaning

    m = get_meaning(41)
    assert [p["number"] for p in m["profiles"]] == [4, 1, 5]
    for p in m["profiles"]:
        assert p["planet"] and p["personality"] and p["strengths"] and p["cautions"]
    assert [p["number"] for p in get_meaning(7)["profiles"]] == [7]
