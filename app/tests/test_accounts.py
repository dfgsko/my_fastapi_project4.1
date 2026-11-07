"""
Лабораторная № 8: регистрация с проверкой возраста и подтверждением email,
2FA (TOTP), сессии, CSRF, ролевая модель, профиль, аватар, модерация.
"""

import io
import time
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app
from app.tests.conftest import TEST_PASSWORD, csrf_headers

NEW_USER = {"username": "petr", "email": "petr@example.com", "password": "Petr-passw0rd-1"}
COURSE = {"title": "Основы SQL", "description": "Курс", "instructor": "Иванов И.И.",
          "duration_hours": 10}


def _png(size=(128, 128), color=(200, 120, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


async def _login(client, username, password=TEST_PASSWORD):
    return await client.post("/auth/token", data={"username": username, "password": password})


def _new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _db_user(db_session, uid):
    from app.db_models.user import User

    async with db_session() as s:
        return await s.get(User, uid)


# ============================================================ регистрация
async def test_full_registration_flow_age_then_email_then_login(anon_client, sent_emails):
    reg = await anon_client.post("/auth/register", json=NEW_USER)
    assert reg.status_code == 201
    assert reg.json()["requires_age_verification"] is True
    assert sent_emails == []  # письмо — только после проверки возраста
    assert "registration_token=" in reg.headers.get("set-cookie", "")

    # До проверки возраста войти нельзя.
    blocked = await _login(anon_client, "petr", NEW_USER["password"])
    assert blocked.status_code == 403 and blocked.json()["code"] == "age_verification_required"

    age = await anon_client.post(
        "/auth/verify-age", files={"photo": ("me.png", _png(), "image/png")},
        headers=csrf_headers(anon_client),
    )
    assert age.status_code == 200, age.text
    assert age.json()["verified"] is True and age.json()["estimator"] == "mock"

    done = await anon_client.post("/auth/complete-registration", json={},
                                  headers=csrf_headers(anon_client))
    assert done.status_code == 200 and done.json()["email_sent"] is True
    assert len(sent_emails) == 1 and sent_emails[0][0] == "petr@example.com"

    # Email не подтверждён — вход заблокирован.
    not_yet = await _login(anon_client, "petr", NEW_USER["password"])
    assert not_yet.status_code == 403 and not_yet.json()["code"] == "email_not_verified"

    token = sent_emails[0][1]
    ok = await anon_client.get("/auth/verify-email", params={"token": token})
    assert ok.status_code == 200
    # Ссылка одноразовая.
    again = await anon_client.get("/auth/verify-email", params={"token": token})
    assert again.status_code == 400

    login = await _login(anon_client, "petr", NEW_USER["password"])
    assert login.status_code == 200
    me = (await anon_client.get("/auth/me")).json()
    assert me["is_email_verified"] and me["is_age_verified"] and me["role"] == "client"


async def test_registration_can_skip_age_verification(anon_client, sent_emails, db_session):
    reg = await anon_client.post("/auth/register", json=NEW_USER)
    done = await anon_client.post(
        "/auth/complete-registration", json={"skip_age_verification": True},
        headers=csrf_headers(anon_client),
    )
    assert done.status_code == 200 and len(sent_emails) == 1
    user = await _db_user(db_session, reg.json()["id"])
    assert user.age_verification_required is False and user.is_age_verified is False


async def test_complete_registration_without_age_is_forbidden(anon_client):
    await anon_client.post("/auth/register", json=NEW_USER)
    resp = await anon_client.post("/auth/complete-registration", json={},
                                  headers=csrf_headers(anon_client))
    assert resp.status_code == 403


async def test_registration_token_is_not_an_access_token(anon_client):
    await anon_client.post("/auth/register", json=NEW_USER)
    # Cookie незавершённой регистрации не даёт доступа к API.
    assert (await anon_client.get("/auth/me")).status_code == 401
    assert (await anon_client.get("/courses")).status_code == 401


async def test_email_token_stored_as_hash_and_expires(anon_client, sent_emails, db_session,
                                                      monkeypatch):
    monkeypatch.setenv("AGE_VERIFICATION_ON_REGISTRATION", "false")
    reg = await anon_client.post("/auth/register", json=NEW_USER)
    token = sent_emails[0][1]
    user = await _db_user(db_session, reg.json()["id"])
    assert user.email_verification_token != token and len(user.email_verification_token) == 64

    from app.db_models.user import User

    async with db_session() as s:
        u = await s.get(User, user.id)
        u.email_verification_sent_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=25)
        await s.commit()
    expired = await anon_client.get("/auth/verify-email", params={"token": token})
    assert expired.status_code == 400 and "истёк" in expired.json()["detail"]


async def test_resend_verification_is_generic_and_rate_limited(anon_client, sent_emails,
                                                               monkeypatch):
    monkeypatch.setenv("AGE_VERIFICATION_ON_REGISTRATION", "false")
    monkeypatch.setenv("EMAIL_RESEND_COOLDOWN_SECONDS", "0")
    await anon_client.post("/auth/register", json=NEW_USER)
    anon_client.cookies.clear()
    known = await anon_client.post("/auth/resend-verification", json={"email": NEW_USER["email"]})
    unknown = await anon_client.post("/auth/resend-verification", json={"email": "no@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()  # не раскрываем, есть ли такой адрес
    assert len(sent_emails) == 2
    # Новое письмо делает старую ссылку недействительной.
    old_token = sent_emails[0][1]
    assert (await anon_client.get("/auth/verify-email", params={"token": old_token})).status_code == 400


def test_verification_email_is_utf8_and_has_link(monkeypatch):
    from app.tasks import build_verification_email

    monkeypatch.setenv("FRONTEND_URL", "https://edu.example.com")
    msg, url = build_verification_email("anna@example.com", "tok123")
    assert url == "https://edu.example.com/verify-email?token=tok123"
    assert "Подтвердите email" in msg["Subject"] and url in msg.get_content()


# ================================================================== 2FA
async def _enable_2fa(client) -> tuple[str, list[str]]:
    enable = await client.post("/auth/2fa/enable", headers=csrf_headers(client))
    assert enable.status_code == 200, enable.text
    data = enable.json()
    assert data["qr_code"] and data["otpauth_uri"].startswith("otpauth://totp/")
    secret = data["secret"]
    confirm = await client.post(
        "/auth/2fa/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=csrf_headers(client)
    )
    assert confirm.status_code == 200, confirm.text
    return secret, confirm.json()["recovery_codes"]


async def test_2fa_enable_confirm_and_login_second_step(anon_client, make_user, db_session):
    info = await make_user("bob")
    await _login(anon_client, "bob")
    secret, recovery = await _enable_2fa(anon_client)
    assert len(recovery) == 8

    user = await _db_user(db_session, info["id"])
    assert user.totp_enabled and secret not in user.totp_secret  # секрет зашифрован

    anon_client.cookies.clear()
    first = await _login(anon_client, "bob")
    body = first.json()
    assert first.status_code == 200 and body["2fa_required"] is True and body["temp_token"]
    assert "access_token=" not in first.headers.get("set-cookie", "")  # токена ещё нет

    # Код прошлого интервала уже использован при confirm → берём следующий.
    code = pyotp.TOTP(secret).at(time.time() + 30)
    ok = await anon_client.post("/auth/2fa/verify",
                                json={"temp_token": body["temp_token"], "code": code})
    assert ok.status_code == 200
    assert (await anon_client.get("/auth/me")).json()["totp_enabled"] is True

    # temp_token одноразовый и не годится как access.
    replay = await anon_client.post("/auth/2fa/verify",
                                    json={"temp_token": body["temp_token"], "code": code})
    assert replay.status_code == 401
    as_access = await anon_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['temp_token']}"})
    assert as_access.status_code == 401


async def test_2fa_wrong_code_and_same_code_twice(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob")
    secret, _ = await _enable_2fa(anon_client)
    anon_client.cookies.clear()
    temp = (await _login(anon_client, "bob")).json()["temp_token"]
    bad = await anon_client.post("/auth/2fa/verify", json={"temp_token": temp, "code": "000000"})
    assert bad.status_code == 400
    # Код, уже принятый при подтверждении, повторно не принимается (replay).
    used = pyotp.TOTP(secret).now()
    replay = await anon_client.post("/auth/2fa/verify", json={"temp_token": temp, "code": used})
    assert replay.status_code == 400


async def test_2fa_recovery_code_works_once(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob")
    _, recovery = await _enable_2fa(anon_client)
    anon_client.cookies.clear()
    temp = (await _login(anon_client, "bob")).json()["temp_token"]
    ok = await anon_client.post("/auth/2fa/verify", json={"temp_token": temp, "code": recovery[0]})
    assert ok.status_code == 200
    assert (await anon_client.get("/auth/me")).json()["recovery_codes_left"] == 7
    anon_client.cookies.clear()
    temp2 = (await _login(anon_client, "bob")).json()["temp_token"]
    again = await anon_client.post("/auth/2fa/verify",
                                   json={"temp_token": temp2, "code": recovery[0]})
    assert again.status_code == 400


async def test_2fa_verify_is_rate_limited(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob")
    await _enable_2fa(anon_client)
    anon_client.cookies.clear()
    temp = (await _login(anon_client, "bob")).json()["temp_token"]
    codes = [
        (await anon_client.post("/auth/2fa/verify",
                                json={"temp_token": temp, "code": "11111" + str(i)})).status_code
        for i in range(6)
    ]
    assert codes[-1] == 429


async def test_2fa_temp_token_expires(anon_client, make_user, monkeypatch):
    await make_user("bob")
    await _login(anon_client, "bob")
    secret, _ = await _enable_2fa(anon_client)
    monkeypatch.setenv("TWO_FACTOR_TEMP_TOKEN_MINUTES", "-1")
    anon_client.cookies.clear()
    temp = (await _login(anon_client, "bob")).json()["temp_token"]
    code = pyotp.TOTP(secret).at(time.time() + 30)
    resp = await anon_client.post("/auth/2fa/verify", json={"temp_token": temp, "code": code})
    assert resp.status_code == 401


async def test_2fa_disable_requires_valid_code(anon_client, make_user):
    await make_user("bob")
    await _login(anon_client, "bob")
    secret, _ = await _enable_2fa(anon_client)
    bad = await anon_client.post("/auth/2fa/disable", json={"code": "123456"},
                                 headers=csrf_headers(anon_client))
    assert bad.status_code == 400
    code = pyotp.TOTP(secret).at(time.time() + 30)
    ok = await anon_client.post("/auth/2fa/disable", json={"code": code},
                                headers=csrf_headers(anon_client))
    assert ok.status_code == 200
    anon_client.cookies.clear()
    assert "2fa_required" not in (await _login(anon_client, "bob")).json()


async def test_2fa_confirm_requires_enable_first(user_client):
    resp = await user_client.post("/auth/2fa/confirm", json={"code": "123456"})
    assert resp.status_code == 400


# ======================================================== сессии и CSRF
async def test_sessions_list_and_revoke(anon_client, make_user):
    await make_user("bob")
    async with _new_client() as phone:
        await _login(phone, "bob")
        await _login(anon_client, "bob")
        sessions = (await anon_client.get("/auth/sessions")).json()
        assert len(sessions) == 2
        current = [s for s in sessions if s["current"]]
        other = [s for s in sessions if not s["current"]]
        assert len(current) == 1 and len(other) == 1
        assert current[0]["ip_address"] and current[0]["started_at"]

        revoke = await anon_client.delete(f"/auth/sessions/{other[0]['id']}",
                                          headers=csrf_headers(anon_client))
        assert revoke.status_code == 204
        assert (await phone.get("/auth/me")).status_code == 401  # сразу, не через 30 мин
        assert (await anon_client.get("/auth/me")).status_code == 200

        # Отзыв своей текущей сессии = выход.
        own = await anon_client.delete(f"/auth/sessions/{current[0]['id']}",
                                       headers=csrf_headers(anon_client))
        assert own.status_code == 204
        assert (await anon_client.get("/auth/me")).status_code == 401


async def test_cannot_revoke_foreign_session(anon_client, make_user):
    await make_user("bob")
    await make_user("eve")
    async with _new_client() as eve:
        await _login(eve, "eve")
        eve_session = (await eve.get("/auth/sessions")).json()[0]["id"]
        await _login(anon_client, "bob")
        resp = await anon_client.delete(f"/auth/sessions/{eve_session}",
                                        headers=csrf_headers(anon_client))
        assert resp.status_code == 404
        assert (await eve.get("/auth/me")).status_code == 200


async def test_logout_all_devices(anon_client, make_user):
    await make_user("bob")
    async with _new_client() as phone:
        await _login(phone, "bob")
        await _login(anon_client, "bob")
        out = await anon_client.post("/auth/logout-all", headers=csrf_headers(anon_client))
        assert out.status_code == 204
        assert (await phone.get("/auth/me")).status_code == 401
        assert (await anon_client.get("/auth/me")).status_code == 401


async def test_csrf_blocks_cookie_post_without_header(anon_client, make_user):
    await make_user("bob", role="moderator")
    await _login(anon_client, "bob")
    blocked = await anon_client.post("/courses", json=COURSE)
    assert blocked.status_code == 403 and "CSRF" in blocked.json()["detail"]
    ok = await anon_client.post("/courses", json=COURSE, headers=csrf_headers(anon_client))
    assert ok.status_code == 201
    # GET не требует CSRF-токена.
    assert (await anon_client.get("/courses")).status_code == 200


async def test_bearer_clients_do_not_need_csrf(client):
    # API-клиент с заголовком Authorization (Swagger, curl) cookie не использует.
    assert (await client.post("/courses", json=COURSE)).status_code == 201


# ===================================================================== RBAC
async def test_client_cannot_manage_courses_moderator_can(user_client, moderator_client):
    assert (await user_client.post("/courses", json=COURSE)).status_code == 403
    created = await moderator_client.post("/courses", json=COURSE)
    assert created.status_code == 201
    cid = created.json()["id"]
    assert (await user_client.put(f"/courses/{cid}", json=COURSE)).status_code == 403
    assert (await user_client.delete(f"/courses/{cid}")).status_code == 403
    assert (await moderator_client.put(f"/courses/{cid}", json={**COURSE, "title": "SQL-2"})
            ).status_code == 200
    assert (await moderator_client.delete(f"/courses/{cid}")).status_code == 204


async def test_require_role_rejects_unknown_role():
    from app.auth import require_role

    with pytest.raises(ValueError):
        require_role("superuser")


async def test_age_restricted_courses_hidden_on_backend(user_client, moderator_client, client):
    await moderator_client.post("/courses", json=COURSE)
    adult = (await moderator_client.post("/courses", json={**COURSE, "title": "Вино", "min_age": 18})
             ).json()
    listing = await user_client.get("/courses")
    assert [c["title"] for c in listing.json()] == ["Основы SQL"]
    assert listing.headers["x-age-restricted-hidden"] == "1"
    direct = await user_client.get(f"/courses/{adult['id']}")
    assert direct.status_code == 403 and direct.headers["x-error-code"] == "age_verification_required"
    # Записаться на курс 18+ в обход интерфейса тоже нельзя.
    enroll = await user_client.post(
        "/enrollments", json={"student_id": user_client.info["student_id"], "course_id": adult["id"]}
    )
    assert enroll.status_code == 403
    # Модератор видит всё.
    assert len((await moderator_client.get("/courses")).json()) == 2


async def test_age_verified_user_sees_restricted_course(make_user, moderator_client):
    await moderator_client.post("/courses", json={**COURSE, "min_age": 18})
    info = await make_user("grown", age_verified=True)
    async with _new_client() as c:
        c.headers.update(info["headers"])
        resp = await c.get("/courses")
        assert len(resp.json()) == 1 and resp.headers["x-age-restricted-hidden"] == "0"


async def test_cache_does_not_leak_restricted_courses(user_client, moderator_client):
    await moderator_client.post("/courses", json={**COURSE, "min_age": 18})
    # Модератор прогревает кэш списка по преподавателю...
    assert len((await moderator_client.get("/courses", params={"instructor": "Иванов"})).json()) == 1
    # ...но клиент без проверки возраста не получает курс 18+ из кэша.
    assert (await user_client.get("/courses", params={"instructor": "Иванов"})).json() == []


# ============================================================ проверка возраста
async def test_verify_age_from_account_settings(user_client):
    resp = await user_client.post(
        "/auth/verify-age", files={"photo": ("me.jpg", _png(), "image/png")})
    assert resp.status_code == 200
    me = (await user_client.get("/auth/me")).json()
    assert me["is_age_verified"] and me["minimum_age"] == 18 and me["age_verified_at"]


async def test_verify_age_under_18_is_rejected(user_client, monkeypatch):
    monkeypatch.setenv("AGE_ESTIMATOR_MOCK_AGE", "16")
    resp = await user_client.post(
        "/auth/verify-age", files={"photo": ("me.png", _png(), "image/png")})
    assert resp.status_code == 403
    assert (await user_client.get("/auth/me")).json()["is_age_verified"] is False


async def test_verify_age_threshold_is_18_not_21(user_client, monkeypatch):
    # is_adult в BetterAgeVerify — это ≥ 21; для 18+ решаем по predicted_age.
    monkeypatch.setenv("AGE_ESTIMATOR_MOCK_AGE", "19")
    resp = await user_client.post(
        "/auth/verify-age", files={"photo": ("me.png", _png(), "image/png")})
    assert resp.status_code == 200 and resp.json()["category"] == "TEEN"


@pytest.mark.parametrize(
    "content,expected",
    [(b"<svg onload=alert(1)></svg>", 400), (b"not an image", 400), (_png((32, 32)), 422)],
)
async def test_verify_age_rejects_bad_files(user_client, content, expected):
    resp = await user_client.post(
        "/auth/verify-age", files={"photo": ("x.png", content, "image/png")})
    assert resp.status_code == expected


async def test_verify_age_low_confidence_is_rejected(user_client, monkeypatch):
    monkeypatch.setenv("AGE_MIN_CONFIDENCE", "0.95")  # mock отдаёт 0.9
    resp = await user_client.post(
        "/auth/verify-age", files={"photo": ("me.png", _png(), "image/png")})
    assert resp.status_code == 422


async def test_betterageverify_without_weights_returns_503(user_client, monkeypatch, tmp_path):
    from app import age_estimator

    monkeypatch.setenv("AGE_ESTIMATOR_BACKEND", "betterageverify")
    monkeypatch.setenv("BETTERAGEVERIFY_WEIGHTS_DIR", str(tmp_path))
    monkeypatch.setattr(age_estimator, "_estimators", {})
    resp = await user_client.post(
        "/auth/verify-age", files={"photo": ("me.png", _png(), "image/png")})
    assert resp.status_code == 503


# ================================================== профиль, аватар, username
async def test_profile_display_name(user_client):
    resp = await user_client.patch("/users/me/profile", json={"display_name": "  Алиса   К. "})
    assert resp.status_code == 200 and resp.json()["display_name"] == "Алиса К."
    # Внешний URL аватара задать нельзя (трекинг-пиксель).
    bad = await user_client.patch("/users/me/profile",
                                  json={"avatar_url": "https://evil.example/p.gif"})
    assert bad.status_code == 422


async def test_avatar_upload_reencodes_and_serves(user_client):
    up = await user_client.post("/users/me/avatar",
                                files={"file": ("a.png", _png((600, 400)), "image/png")})
    assert up.status_code == 200
    url = up.json()["avatar_url"]
    assert url.startswith(f"/users/{user_client.info['id']}/avatar?v=")
    img = await user_client.get(url)
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"
    # same-site: <img> с фронтенда (другой порт того же сайта) может загрузить аватар.
    assert img.headers["cross-origin-resource-policy"] == "same-site"
    assert Image.open(io.BytesIO(img.content)).size == (256, 256)
    # Удаление.
    assert (await user_client.delete("/users/me/avatar")).status_code == 204
    assert (await user_client.get(url)).status_code == 404


@pytest.mark.parametrize(
    "content",
    [
        b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>',
        b"<svg onload=alert(1)>",
        b"GIF89a....",
        b"\x89PNG\r\n\x1a\n" + b"broken",
    ],
)
async def test_avatar_rejects_svg_and_fake_images(user_client, content):
    # Content-Type от клиента «image/png» не помогает: тип — по магическим байтам.
    resp = await user_client.post("/users/me/avatar",
                                  files={"file": ("a.png", content, "image/png")})
    assert resp.status_code == 415


async def test_avatar_size_limit(user_client, monkeypatch):
    monkeypatch.setenv("AVATAR_MAX_BYTES", "1000")
    big = _png((300, 300)) + b"\0" * 2000  # больше лимита
    resp = await user_client.post("/users/me/avatar",
                                  files={"file": ("a.png", big, "image/png")})
    assert resp.status_code == 413


async def test_avatar_requires_auth(anon_client):
    assert (await anon_client.get("/users/1/avatar")).status_code == 401


async def test_username_change_cooldown_and_uniqueness(user_client, make_user, anon_client):
    await make_user("taken_name")
    taken = await user_client.patch("/users/me/username", json={"new_username": "TAKEN_NAME"})
    assert taken.status_code == 409
    ok = await user_client.patch("/users/me/username", json={"new_username": "alice_new"})
    assert ok.status_code == 200 and ok.json()["username"] == "alice_new"
    assert ok.json()["next_username_change_at"]
    # Токен продолжает работать после смены username (пользователь ищется по id).
    assert (await user_client.get("/auth/me")).json()["username"] == "alice_new"
    again = await user_client.patch("/users/me/username", json={"new_username": "alice_3"})
    assert again.status_code == 429 and "Retry-After" in again.headers
    # Войти можно уже под новым именем.
    assert (await _login(anon_client, "alice_new")).status_code == 200


async def test_moderator_resets_username_without_cooldown(user_client, moderator_client):
    uid = user_client.info["id"]
    await user_client.patch("/users/me/username", json={"new_username": "bad_word"})
    reset = await moderator_client.post(f"/users/{uid}/reset-username")
    assert reset.status_code == 200 and reset.json()["username"] == f"user{uid}"
    # Кулдаун снят — пользователь может сразу выбрать новый ник.
    assert (await user_client.patch("/users/me/username", json={"new_username": "alice_ok"})
            ).status_code == 200


async def test_moderator_sanctions_only_clients(moderator_client, user_client, admin):
    uid = user_client.info["id"]
    assert (await moderator_client.post(f"/users/{uid}/block")).status_code == 200
    assert (await user_client.get("/auth/me")).status_code == 401
    assert (await moderator_client.post(f"/users/{uid}/unblock")).status_code == 200
    # Модератор не может наказать администратора и не может менять роли.
    assert (await moderator_client.post(f"/users/{admin['id']}/block")).status_code == 403
    assert (await moderator_client.post(f"/users/{admin['id']}/reset-username")).status_code == 403
    assert (await moderator_client.patch(f"/users/{uid}", json={"role": "admin"})).status_code == 403


async def test_client_cannot_moderate(user_client, admin):
    assert (await user_client.get("/users")).status_code == 403
    assert (await user_client.post(f"/users/{admin['id']}/reset-username")).status_code == 403


async def test_admin_can_assign_moderator_role(client, user_client):
    uid = user_client.info["id"]
    resp = await client.patch(f"/users/{uid}", json={"role": "moderator"})
    assert resp.status_code == 200 and resp.json()["role"] == "moderator"
    assert (await user_client.post("/courses", json=COURSE)).status_code == 201


# ============================================================== шифрование
def test_totp_secret_encryption_roundtrip(monkeypatch):
    from app import totp

    enc = totp.encrypt_secret("JBSWY3DPEHPK3PXP")
    assert enc != "JBSWY3DPEHPK3PXP" and totp.decrypt_secret(enc) == "JBSWY3DPEHPK3PXP"
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", "another-key")
    assert totp.decrypt_secret(enc) is None  # другим ключом не расшифровать
