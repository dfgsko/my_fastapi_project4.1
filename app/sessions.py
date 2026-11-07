"""
Сессии на httpOnly cookies и защита от CSRF (лабораторная № 8, шаг 5).

Какие cookie ставит сервер при входе:

  access_token   httpOnly, SameSite=Strict, path=/,             30 минут
  refresh_token  httpOnly, SameSite=Strict, path=/auth/refresh, 7 дней
  csrf_token     НЕ httpOnly (его читает JS), SameSite=Strict,  7 дней

httpOnly: JavaScript страницы не может прочитать токен — XSS-скрипт его не
украдёт. Но браузер сам прикладывает cookie к запросам, и это открывает CSRF.
Защита в два слоя:
  1) SameSite=Strict — cookie не уходят с запросами, начатыми с чужого сайта;
  2) double-submit token — для POST/PUT/PATCH/DELETE с cookie-аутентификацией
     заголовок X-CSRF-Token должен совпадать с cookie csrf_token. Чужой сайт
     не может прочитать нашу cookie и не подставит правильный заголовок.
     Это нужно на случай, когда SameSite не спасает: уязвимый поддомен
     (тот же «сайт»), старые браузеры, ошибка в настройке Lax.

refresh_token ограничен path=/auth/refresh: он не отправляется ни с одним
другим запросом, поэтому его не увидит ни один другой эндпоинт и ни один лог.
"""

import hmac
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    REGISTRATION_COOKIE,
    create_access_token,
    create_refresh_token,
)
from app.config import (
    access_token_expire_minutes,
    cookie_samesite,
    cookie_secure,
    refresh_token_expire_days,
    registration_token_minutes,
)
from app.db_models.user import RefreshToken, User

REFRESH_PATH = "/auth/refresh"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Эндпоинты, где сессии ещё нет (вход, регистрация, второй шаг 2FA,
# подтверждение email по ссылке) — CSRF-токен взять неоткуда.
CSRF_EXEMPT = (
    "/auth/token",
    "/auth/register",
    "/auth/2fa/verify",
    "/auth/verify-email",
)


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _cookie_kwargs() -> dict:
    return {"secure": cookie_secure(), "samesite": cookie_samesite()}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def issue_session(
    session: AsyncSession,
    response: Response,
    user: User,
    request: Request,
    family_id: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> str:
    """
    Выдаёт новую пару токенов и кладёт её в cookie. Возвращает family_id.
    family_id=None — новый вход (новая сессия), иначе — ротация существующей.
    """
    refresh, jti, expires = create_refresh_token(user, family_id)
    family = family_id or jti
    session.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            family_id=family,
            expires_at=_naive_utc(expires),
            user_agent=(request.headers.get("user-agent") or "")[:200] or None,
            ip_address=client_ip(request)[:64],
            session_started_at=started_at or _naive_utc(datetime.now(timezone.utc)),
        )
    )
    await session.commit()

    access = create_access_token(user, session_id=family)
    kw = _cookie_kwargs()
    response.set_cookie(
        ACCESS_COOKIE, access, httponly=True, max_age=access_token_expire_minutes() * 60,
        path="/", **kw,
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, max_age=refresh_token_expire_days() * 86400,
        path=REFRESH_PATH, **kw,
    )
    # CSRF-токен меняется вместе с сессией (при входе и каждой ротации).
    response.set_cookie(
        CSRF_COOKIE, secrets.token_urlsafe(32), httponly=False,
        max_age=refresh_token_expire_days() * 86400, path="/", **kw,
    )
    if REGISTRATION_COOKIE in request.cookies:
        response.delete_cookie(REGISTRATION_COOKIE, path="/auth", **kw)
    return family


def clear_session_cookies(response: Response) -> None:
    kw = _cookie_kwargs()
    response.delete_cookie(ACCESS_COOKIE, path="/", **kw)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, **kw)
    response.delete_cookie(CSRF_COOKIE, path="/", **kw)


def set_registration_cookie(response: Response, token: str) -> None:
    """Короткоживущая cookie незавершённой регистрации (только для /auth/*)."""
    kw = _cookie_kwargs()
    response.set_cookie(
        REGISTRATION_COOKIE, token, httponly=True, max_age=registration_token_minutes() * 60,
        path="/auth", **kw,
    )
    # Шаги регистрации тоже меняют состояние (POST) — им нужен CSRF-токен.
    response.set_cookie(
        CSRF_COOKIE, secrets.token_urlsafe(32), httponly=False,
        max_age=registration_token_minutes() * 60, path="/", **kw,
    )


def _csrf_required(request: Request) -> bool:
    if request.method in SAFE_METHODS:
        return False
    if request.url.path.startswith(CSRF_EXEMPT):
        return False
    # API-клиент с заголовком Authorization не использует cookie: CSRF ему
    # не грозит (чужой сайт не может подставить заголовок).
    if request.headers.get("authorization"):
        return False
    cookies = request.cookies
    return any(c in cookies for c in (ACCESS_COOKIE, REFRESH_COOKIE, REGISTRATION_COOKIE))


def setup_csrf(app: FastAPI) -> None:
    @app.middleware("http")
    async def csrf_middleware(request: Request, call_next):
        if _csrf_required(request):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not header or not hmac.compare_digest(cookie, header):
                return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)
        return await call_next(request)
