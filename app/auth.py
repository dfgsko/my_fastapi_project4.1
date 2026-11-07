"""
Аутентификация и авторизация (лабораторные № 5 и № 8): пароли, JWT, роли.

Схема: access-токен (30 мин) + refresh-токен (7 дней, хранится в БД по jti
и может быть отозван). Алгоритм HS256, ключ — SECRET_KEY из Vault.

С лабораторной № 8 токены живут в httpOnly cookie (см. app/sessions.py):
JavaScript страницы их не видит, поэтому XSS не может их украсть. Заголовок
Authorization: Bearer по-прежнему принимается — для Swagger, CLI и тестов.

Типы токенов (claim `type`), каждый принимается только своим эндпоинтом:
  access        — обычные запросы к API;
  refresh       — только POST /auth/refresh;
  2fa_pending   — только POST /auth/2fa/verify (пароль верный, ждём код);
  registration  — только шаги незавершённой регистрации (проверка возраста).

Отличия от шаблона методички (и почему):
  • PyJWT + bcrypt вместо python-jose + passlib: python-jose слабо
    поддерживается и имел CVE, а passlib несовместим с bcrypt ≥ 4.1;
  • `algorithms=[ALG]` и обязательные claims (`exp`, `sub`, `type`) при
    декодировании — защита от alg=none и токенов без срока действия;
  • пользователь перечитывается из БД на каждый запрос (по uid, а не по
    username — username теперь можно менять): деактивация и смена роли
    действуют сразу, а не через 30 минут;
  • при неизвестном пользователе всё равно выполняется проверка bcrypt —
    время ответа не выдаёт, существует ли логин (timing attack).
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    access_token_expire_minutes,
    bcrypt_rounds,
    get_secret_key,
    jwt_algorithm,
    password_min_length,
    refresh_token_expire_days,
    registration_token_minutes,
    two_factor_temp_token_minutes,
)
from app.database import get_db
from app.db_models.user import User

# auto_error=False: токен может прийти и в cookie, а не только в заголовке.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
REGISTRATION_COOKIE = "registration_token"

ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"
ROLE_CLIENT = "client"
ROLE_USER = ROLE_CLIENT  # совместимость со старым кодом (роль user из лаб. № 5)
ROLES = (ROLE_CLIENT, ROLE_MODERATOR, ROLE_ADMIN)
# Иерархия: каждая следующая роль умеет всё, что предыдущая.
ROLE_LEVEL = {ROLE_CLIENT: 0, ROLE_MODERATOR: 1, ROLE_ADMIN: 2}

_BCRYPT_MAX_BYTES = 72


# ---------------------------------------------------------------- пароли
def validate_password_policy(password: str) -> str:
    """Политика паролей: длина, буква и цифра, ограничение bcrypt (72 байта)."""
    min_len = password_min_length()
    if len(password) < min_len:
        raise ValueError(f"Пароль должен быть не короче {min_len} символов")
    if len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError("Пароль слишком длинный (максимум 72 байта)")
    if not re.search(r"[A-Za-zА-Яа-яЁё]", password) or not re.search(r"\d", password):
        raise ValueError("Пароль должен содержать и буквы, и цифры")
    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8")[:_BCRYPT_MAX_BYTES], bcrypt.gensalt(rounds=bcrypt_rounds())
    ).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES], hashed_password.encode("ascii")
        )
    except ValueError:
        return False


_dummy_hash: Optional[str] = None


def verify_dummy_password(plain_password: str) -> None:
    """Выравнивает время ответа для несуществующего логина."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("dummy-password-1")
    verify_password(plain_password, _dummy_hash)


# ------------------------------------------------------------------ токены
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(claims: dict) -> str:
    return jwt.encode(claims, get_secret_key(), algorithm=jwt_algorithm())


def create_access_token(
    user: User, expires_delta: Optional[timedelta] = None, session_id: Optional[str] = None
) -> str:
    now = _now()
    claims = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,  # справочно; решения принимаются по роли из БД
        "type": "access",
        "iat": now,
        "exp": now + (expires_delta or timedelta(minutes=access_token_expire_minutes())),
    }
    if session_id:
        # sid = family_id refresh-токена: по нему logout отзывает именно
        # эту сессию, а список сессий помечает «текущую».
        claims["sid"] = session_id
    return _encode(claims)


def create_refresh_token(user: User, family_id: Optional[str] = None) -> tuple[str, str, datetime]:
    """Возвращает (токен, jti, expires_at). jti сохраняется в таблице refresh_tokens."""
    now = _now()
    jti = uuid.uuid4().hex
    expires = now + timedelta(days=refresh_token_expire_days())
    claims = {
        "sub": user.username,
        "uid": user.id,
        "type": "refresh",
        "jti": jti,
        "fam": family_id or jti,
        "iat": now,
        "exp": expires,
    }
    return _encode(claims), jti, expires


