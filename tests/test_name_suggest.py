import random
from datetime import date

from app import name_suggest, taksa


def test_detects_suggest_questions():
    assert name_suggest.is_name_suggest_question("แนะนำชื่อลูกชายเกิดวันอังคารหน่อย")
    assert name_suggest.is_name_suggest_question("ชื่ออะไรดี")
    assert name_suggest.is_name_suggest_question("ช่วยตั้งชื่อให้ลูกสาวหน่อย")


def test_does_not_hijack_name_check():
    assert not name_suggest.is_name_suggest_question('ตั้งชื่อ "ภูมิ" ดีไหม')
    assert not name_suggest.is_name_suggest_question("ชื่อภูมิดีไหม")


def test_extract_day_and_gender():
    assert name_suggest.extract_day_index("ลูกเกิดวันอังคาร") == 2
    assert name_suggest.extract_day_index("ชื่ออะไรดี") is None
    assert name_suggest.extract_gender("ชื่อลูกชาย") == "m"
    assert name_suggest.extract_gender("ชื่อลูกสาว") == "f"
    assert name_suggest.extract_gender("ชื่ออะไรดี") is None


def test_suggestions_avoid_kalakin_for_every_day():
    for day in range(7):
        for seed in range(5):
            names = name_suggest.suggest_names(day, None, 4, random.Random(seed))
            assert len(names) == 4
            assert len({n["name"] for n in names}) == 4
            for n in names:
                cat = taksa.classify_consonant(taksa.first_consonant(n["name"]), day)
                assert cat["name"] != "กาลกิณี"
                assert n["meaning"]


def test_gender_filter():
    males = {n["name"] for n in name_suggest.load_names() if n["gender"] == "f"}
    for n in name_suggest.suggest_names(2, "m", 4, random.Random(1)):
        assert n["name"] not in males
