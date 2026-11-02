"""
/auth — регистрация, вход, обновление и отзыв токенов.

  POST /auth/register         — создаёт студента и пользователя с ролью user
  POST /auth/token            — вход (OAuth2 password flow): access + refresh
  POST /auth/refresh          — ротация refresh-токена (старый отзывается)
  POST /auth/logout           — отзыв refresh-токена
  POST /auth/change-password  — смена пароля, отзыв всех refresh-токенов
  GET  /auth/me               — кто я
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    ROLE_USER,
    TokenData,
    create_access_token,
    create_refresh_token,
    credentials_exception,
    decode_token,
    get_current_user,
    hash_password,
    verify_dummy_password,
    verify_password,
)
from app.config import auth_rate_limit, registration_enabled
from app.database import get_db
from app.db_models.student import Student as StudentORM
from app.db_models.user import RefreshToken, User
from app.metrics import AUTH_EVENTS
from app.models.user import (
    ChangePasswordRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.redis_client import rate_limit_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


async def _issue_tokens(session: AsyncSession, user: User) -> TokenPair:
    refresh, jti, expires = create_refresh_token(user)
    session.add(RefreshToken(jti=jti, user_id=user.id, expires_at=_naive_utc(expires)))
    await session.commit()
    return TokenPair(access_token=create_access_token(user), refresh_token=refresh)


async def _revoke_all(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация студента (роль user назначается сервером)",
)
async def register(
    payload: RegisterRequest, request: Request, session: AsyncSession = Depends(get_db)
) -> User:
    if not registration_enabled():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Регистрация отключена")
    max_req, window = auth_rate_limit()
    await rate_limit_check(f"rate_limit:register:{_client_ip(request)}", max_req, window)

    student = StudentORM(full_name=payload.full_name, email=payload.email)
    session.add(student)
    try:
        await session.flush()
        user = User(
            username=payload.username,
            hashed_password=hash_password(payload.password),
            role=ROLE_USER,  # роль не приходит от клиента (Mass Assignment)
            student_id=student.id,
        )
        session.add(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Одинаковый ответ для занятого логина и email: не раскрываем, что именно занято.
        raise HTTPException(status.HTTP_409_CONFLICT, "Логин или email уже используются")
    AUTH_EVENTS.labels(event="register").inc()
    return user


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/token", response_model=TokenPair, summary="Вход: получить access и refresh токены")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
) -> TokenPair:
    # Лимиты от брутфорса: по логину (не обойти сменой IP) и по клиентскому IP.
    max_req, window = auth_rate_limit()
    username = form_data.username.strip().lower()
    await rate_limit_check(f"rate_limit:auth:user:{username}", max_req, window)
    await rate_limit_check(f"rate_limit:auth:ip:{_client_ip(request)}", max_req * 3, window)

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        verify_dummy_password(form_data.password)  # выравниваем время ответа
        ok = False
    else:
        ok = verify_password(form_data.password, user.hashed_password)

    if not ok or not user.is_active:
        AUTH_EVENTS.labels(event="login_failure").inc()
        logger.warning("Неудачный вход: user=%r ip=%s", username, _client_ip(request))
        # Одно и то же сообщение для «нет пользователя» и «неверный пароль».
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    AUTH_EVENTS.labels(event="login_success").inc()
    return await _issue_tokens(session, user)


@router.post("/refresh", response_model=TokenPair, summary="Обновить пару токенов (ротация)")
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_db)) -> TokenPair:
    claims = decode_token(payload.refresh_token, "refresh")
    stored = await session.get(RefreshToken, claims.get("jti", ""))
    if stored is None or stored.user_id != claims.get("uid"):
        AUTH_EVENTS.labels(event="refresh_rejected").inc()
        raise credentials_exception()
    if stored.revoked:
        # Повторное предъявление уже использованного токена = возможная кража:
        # отзываем все токены пользователя, войти заново придётся паролем.
        await _revoke_all(session, stored.user_id)
        await session.commit()
        AUTH_EVENTS.labels(event="refresh_reuse").inc()
        logger.warning("Повторное использование refresh-токена, user_id=%s", stored.user_id)
        raise credentials_exception()

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise credentials_exception()

    stored.revoked = True  # ротация: каждый refresh-токен одноразовый
    AUTH_EVENTS.labels(event="refresh").inc()
    return await _issue_tokens(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Отозвать refresh-токен")
async def logout(payload: RefreshRequest, session: AsyncSession = Depends(get_db)) -> None:
    claims = decode_token(payload.refresh_token, "refresh")
    stored = await session.get(RefreshToken, claims.get("jti", ""))
    if stored is not None:
        stored.revoked = True
        await session.commit()
    AUTH_EVENTS.labels(event="logout").inc()


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сменить пароль (все refresh-токены отзываются)",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    user = await session.get(User, current_user.user_id)
    if user is None or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль неверен")
    user.hashed_password = hash_password(payload.new_password)
    await _revoke_all(session, user.id)
    await session.commit()


@router.get("/me", summary="Текущий пользователь")
async def read_users_me(current_user: TokenData = Depends(get_current_user)) -> dict:
    return {
        "username": current_user.username,
        "role": current_user.role,
        "student_id": current_user.student_id,
    }