def create_two_factor_token(user: User) -> str:
    """temp_token: пароль проверен, но доступ появится только после кода 2FA."""
    now = _now()
    return _encode(
        {
            "sub": user.username,
            "uid": user.id,
            "type": "2fa_pending",
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + timedelta(minutes=two_factor_temp_token_minutes()),
        }
    )


def create_registration_token(user: User) -> str:
    """Токен незавершённой регистрации: даёт доступ только к шагу проверки возраста."""
    now = _now()
    return _encode(
        {
            "sub": user.username,
            "uid": user.id,
            "type": "registration",
            "iat": now,
            "exp": now + timedelta(minutes=registration_token_minutes()),
        }
    )


def credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_token(token: str, expected_type: str) -> dict:
    """Проверяет подпись, срок действия, обязательные claims и тип токена."""
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=[jwt_algorithm()],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError:
        raise credentials_exception()
    if payload.get("type") != expected_type:
        raise credentials_exception()
    return payload


def extract_access_token(request: Request, bearer: Optional[str]) -> Optional[str]:
    """Сначала заголовок Authorization (API-клиенты), затем httpOnly cookie (SPA)."""
    return bearer or request.cookies.get(ACCESS_COOKIE)


# ------------------------------------------------------- текущий пользователь
@dataclass
class TokenData:
    """Аутентифицированный пользователь (данные берутся из БД, не из токена)."""

    user_id: int
    username: str
    role: str
    student_id: Optional[int] = None
    session_id: Optional[str] = None
    is_age_verified: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_moderator(self) -> bool:
        """Модератор или выше (администратор умеет всё, что модератор)."""
        return ROLE_LEVEL.get(self.role, -1) >= ROLE_LEVEL[ROLE_MODERATOR]


async def session_is_active(session: AsyncSession, user_id: int, family_id: str) -> bool:
    from app.db_models.user import RefreshToken

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = await session.execute(
        select(RefreshToken.jti).where(
            RefreshToken.user_id == user_id,
            RefreshToken.family_id == family_id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > now,
        ).limit(1)
    )
    return row.first() is not None


async def _load_user(session: AsyncSession, payload: dict) -> User:
    uid = payload.get("uid")
    user = await session.get(User, uid) if isinstance(uid, int) else None
    if user is None or not user.is_active:
        raise credentials_exception()
    return user


async def get_current_user(
    request: Request,
    bearer: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> TokenData:
    token = extract_access_token(request, bearer)
    if not token:
        raise credentials_exception("Not authenticated")
    payload = decode_token(token, "access")
    user = await _load_user(session, payload)
    sid = payload.get("sid")
    if sid and not await session_is_active(session, user.id, sid):
        # Сессию отозвали (выход, «выйти со всех устройств», смена пароля):
        # access-токен этой сессии перестаёт работать сразу, а не через 30 минут.
        raise credentials_exception("Session revoked")
    return TokenData(
        user_id=user.id,
        username=user.username,
        role=user.role,
        student_id=user.student_id,
        session_id=payload.get("sid"),
        is_age_verified=user.is_age_verified,
    )


async def get_optional_user(
    request: Request,
    bearer: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> Optional[TokenData]:
    """Как get_current_user, но для публичных эндпоинтов: аноним → None."""
    if not extract_access_token(request, bearer):
        return None
    try:
        return await get_current_user(request, bearer, session)
    except HTTPException:
        return None


async def get_current_or_registering_user(
    request: Request,
    bearer: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """
    Для шагов регистрации (проверка возраста, завершение регистрации):
    подходит обычная сессия ИЛИ registration-токен из cookie, который
    выдаётся при POST /auth/register и больше ни на что не годится.
    """
    token = extract_access_token(request, bearer)
    if token:
        return await _load_user(session, decode_token(token, "access"))
    reg = request.cookies.get(REGISTRATION_COOKIE)
    if not reg:
        raise credentials_exception("Not authenticated")
    return await _load_user(session, decode_token(reg, "registration"))


def require_role(*allowed_roles: str):
    """
    Зависимость-фабрика: пропускает только перечисленные роли, иначе 403.

        @router.post("/courses", dependencies=[Depends(require_role("moderator", "admin"))])
    """
    unknown = set(allowed_roles) - set(ROLES)
    if unknown:
        raise ValueError(f"Неизвестные роли: {unknown}")

    async def checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return current_user

    return checker


async def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Зависимость: только роль admin (иначе 403)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user


require_moderator = require_role(ROLE_MODERATOR, ROLE_ADMIN)
