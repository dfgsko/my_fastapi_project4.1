"""Авторизация файлов в S3: каталог пользователя, сертификаты, path traversal."""

COURSE = {"title": "K8s", "description": "d", "instructor": "I", "duration_hours": 8}


async def _upload(c, name="a.txt", folder="docs"):
    resp = await c.post(
        f"/files/upload?folder={folder}", files={"file": (name, b"secret", "text/plain")}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


async def test_user_files_land_in_own_directory(user_client, fake_s3):
    key = await _upload(user_client)
    assert key.startswith(f"users/{user_client.info['id']}/docs/")
    assert key in fake_s3.objects


async def test_user_cannot_read_or_delete_other_users_files(user_client, make_user, fake_s3):
    key = await _upload(user_client)
    mallory = await make_user("mallory")
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=mallory["headers"]
    ) as other:
        assert (await other.get(f"/files/download/{key}")).status_code == 403
        assert (await other.get(f"/files/url/{key}")).status_code == 403
        assert (await other.delete(f"/files/{key}")).status_code == 403
        assert (await other.get("/files")).json()["count"] == 0  # чужие не видны в списке
    assert key in fake_s3.objects  # файл цел


async def test_user_cannot_read_arbitrary_keys(user_client, client, fake_s3):
    admin_key = await _upload(client, folder="internal")
    assert (await user_client.get(f"/files/download/{admin_key}")).status_code == 403
    assert (await user_client.get("/files/download/uploads/anything")).status_code == 403


async def test_list_is_scoped_to_own_prefix(user_client, client, fake_s3):
    await _upload(user_client)
    await _upload(client)
    mine = (await user_client.get("/files")).json()
    assert mine["count"] == 1 and mine["files"][0]["name"].startswith("users/")
    assert (await client.get("/files")).json()["count"] == 2  # админ видит всё


def test_key_syntax_blocks_path_traversal():
    """HTTP-клиенты нормализуют `..` в URL, поэтому проверяем функцию напрямую."""
    import pytest
    from fastapi import HTTPException

    from app.routers.files import _check_key_syntax

    for bad in (
        "users/1/../2/x",
        "../etc/passwd",
        "a/../../b",
        "/abs/path",
        "a\\b",
        "",
        "x" * 301,
    ):
        with pytest.raises(HTTPException) as exc:
            _check_key_syntax(bad)
        assert exc.value.status_code == 400, bad
    _check_key_syntax("users/1/docs/ab12_file.txt")  # нормальный ключ проходит


async def test_list_prefix_traversal_rejected(user_client, fake_s3):
    assert (await user_client.get("/files?prefix=../")).status_code == 400
    assert (await user_client.get("/files?prefix=a/../b")).status_code == 400


async def test_certificate_visible_only_to_its_student(user_client, client, make_user, fake_s3):
    course_id = (await client.post("/courses", json=COURSE)).json()["id"]
    enr = (
        await user_client.post(
            "/enrollments",
            json={"student_id": user_client.info["student_id"], "course_id": course_id},
        )
    ).json()
    cert_key = f"certificates/certificate_{enr['id']}.pdf"
    fake_s3.objects[cert_key] = (b"%PDF", "application/pdf")

    assert (await user_client.get(f"/files/download/{cert_key}")).status_code == 200

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    mallory = await make_user("mallory")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=mallory["headers"]
    ) as other:
        assert (await other.get(f"/files/download/{cert_key}")).status_code == 403
