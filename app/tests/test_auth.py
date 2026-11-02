"""Аутентификация: регистрация, вход, JWT, refresh-ротация, отзыв, политика паролей."""

from datetime import timedelta

import jwt
import pytest

from app.auth import create_access_token
from app.config import get_secret_key
from app.tests.conftest import TEST_PASSWORD

REGISTER = {
    "username": "anna_s",
    "password": "Str0ng-passw0rd",
    "full_name": "Смирнова Анна",
    "email": "anna@example.com",
}


async def _login(client, username, password):
    return await client.post("/auth/token", data={"username": username, "password": password})


# ------------------------------------------------------------ регистрация
async def test_register_creates_user_with_role_user(anon_client):
    resp = await anon_client.post("/auth/register", json=REGISTER)
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "user" and body["student_id"] is not None
    assert "password" not in body and "hashed_password" not in body


async def test_register_rejects_role_field_mass_assignment(anon_client):
    resp = await anon_client.post("/auth/register", json={**REGISTER, "role": "admin"})
    assert resp.status_code == 422  # лишнее поле запрещено, роль не повышается


@pytest.mark.parametrize("password", ["short1", "onlyletterslong", "1234567890123", "a1" * 40])
async def test_register_password_policy(anon_client, password):
    resp = await anon_client.post("/auth/register", json={**REGISTER, "password": password})
    assert resp.status_code == 422


async def test_register_duplicate_returns_409(anon_client):
    await anon_client.post("/auth/register", json=REGISTER)
    again = await anon_client.post("/auth/register", json=REGISTER)
    assert again.status_code == 409
    other_email = await anon_client.post(
        "/auth/register", json={**REGISTER, "email": "other@example.com"}
    )
    assert other_email.status_code == 409
    assert other_email.json() == again.json()  # не раскрываем, что именно занято


async def test_register_can_be_disabled(anon_client, monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "false")
    assert (await anon_client.post("/auth/register", json=REGISTER)).status_code == 403


# ------------------------------------------------------------------- вход
async def test_login_returns_token_pair(anon_client, make_user):
    await make_user("bob")
    resp = await _login(anon_client, "bob", TEST_PASSWORD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer" and body["access_token"] and body["refresh_token"]
    assert resp.headers["cache-control"] == "no-store"


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


async def test_me_returns_current_user(user_client):
    body = (await user_client.get("/auth/me")).json()
    assert body["username"] == "alice" and body["role"] == "user"


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
    # 4. refresh вместо access.
    wrong_type = jwt.encode(
        {**now_claims, "type": "refresh", "exp": 9999999999}, get_secret_key(), algorithm="HS256"
    )
    for token in (none_token, wrong_key, no_exp, wrong_type, "garbage.token.value"):
        resp = await anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, token[:20]
        assert resp.headers["www-authenticate"] == "Bearer"


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
async def test_refresh_rotates_and_old_token_is_dead(anon_client, make_user):
    await make_user("bob")
    first = (await _login(anon_client, "bob", TEST_PASSWORD)).json()
    second = await anon_client.post(
        "/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert second.status_code == 200
    new_pair = second.json()
    assert new_pair["refresh_token"] != first["refresh_token"]
    me = await anon_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {new_pair['access_token']}"}
    )
    assert me.status_code == 200


async def test_refresh_token_reuse_revokes_everything(anon_client, make_user):
    await make_user("bob")
    first = (await _login(anon_client, "bob", TEST_PASSWORD)).json()
    rotated = (
        await anon_client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    ).json()
    # Кто-то повторно предъявляет уже использованный токен → кража: всё отзывается.
    reuse = await anon_client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401
    after = await anon_client.post(
        "/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert after.status_code == 401


async def test_access_token_cannot_be_used_as_refresh(anon_client, make_user):
    await make_user("bob")
    pair = (await _login(anon_client, "bob", TEST_PASSWORD)).json()
    resp = await anon_client.post("/auth/refresh", json={"refresh_token": pair["access_token"]})
    assert resp.status_code == 401


async def test_refresh_token_is_not_accepted_in_query_string(anon_client):
    resp = await anon_client.post("/auth/refresh?refresh_token=abc")
    assert resp.status_code == 422  # токен только в теле запроса (не попадает в логи)


async def test_logout_revokes_refresh_token(anon_client, make_user):
    await make_user("bob")
    pair = (await _login(anon_client, "bob", TEST_PASSWORD)).json()
    assert (
        await anon_client.post("/auth/logout", json={"refresh_token": pair["refresh_token"]})
    ).status_code == 204
    resp = await anon_client.post("/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert resp.status_code == 401


async def test_change_password_revokes_refresh_tokens(anon_client, make_user):
    await make_user("bob")
    pair = (await _login(anon_client, "bob", TEST_PASSWORD)).json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    bad = await anon_client.post(
        "/auth/change-password",
        json={"current_password": "Wrong-passw0rd", "new_password": "New-passw0rd-2"},
        headers=headers,
    )
    assert bad.status_code == 400
    ok = await anon_client.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "New-passw0rd-2"},
        headers=headers,
    )
    assert ok.status_code == 204
    assert (
        await anon_client.post("/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    ).status_code == 401
    assert (await _login(anon_client, "bob", "New-passw0rd-2")).status_code == 200
    assert (await _login(anon_client, "bob", TEST_PASSWORD)).status_code == 401


async def test_auth_events_are_counted(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob", "Wrong-passw0rd")
    await _login(anon_client, "bob", TEST_PASSWORD)
    text = (await anon_client.get("/metrics")).text
    assert 'auth_events_total{event="login_failure"}' in text
    assert 'auth_events_total{event="login_success"}' in text
