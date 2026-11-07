"""
Аутентификация: регистрация, вход, JWT в httpOnly cookie, refresh-ротация,
reuse detection, отзыв, политика паролей (лабораторные № 5 и № 8).
"""

from datetime import timedelta

import jwt
import pytest

from app.auth import create_access_token
from app.config import get_secret_key
from app.tests.conftest import TEST_PASSWORD, csrf_headers

REGISTER = {
    "username": "anna_s",
    "password": "Str0ng-passw0rd",
    "full_name": "Смирнова Анна",
    "email": "anna@example.com",
}


async def _login(client, username, password):
    return await client.post("/auth/token", data={"username": username, "password": password})


def _set_cookie_headers(resp) -> list[str]:
    return resp.headers.get_list("set-cookie")


def _cookie(resp, name: str) -> str:
    for header in _set_cookie_headers(resp):
        if header.startswith(f"{name}="):
            return header
    raise AssertionError(f"cookie {name} не выставлена: {_set_cookie_headers(resp)}")


# ------------------------------------------------------------ регистрация
async def test_register_creates_client_with_unverified_email(anon_client, monkeypatch):
    monkeypatch.setenv("AGE_VERIFICATION_ON_REGISTRATION", "false")
    resp = await anon_client.post("/auth/register", json=REGISTER)
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "client" and body["requires_age_verification"] is False
    assert "password" not in body and "hashed_password" not in body


async def test_register_rejects_role_field_mass_assignment(anon_client):
    resp = await anon_client.post("/auth/register", json={**REGISTER, "role": "admin"})
    assert resp.status_code == 422  # лишнее поле запрещено, роль не повышается


@pytest.mark.parametrize(
    "password", ["short1", "onlyletterslong", "1234567890123", "a1" * 40, "Abcdefgh123"]
)
async def test_register_password_policy(anon_client, password):
    # Последний пароль — 11 символов: минимум с лаб. № 8 — 12.
    resp = await anon_client.post("/auth/register", json={**REGISTER, "password": password})
    assert resp.status_code == 422


async def test_register_duplicate_email_409_with_field(anon_client):
    await anon_client.post("/auth/register", json=REGISTER)
    again = await anon_client.post(
        "/auth/register", json={**REGISTER, "username": "other_name", "email": "ANNA@example.com"}
    )
    assert again.status_code == 409
    assert again.json()["field"] == "email"  # форма покажет ошибку под полем email
    taken_login = await anon_client.post(
        "/auth/register", json={**REGISTER, "email": "other@example.com", "username": "ANNA_S"}
    )
    assert taken_login.status_code == 409 and taken_login.json()["field"] == "username"


async def test_register_can_be_disabled(anon_client, monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "false")
    assert (await anon_client.post("/auth/register", json=REGISTER)).status_code == 403


# ------------------------------------------------------------------- вход
async def test_login_sets_httponly_cookies_and_returns_no_tokens(anon_client, make_user):
    await make_user("bob")
    resp = await _login(anon_client, "bob", TEST_PASSWORD)
    assert resp.status_code == 200
    body = resp.json()
    # Токенов в теле нет: JavaScript (и XSS) их не увидит.
    assert "access_token" not in body and "refresh_token" not in body
    assert body["user"]["username"] == "bob"
    access = _cookie(resp, "access_token").lower()
    refresh = _cookie(resp, "refresh_token").lower()
    csrf = _cookie(resp, "csrf_token").lower()
    assert "httponly" in access and "samesite=strict" in access and "path=/" in access
    assert "httponly" in refresh and "path=/auth/refresh" in refresh
    assert "httponly" not in csrf  # CSRF-токен должен читать JS
    assert resp.headers["cache-control"] == "no-store"


