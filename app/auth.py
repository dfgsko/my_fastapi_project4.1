"""
Аутентификация и авторизация (лабораторная № 5): пароли, JWT, роли.

Схема: access-токен (30 мин) + refresh-токен (7 дней, хранится в БД по jti
и может быть отозван). Алгоритм HS256, ключ — SECRET_KEY из Vault.

Отличия от шаблона методички (и почему):
  • PyJWT + bcrypt вместо python-jose + passlib: python-jose слабо
    поддерживается и имел CVE (в т.ч. по обработке алгоритма), а passlib
    несовместим с bcrypt ≥ 4.1;
  • `algorithms=[ALG]` и обязательные claims (`exp`, `sub`, `type`) при
    декодировании — защита от alg=none и токенов без срока действия;
  • тип токена проверяется: refresh нельзя использовать как access и наоборот;
  • пользователь перечитывается из БД на каждый запрос: деактивация и смена
    роли действуют сразу, а не через 30 минут (до истечения access-токена);
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
from fastapi import Depends, HTTPException, status
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
)
from app.database import get_db
from app.db_models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_ADMIN, ROLE_USER)

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


def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    now = _now()
    claims = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,  # справочно; решения принимаются по роли из БД
        "type": "access",
        "iat": now,
        "exp": now + (expires_delta or timedelta(minutes=access_token_expire_minutes())),
    }
    return jwt.encode(claims, get_secret_key(), algorithm=jwt_algorithm())


def create_refresh_token(user: User) -> tuple[str, str, datetime]:
    """Возвращает (токен, jti, expires_at). jti сохраняется в таблице refresh_tokens."""
    now = _now()
    jti = uuid.uuid4().hex
    expires = now + timedelta(days=refresh_token_expire_days())
    claims = {
        "sub": user.username,
        "uid": user.id,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(claims, get_secret_key(), algorithm=jwt_algorithm()), jti, expires


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


# ------------------------------------------------------- текущий пользователь
@dataclass
class TokenData:
    """Аутентифицированный пользователь (данные берутся из БД, не из токена)."""

    user_id: int
    username: str
    role: str
    student_id: Optional[int] = None

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


async def get_current_user(
    token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_db)
) -> TokenData:
    payload = decode_token(token, "access")
    result = await session.execute(select(User).where(User.username == payload["sub"]))
    user = result.scalar_one_or_none()
    # uid в токене должен совпадать с пользователем: имя могли переиспользовать.
    if user is None or not user.is_active or user.id != payload.get("uid"):
        raise credentials_exception()
    return TokenData(
        user_id=user.id, username=user.username, role=user.role, student_id=user.student_id
    )


async def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Зависимость: только роль admin (иначе 403)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user
