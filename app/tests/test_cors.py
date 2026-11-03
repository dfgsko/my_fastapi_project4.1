"""CORS для фронтенда на Vite (лаб. № 6): браузер на :5173 ходит в API на :8000."""

import pytest

from app import config

ORIGIN = "http://localhost:5173"


async def test_preflight_allows_vite_origin(anon_client):
    """Шаг 2 лабораторной: OPTIONS должен вернуть Access-Control-Allow-Origin."""
    resp = await anon_client.options(
        "/courses",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert "GET" in resp.headers["access-control-allow-methods"]
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()


async def test_both_localhost_spellings_allowed(anon_client):
    resp = await anon_client.options(
        "/courses",
        headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


async def test_foreign_origin_is_not_allowed(anon_client):
    resp = await anon_client.options(
        "/courses",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in resp.headers
    assert resp.status_code == 400  # Starlette отклоняет preflight с чужого origin


async def test_401_response_is_readable_by_browser(anon_client):
    """
    Без CORS-заголовков на ответе 401 браузер скрыл бы статус («CORS error»), и
    перехватчик Axios не смог бы отправить пользователя на /login.
    """
    resp = await anon_client.get("/courses", headers={"Origin": ORIGIN})
    assert resp.status_code == 401
    assert resp.headers["access-control-allow-origin"] == ORIGIN


async def test_login_from_vite_origin(anon_client, make_user):
    from app.tests.conftest import TEST_PASSWORD

    await make_user("bob")
    resp = await anon_client.post(
        "/auth/token",
        data={"username": "bob", "password": TEST_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert resp.json()["access_token"]


async def test_courses_list_has_fields_used_by_frontend(client):
    await client.post(
        "/courses",
        json={
            "title": "Kubernetes",
            "description": "Основы",
            "instructor": "Иванов",
            "duration_hours": 8,
        },
    )
    items = (await client.get("/courses", headers={"Origin": ORIGIN})).json()
    assert {"id", "title", "description", "instructor", "duration_hours"} <= set(items[0])


def test_cors_defaults_depend_on_environment(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert config.cors_origins() == config.DEV_CORS_ORIGINS
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert config.cors_origins() == []  # в production по умолчанию CORS выключен


def test_explicit_cors_settings_win(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert config.cors_origins() == []  # явная пустая строка выключает CORS
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    assert config.cors_origins() == ["https://a.example", "https://b.example"]


@pytest.mark.parametrize("bad", ["*", "http://*"])
def test_wildcard_never_default(bad):
    assert bad not in config.DEV_CORS_ORIGINS