async def test_cookie_is_secure_in_production(anon_client, make_user, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    await make_user("bob")
    resp = await _login(anon_client, "bob", TEST_PASSWORD)
    assert "secure" in _cookie(resp, "access_token").lower()


async def test_cookie_session_works_for_me(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob", TEST_PASSWORD)
    me = await anon_client.get("/auth/me")  # без заголовка Authorization — по cookie
    assert me.status_code == 200 and me.json()["username"] == "bob"


async def test_login_by_email(anon_client, make_user):
    await make_user("bob")
    assert (await _login(anon_client, "BOB@example.com", TEST_PASSWORD)).status_code == 200


async def test_login_errors_are_indistinguishable(anon_client, make_user):
    await make_user("bob")
    wrong_pass = await _login(anon_client, "bob", "Wrong-passw0rd")
    no_user = await _login(anon_client, "ghost", "Wrong-passw0rd")
    assert wrong_pass.status_code == no_user.status_code == 401
    assert wrong_pass.json() == no_user.json()


async def test_login_is_case_insensitive_for_username(anon_client, make_user):
    await make_user("bob")
    assert (await _login(anon_client, "BOB", TEST_PASSWORD)).status_code == 200


async def test_login_rate_limit_stops_bruteforce(anon_client, make_user, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX", "3")
    await make_user("bob")
    codes = [(await _login(anon_client, "bob", f"Wrong-pass{i}0")).status_code for i in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    # Даже верный пароль блокируется, пока окно не истечёт.
    assert (await _login(anon_client, "bob", TEST_PASSWORD)).status_code == 429


async def test_inactive_user_cannot_login(anon_client, client, make_user):
    info = await make_user("bob")
    await client.patch(f"/users/{info['id']}", json={"is_active": False})
    assert (await _login(anon_client, "bob", TEST_PASSWORD)).status_code == 401


# -------------------------------------------------------------- токены JWT
async def test_me_requires_token(anon_client):
    assert (await anon_client.get("/auth/me")).status_code == 401


async def test_me_returns_profile_without_secrets(user_client):
    body = (await user_client.get("/auth/me")).json()
    assert body["username"] == "alice" and body["role"] == "client"
    assert body["is_email_verified"] is True and body["totp_enabled"] is False
    for secret in ("hashed_password", "totp_secret", "email_verification_token",
                   "totp_recovery_codes"):
        assert secret not in body


async def test_expired_token_rejected(anon_client, make_user, db_session):
    from app.db_models.user import User

    info = await make_user("bob")
    async with db_session() as s:
        user = await s.get(User, info["id"])
    token = create_access_token(user, expires_delta=timedelta(seconds=-5))
    resp = await anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_forged_tokens_rejected(anon_client, make_user):
    info = await make_user("bob")
    now_claims = {"sub": "bob", "uid": info["id"], "type": "access", "role": "admin"}

    # 1. alg=none: подпись отсутствует.
    none_token = jwt.encode({**now_claims, "exp": 9999999999}, key=None, algorithm="none")
    # 2. подпись чужим ключом.
    wrong_key = jwt.encode({**now_claims, "exp": 9999999999}, "x" * 40, algorithm="HS256")
    # 3. без срока действия (exp обязателен).
    no_exp = jwt.encode(now_claims, get_secret_key(), algorithm="HS256")
    # 4. refresh вместо access; 5. temp_token 2FA вместо access.
    wrong_type = jwt.encode(
        {**now_claims, "type": "refresh", "exp": 9999999999}, get_secret_key(), algorithm="HS256"
    )
    pending = jwt.encode(
        {**now_claims, "type": "2fa_pending", "exp": 9999999999}, get_secret_key(),
        algorithm="HS256",
    )
    for token in (none_token, wrong_key, no_exp, wrong_type, pending, "garbage.token.value"):
        resp = await anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, token[:20]
        assert resp.headers["www-authenticate"] == "Bearer"


async def test_forged_cookie_rejected(anon_client, make_user):
    info = await make_user("bob")
    forged = jwt.encode(
        {"sub": "bob", "uid": info["id"], "type": "access", "exp": 9999999999}, "x" * 40,
        algorithm="HS256",
    )
    anon_client.cookies.set("access_token", forged)
    assert (await anon_client.get("/auth/me")).status_code == 401


async def test_role_in_token_is_not_trusted(anon_client, make_user):
    """Роль берётся из БД: токен с role=admin у обычного пользователя не даёт прав."""
    info = await make_user("bob")
    token = jwt.encode(
        {"sub": "bob", "uid": info["id"], "type": "access", "role": "admin", "exp": 9999999999},
        get_secret_key(),
        algorithm="HS256",
    )
    resp = await anon_client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_deactivated_user_token_stops_working_immediately(user_client, client):
    assert (await user_client.get("/auth/me")).status_code == 200
    await client.patch(f"/users/{user_client.info['id']}", json={"is_active": False})
    assert (await user_client.get("/auth/me")).status_code == 401


# ----------------------------------------------------------------- refresh
async def test_refresh_rotates_cookie_and_old_token_is_dead(anon_client, make_user):
    await make_user("bob")
    first = await _login(anon_client, "bob", TEST_PASSWORD)
    old_refresh = anon_client.cookies.get("refresh_token", path="/auth/refresh")
    second = await anon_client.post("/auth/refresh", headers=csrf_headers(anon_client))
    assert second.status_code == 200
    new_refresh = anon_client.cookies.get("refresh_token", path="/auth/refresh")
    assert new_refresh and new_refresh != old_refresh
    assert "refresh_token" not in second.json()
    assert (await anon_client.get("/auth/me")).status_code == 200
    assert first.status_code == 200


async def test_refresh_token_reuse_revokes_everything(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob", TEST_PASSWORD)
    stolen = anon_client.cookies.get("refresh_token", path="/auth/refresh")
    assert (await anon_client.post("/auth/refresh", headers=csrf_headers(anon_client))).status_code == 200
    # Злоумышленник (со своего клиента) предъявляет уже использованный токен →
    # вся сессия отзывается.
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as attacker:
        reuse = await attacker.post("/auth/refresh", json={"refresh_token": stolen})
    assert reuse.status_code == 401
    # Легальный пользователь тоже выкинут: и refresh, и access этой сессии мертвы.
    after = await anon_client.post("/auth/refresh", headers=csrf_headers(anon_client))
    assert after.status_code == 401
    assert (await anon_client.get("/auth/me")).status_code == 401


async def test_refresh_requires_csrf_header_when_using_cookie(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob", TEST_PASSWORD)
    no_header = await anon_client.post("/auth/refresh")
    assert no_header.status_code == 403
    wrong = await anon_client.post("/auth/refresh", headers={"X-CSRF-Token": "forged"})
    assert wrong.status_code == 403


async def test_access_token_cannot_be_used_as_refresh(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob", TEST_PASSWORD)
    access = anon_client.cookies.get("access_token")
    anon_client.cookies.clear()
    resp = await anon_client.post("/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


async def test_refresh_token_is_not_accepted_in_query_string(anon_client):
    resp = await anon_client.post("/auth/refresh?refresh_token=abc")
    assert resp.status_code == 401  # из query не читается (не попадает в логи)


async def test_logout_revokes_session_and_clears_cookies(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob", TEST_PASSWORD)
    refresh_cookie = anon_client.cookies.get("refresh_token", path="/auth/refresh")
    out = await anon_client.post("/auth/logout", headers=csrf_headers(anon_client))
    assert out.status_code == 204
    assert any(h.startswith("access_token=") and "max-age=0" in h.lower()
               for h in _set_cookie_headers(out))
    assert (await anon_client.get("/auth/me")).status_code == 401
    anon_client.cookies.clear()
    again = await anon_client.post("/auth/refresh", json={"refresh_token": refresh_cookie})
    assert again.status_code == 401


async def test_change_password_revokes_other_sessions(anon_client, make_user, db_session):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    await make_user("bob")
    # Вторая сессия того же пользователя (другое устройство).
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await _login(other, "bob", TEST_PASSWORD)
        await _login(anon_client, "bob", TEST_PASSWORD)
        bad = await anon_client.post(
            "/auth/change-password",
            json={"current_password": "Wrong-passw0rd", "new_password": "New-passw0rd-2"},
            headers=csrf_headers(anon_client),
        )
        assert bad.status_code == 400
        ok = await anon_client.post(
            "/auth/change-password",
            json={"current_password": TEST_PASSWORD, "new_password": "New-passw0rd-2"},
            headers=csrf_headers(anon_client),
        )
        assert ok.status_code == 204
        # Текущая сессия жива, другая — отозвана сразу (и access, и refresh).
        assert (await anon_client.get("/auth/me")).status_code == 200
        assert (await other.get("/auth/me")).status_code == 401
        # Отозванное устройство пытается обновить токен: 401, но это НЕ кража —
        # текущую сессию reuse detection не трогает.
        assert (await other.post("/auth/refresh", headers=csrf_headers(other))).status_code == 401
        assert (await anon_client.get("/auth/me")).status_code == 200
    anon_client.cookies.clear()
    assert (await _login(anon_client, "bob", "New-passw0rd-2")).status_code == 200
    assert (await _login(anon_client, "bob", TEST_PASSWORD)).status_code == 401


async def test_auth_events_are_counted(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob", "Wrong-passw0rd")
    await _login(anon_client, "bob", TEST_PASSWORD)
    text = (await anon_client.get("/metrics")).text
    assert 'auth_events_total{event="login_failure"}' in text
    assert 'auth_events_total{event="login_success"}' in text
