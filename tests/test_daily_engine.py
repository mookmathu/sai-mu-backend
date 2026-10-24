from datetime import date, time

from app import daily_engine as e


def test_report_shape_and_determinism():
    kw = dict(zodiac_sign="ตุลย์", birth_date=date(2002, 3, 14), today=date(2026, 10, 22), birth_time=time(8, 30))
    a, b = e.build_daily_report(**kw), e.build_daily_report(**kw)
    assert a == b
    assert [c["key"] for c in a["categories"]] == [k for k, _ in e.CATEGORIES]
    assert all(1 <= c["score"] <= 5 for c in a["categories"])
    assert all(f["sources"] for f in a["factors"])  # ทุกปัจจัยต้องมีแหล่งอ้างอิง


def test_unknown_birth_time_skips_natal_moon_layers():
    r = e.build_daily_report(zodiac_sign="ตุลย์", birth_date=date(2002, 3, 14), today=date(2026, 10, 22))
    assert r["birth_time_known"] is False
    assert [f["key"] for f in r["factors"]] == ["house"]  # ไม่เดาจันทร์กำเนิด


def test_good_and_bad_house_effect():
    from datetime import timedelta

    seen = {}
    for i in range(60):
        r = e.build_daily_report(zodiac_sign="เมษ", birth_date=date(2002, 3, 14), today=date(2026, 10, 1) + timedelta(days=i))
        seen[r["moon_house_no"]] = r
    good = seen[7]["categories"]  # ปัตนิ: ความรักและครอบครัว/เพื่อน เป็นภพดี
    assert next(c for c in good if c["key"] == "love")["score"] >= 4
    bad = seen[8]["categories"]  # มรณะ: ภพไม่ดี
    assert next(c for c in bad if c["key"] == "money")["score"] <= 2


def test_detect_focus():
    assert e.detect_focus("ความรักวันนี้เป็นไง") == "love"
    assert e.detect_focus("ดวงวันนี้เป็นยังไง") is None
