import pytest
from fastapi.testclient import TestClient

from app import name_numerology as nn
from app.main import app


def test_table_covers_all_thai_consonants_once():
    consonants = set("กขคฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")
    assert consonants <= set(nn.CHAR_VALUE)
    all_chars = [c for chars in nn.TABLE.values() for c in chars]
    assert len(all_chars) == len(set(all_chars))
    assert all(1 <= v <= 9 for v in nn.CHAR_VALUE.values())


def test_char_values_from_table():
    assert nn.CHAR_VALUE["ก"] == 1 and nn.CHAR_VALUE["ม"] == 5 and nn.CHAR_VALUE["ย"] == 8
    assert nn.CHAR_VALUE["ใ"] == 6 and nn.CHAR_VALUE["ไ"] == 9 and nn.CHAR_VALUE["์"] == 9
    assert nn.CHAR_VALUE["ุ"] == 1 and nn.CHAR_VALUE["ู"] == 2 and nn.CHAR_VALUE["้"] == 2


def test_total_no_reduction_and_ignores_unknown():
    assert nn.total("มธุรดา") == 5 + 4 + 1 + 4 + 1 + 1
    assert nn.total("สมชาย  ABC 123 ฯ") == nn.total("สมชาย") == 23


def test_reverse_and_tags():
    assert nn.reverse_number(13) == 31
    assert nn.tags_for(23) == ["good", "caution_male"]
    assert nn.tags_for(23, "female") == ["good"]
    assert nn.tags_for(16, "male") == []
    assert nn.tags_for(16) == ["caution_female"]
    assert nn.tags_for(32) == ["middle", "caution_male"]
    assert nn.tags_for(7) == []


def test_skip_silenced(monkeypatch):
    base = nn.total("จันทร์")
    monkeypatch.setattr(nn, "SKIP_SILENCED", True)
    assert nn.total("จันทร์") == base - nn.CHAR_VALUE["ร"]


def test_analyze_weights_and_parts():
    r = nn.analyze_name("สมชาย", "ใจดี", "male")
    assert r["first"]["total"] == 23 and r["last"]["total"] == 20
    assert r["full"]["total"] == 43
    assert (r["first"]["weight"], r["last"]["weight"], r["full"]["weight"]) == (40, 20, 40)
    assert r["first"]["reverse_total"] == 32
    with pytest.raises(ValueError):
        nn.analyze_name("  ")


def test_endpoint():
    c = TestClient(app)
    r = c.post("/numerology/name", json={"first_name": "สมชาย", "last_name": "ใจดี", "gender": "male"})
    assert r.status_code == 200
    assert r.json()["first"]["total"] == 23
    assert c.post("/numerology/name", json={"first_name": ""}).status_code == 422
    assert c.post("/numerology/name", json={"first_name": "x", "gender": "other"}).status_code == 422
