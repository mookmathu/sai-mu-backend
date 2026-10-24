import pytest
from fastapi.testclient import TestClient

from app import number_luck as nl
from app.main import app


def test_groups_disjoint():
    assert not (nl.GREAT & nl.FAIR) and not (nl.GREAT & nl.POOR) and not (nl.FAIR & nl.POOR)


def test_article_examples():
    assert nl.analyze_number("5532")["total"] == 15          # ตัวอย่างบทความ
    r = nl.analyze_number("5กก-1555")                       # ก=1 → 5+1+1+1+5+5+5 = 23
    assert r["total"] == 23 and r["level"] == "great" and r["letter_sum"] == 2


def test_levels_and_unknown():
    assert nl.level_of(7) == "poor" and nl.level_of(13) == "fair" and nl.level_of(54) == "great"
    assert nl.level_of(1) == "unknown" and nl.level_of(2) == "unknown" and nl.level_of(55) == "unknown"


def test_thai_digits_and_phone():
    assert nl.analyze_number("๕๕๓๒")["total"] == 15
    assert nl.analyze_number("081-234-5678")["total"] == 0 + 8 + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8


def test_no_digits_error():
    with pytest.raises(ValueError):
        nl.analyze_number("กก")


def test_endpoint():
    c = TestClient(app)
    r = c.post("/numerology/number", json={"text": "5532"})
    assert r.status_code == 200 and r.json()["total"] == 15 and r.json()["level"] == "great"
    assert c.post("/numerology/number", json={"text": "กก"}).status_code == 400
    assert c.post("/numerology/number", json={"text": ""}).status_code == 422
