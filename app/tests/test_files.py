"""Тесты /files: загрузка, скачивание, список, presigned URL, удаление."""


async def test_upload_and_download_roundtrip(client, fake_s3):
    resp = await client.post(
        "/files/upload",
        files={"file": ("avatar.png", b"\x89PNG-data", "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["size"] == 9
    assert body["key"].startswith("uploads/") and body["key"].endswith("_avatar.png")
    assert body["path"] == f"fastapi-files/{body['key']}"

    dl = await client.get(f"/files/download/{body['key']}")
    assert dl.status_code == 200
    assert dl.content == b"\x89PNG-data"
    assert dl.headers["content-type"] == "image/png"
    assert "attachment" in dl.headers["content-disposition"]


async def test_upload_sanitizes_filename(client, fake_s3):
    resp = await client.post(
        "/files/upload",
        files={"file": ("../../etc/pass wd.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 201
    key = resp.json()["key"]
    assert ".." not in key and " " not in key
    assert key.count("/") == 1  # только папка uploads/


async def test_upload_custom_folder_and_validation(client, fake_s3):
    ok = await client.post(
        "/files/upload?folder=avatars", files={"file": ("a.txt", b"1", "text/plain")}
    )
    assert ok.status_code == 201 and ok.json()["key"].startswith("avatars/")
    bad = await client.post(
        "/files/upload?folder=../x", files={"file": ("a.txt", b"1", "text/plain")}
    )
    assert bad.status_code == 422


async def test_upload_too_large(client, fake_s3, monkeypatch):
    monkeypatch.setenv("S3_MAX_UPLOAD_BYTES", "10")
    resp = await client.post(
        "/files/upload", files={"file": ("big.bin", b"x" * 11, "application/octet-stream")}
    )
    assert resp.status_code == 413
    assert fake_s3.objects == {}


async def test_download_not_found(client, fake_s3):
    resp = await client.get("/files/download/uploads/nope.txt")
    assert resp.status_code == 404


async def test_list_and_delete(client, fake_s3):
    for name in ("a.txt", "b.txt"):
        await client.post("/files/upload", files={"file": (name, b"data", "text/plain")})
    listing = (await client.get("/files")).json()
    assert listing["count"] == 2
    key = listing["files"][0]["name"]

    assert (await client.delete(f"/files/{key}")).status_code == 204
    assert (await client.get("/files")).json()["count"] == 1


async def test_presigned_url(client, fake_s3):
    resp = await client.get("/files/url/uploads/a.txt?expires=120")
    assert resp.status_code == 200
    assert resp.json()["expires_in"] == 120
    assert "uploads/a.txt" in resp.json()["url"]
    assert (await client.get("/files/url/uploads/a.txt?expires=1")).status_code == 422


async def test_storage_down_returns_502(client, monkeypatch):
    import app.s3_client as s3_client
    from botocore.exceptions import EndpointConnectionError

    class Broken:
        def put_object(self, **_):
            raise EndpointConnectionError(endpoint_url="http://seaweedfs-s3:8333")

    monkeypatch.setattr(s3_client, "get_s3_client", lambda read_only=False: Broken())
    resp = await client.post("/files/upload", files={"file": ("a.txt", b"1", "text/plain")})
    assert resp.status_code == 502
