ADMIN = {"X-Admin-Key": "test-admin-key"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_upload_requires_key(client):
    r = client.post("/admin/content/images", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 401


def test_upload_then_public_can_view(client):
    r = client.post("/admin/content/images", headers=ADMIN, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 201
    got = client.get(r.json()["path"])
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    assert got.content == PNG


def test_upload_rejects_non_image(client):
    r = client.post("/admin/content/images", headers=ADMIN, files={"file": ("a.png", b"not an image", "image/png")})
    assert r.status_code == 400


def test_upload_rejects_too_large(client):
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024 + 1)
    r = client.post("/admin/content/images", headers=ADMIN, files={"file": ("a.png", big, "image/png")})
    assert r.status_code == 413


def test_missing_image_is_404(client):
    assert client.get("/content/images/999999").status_code == 404
