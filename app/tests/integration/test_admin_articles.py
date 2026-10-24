"""
ทดสอบ CRUD บทความองค์เทพในหน้าแอดมิน + endpoint สาธารณะ /content/articles:
- ไม่ส่ง X-Admin-Key ต้อง 401
- slug ซ้ำ -> 409, topics/sections ผิดรูปแบบ -> 422
- ฉบับร่างไม่โผล่ใน /content/articles และ source_note ไม่ถูกส่งให้แอป
"""

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config, models
from app.database import Base, get_db
from app.main import app

TEST_ADMIN_KEY = "test-admin-key-for-pytest"

_engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
Base.metadata.create_all(bind=_engine)


def _override_get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
config.settings.admin_api_key = TEST_ADMIN_KEY
client = TestClient(app)
H = {"X-Admin-Key": TEST_ADMIN_KEY}


def setup_function():
    db = _TestSessionLocal()
    db.query(models.DeityArticle).delete()
    db.commit()
    db.close()


def _payload(**over):
    p = {
        "slug": "hindu-ganga",
        "title": "พระแม่คงคา",
        "subtitle": "Ganga Devi • เทวีแห่งสายน้ำ",
        "summary": "สรุปสั้น",
        "topics": "protection, change",
        "sections": json.dumps([{"heading": "ความเป็นมา", "body": "เนื้อหา"}], ensure_ascii=False),
        "source_note": "ที่มาลับฝั่งแอดมิน",
        "is_published": True,
    }
    p.update(over)
    return p


def test_requires_admin_key():
    assert client.get("/admin/content/articles").status_code == 401
    assert client.post("/admin/content/articles", json=_payload()).status_code == 401


def test_crud_and_public_listing_hides_drafts_and_source():
    r = client.post("/admin/content/articles", json=_payload(), headers=H)
    assert r.status_code == 201
    created = r.json()
    assert created["topics"] == "protection,change"
    assert client.post(
        "/admin/content/articles", json=_payload(slug="hindu-indra", title="พระอินทร์", is_published=False), headers=H
    ).status_code == 201

    public = client.get("/content/articles").json()
    assert [a["slug"] for a in public] == ["hindu-ganga"]
    assert public[0]["source_note"] is None

    r = client.put(f"/admin/content/articles/{created['id']}", json=_payload(title="พระแม่คงคา (แก้)"), headers=H)
    assert r.status_code == 200 and r.json()["title"] == "พระแม่คงคา (แก้)"
    assert client.delete(f"/admin/content/articles/{created['id']}", headers=H).status_code == 204
    assert client.delete(f"/admin/content/articles/{created['id']}", headers=H).status_code == 404


def test_duplicate_slug_and_validation():
    assert client.post("/admin/content/articles", json=_payload(), headers=H).status_code == 201
    assert client.post("/admin/content/articles", json=_payload(), headers=H).status_code == 409
    assert client.post("/admin/content/articles", json=_payload(slug="Bad Slug"), headers=H).status_code == 422
    assert client.post("/admin/content/articles", json=_payload(slug="x1", topics="nope"), headers=H).status_code == 422
    assert client.post("/admin/content/articles", json=_payload(slug="x2", sections="{not json"), headers=H).status_code == 422
