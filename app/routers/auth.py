"""
/auth — регистрация, вход, сессии на cookies, email (лабораторные № 5 и № 8).

  POST   /auth/register               — аккаунт с ролью client (email не подтверждён)
  POST   /auth/complete-registration  — после проверки возраста: отправить письмо
  GET    /auth/verify-email?token=    — подтвердить email (одноразовая ссылка)
  POST   /auth/resend-verification    — отправить письмо ещё раз
  POST   /auth/token                  — вход; при 2FA → {"2fa_required", "temp_token"}
  POST   /auth/refresh                — ротация refresh-токена с reuse detection
  POST   /auth/logout                 — завершить текущую сессию
  POST   /auth/logout-all             — выйти со всех устройств
  GET    /auth/sessions               — активные сессии
  DELETE /auth/sessions/{id}          — отозвать сессию
  POST   /auth/change-password        — смена пароля, остальные сессии отзываются
  GET    /auth/me                     — профиль текущего пользователя

Двухфакторная аутентификация — app/routers/auth_2fa.py, проверка возраста —
app/routers/age_verification.py.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import tasks
from app.auth import (
    REFRESH_COOKIE,
    ROLE_CLIENT,
    TokenData,
    create_registration_token,
    create_two_factor_token,
    credentials_exception,
    decode_token,
    extract_access_token,
    get_current_or_registering_user,
    get_current_user,
    hash_password,
    oauth2_scheme,
    verify_dummy_password,
    verify_password,
)
from app.config import (
    age_verification_enabled,
    age_verification_on_registration,
    auth_rate_limit,
    email_resend_cooldown_seconds,
    email_token_hours,
    email_verification_required,
    registration_enabled,
    username_change_cooldown_days,
)
from app.database import get_db
from app.db_models.student import Student as StudentORM
from app.db_models.user import RefreshToken, User
from app.metrics import AUTH_EVENTS
from app.models.user import (
    ChangePasswordRequest,
    CompleteRegistrationRequest,
    MeOut,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    SessionOut,
)
from app.redis_client import rate_limit_check
from app.sessions import (
    clear_session_cookies,
    client_ip,
    issue_session,
    set_registration_cookie,
)
from app.totp import recovery_codes_left

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    """В БД хранится SHA-256 токена из письма: утечка БД не даёт активировать чужой аккаунт."""
    return hashlib.sha256(token.encode()).hexdigest()


def me_payload(user: User) -> dict:
    next_change = None
    if user.username_changed_at:
        next_change = user.username_changed_at + timedelta(days=username_change_cooldown_days())
    return MeOut(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        role=user.role,
        student_id=user.student_id,
        created_at=user.created_at,
        password_changed_at=user.password_changed_at,
        username_changed_at=user.username_changed_at,
        next_username_change_at=next_change,
        totp_enabled=user.totp_enabled,
        totp_enabled_at=user.totp_enabled_at,
        recovery_codes_left=recovery_codes_left(user) if user.totp_enabled else 0,
        is_email_verified=user.is_email_verified,
        email_verified_at=user.email_verified_at,
        is_age_verified=user.is_age_verified,
        age_verified_at=user.age_verified_at,
        minimum_age=user.minimum_age,
        age_verification_required=user.age_verification_required,
        age_verification_available=age_verification_enabled(),
    ).model_dump(mode="json")


async def send_email_verification(session: AsyncSession, user: User) -> None:
    """Новый одноразовый токен (старый перестаёт работать) и письмо через Celery."""
    token = secrets.token_urlsafe(32)
    user.email_verification_token = hash_token(token)
    user.email_verification_sent_at = _utcnow()
    await session.commit()
    try:
        tasks.send_verification_email.delay(user.email, token)
    except Exception as exc:  # noqa: BLE001 — брокер недоступен: письмо можно запросить снова
        logger.error("Не удалось поставить письмо в очередь для user_id=%s: %s", user.id, exc)


# ------------------------------------------------------------ регистрация
@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация (роль client назначается сервером)",
    responses={409: {"description": "Логин или email уже заняты (поле field)"}},
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
):
    if not registration_enabled():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Регистрация отключена")
    max_req, window = auth_rate_limit()
    await rate_limit_check(f"rate_limit:register:{client_ip(request)}", max_req, window)

    # Уникальность без учёта регистра. 409 Conflict: запрос корректен, но
    # конфликтует с существующим ресурсом. Поле указываем, чтобы форма
    # показала ошибку под нужным полем (перебор ограничен rate limit).
    for field, column, value in (
        ("email", User.email, payload.email),
        ("username", User.username, payload.username),
    ):
        taken = await session.execute(select(User.id).where(func.lower(column) == value.lower()))
        if taken.first() is not None:
            text = "Этот email уже зарегистрирован" if field == "email" else "Этот логин уже занят"
            return JSONResponse({"detail": text, "field": field}, status_code=409)

    require_age = age_verification_on_registration()
    student = StudentORM(full_name=payload.full_name or payload.username, email=payload.email)
    session.add(student)
    try:
        await session.flush()
        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            role=ROLE_CLIENT,  # роль не приходит от клиента (Mass Assignment)
            student_id=student.id,
            is_email_verified=False,
            is_age_verified=False,
            age_verification_required=require_age,
            password_changed_at=_utcnow(),
        )
        session.add(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return JSONResponse({"detail": "Логин или email уже используются"}, status_code=409)
    AUTH_EVENTS.labels(event="register").inc()

    if require_age:
        # Письмо не отправляем, пока не пройдена проверка возраста.
        set_registration_cookie(response, create_registration_token(user))
        message = "Аккаунт создан. Подтвердите возраст, чтобы продолжить."
    else:
        await send_email_verification(session, user)
        message = "Аккаунт создан. Проверьте почту, чтобы активировать его."
    return RegisterResponse(
        id=user.id, username=user.username, email=user.email, role=user.role,
        requires_age_verification=require_age, message=message,
    )


@router.post("/complete-registration", summary="Завершить регистрацию: отправить письмо")
async def complete_registration(
    response: Response,
    payload: CompleteRegistrationRequest = Body(default_factory=CompleteRegistrationRequest),
    user: User = Depends(get_current_or_registering_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    user = await session.get(User, user.id)
    if payload.skip_age_verification and not user.is_age_verified:
        # Проверка возраста не обязательна: без неё аккаунт работает, но
        # курсы 18+ скрыты (минимизация данных — не собираем лишнего).
        user.age_verification_required = False
    if user.age_verification_required and not user.is_age_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Age verification not completed")
    if user.is_email_verified:
        await session.commit()
        return {"detail": "Email уже подтверждён", "email_sent": False}
    await send_email_verification(session, user)
    response.delete_cookie("registration_token", path="/auth")
    return {"detail": "Verification email sent. Please check your inbox.", "email_sent": True,
            "email": user.email}


@router.get("/verify-email", summary="Подтвердить email по ссылке из письма")
async def verify_email(token: str, session: AsyncSession = Depends(get_db)) -> dict:
    if not token or len(token) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна")
    result = await session.execute(
        select(User).where(User.email_verification_token == hash_token(token))
    )
    user = result.scalar_one_or_none()
    if user is None:
        # Нет такого токена: неверная ссылка или уже использованная (одноразовая).
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна или уже использована")
    sent = user.email_verification_sent_at or datetime.min
    if _utcnow() - sent > timedelta(hours=email_token_hours()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Срок действия ссылки истёк")
    user.is_email_verified = True
    user.email_verified_at = _utcnow()
    user.email_verification_token = None  # одноразовая ссылка
    await session.commit()
    AUTH_EVENTS.labels(event="email_verified").inc()
    return {"detail": "Email подтверждён. Теперь вы можете войти."}


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Отправить письмо подтверждения ещё раз",
)
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest = Body(default_factory=ResendVerificationRequest),
    bearer: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> dict:
    generic = {"detail": "Если адрес зарегистрирован и не подтверждён, письмо отправлено."}
    user: Optional[User] = None
    try:
        user = await get_current_or_registering_user(request, bearer, session)
    except HTTPException:
        if payload.email:
            max_req, window = auth_rate_limit()
            await rate_limit_check(f"rate_limit:resend:{client_ip(request)}", max_req, window)
            res = await session.execute(select(User).where(User.email == payload.email.lower()))
            user = res.scalar_one_or_none()
    if user is None or user.is_email_verified or not user.email:
        return generic  # одинаковый ответ: не раскрываем, есть ли такой email
    if user.age_verification_required and not user.is_age_verified:
        return generic
    sent = user.email_verification_sent_at
    if sent and (_utcnow() - sent).total_seconds() < email_resend_cooldown_seconds():
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Подождите минуту перед повтором")
    await send_email_verification(session, user)
    return generic


# ------------------------------------------------------------------- вход
@router.post(
    "/token",
    summary="Вход: токены в httpOnly cookie; при 2FA — temp_token для второго шага",
    responses={
        200: {"description": "Вход выполнен (cookie) или требуется код 2FA"},
        401: {"description": "Неверный логин или пароль"},
        403: {"description": "Email не подтверждён / не пройдена проверка возраста"},
    },
)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
):
    # Лимиты от брутфорса: по логину (не обойти сменой IP) и по клиентскому IP.
    max_req, window = auth_rate_limit()
    login_name = form_data.username.strip().lower()
    await rate_limit_check(f"rate_limit:auth:user:{login_name}", max_req, window)
    await rate_limit_check(f"rate_limit:auth:ip:{client_ip(request)}", max_req * 3, window)

    # Входить можно по логину или по email.
    result = await session.execute(
        select(User).where(or_(User.username == login_name, User.email == login_name))
    )
    user = result.scalar_one_or_none()
    if user is None:
        verify_dummy_password(form_data.password)  # выравниваем время ответа
        ok = False
    else:
        ok = verify_password(form_data.password, user.hashed_password)

    if not ok or not user.is_active:
        AUTH_EVENTS.labels(event="login_failure").inc()
        logger.warning("Неудачный вход: user=%r ip=%s", login_name, client_ip(request))
        # Одно и то же сообщение для «нет пользователя» и «неверный пароль».
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Пароль верный, но аккаунт ещё не активирован.
    if user.age_verification_required and not user.is_age_verified:
        resp = JSONResponse(
            {"detail": "Пройдите верификацию возраста, чтобы активировать аккаунт",
             "code": "age_verification_required"},
            status_code=403,
        )
        set_registration_cookie(resp, create_registration_token(user))  # можно продолжить
        return resp
    if email_verification_required() and not user.is_email_verified:
        return JSONResponse(
            {"detail": "Email not verified. Please check your inbox.",
             "code": "email_not_verified"},
            status_code=403,
        )

    if user.totp_enabled:
        # Второй фактор: access-токен не выдаём, только temp_token на 5 минут,
        # который принимает лишь POST /auth/2fa/verify.
        AUTH_EVENTS.labels(event="login_2fa_required").inc()
        return {"2fa_required": True, "temp_token": create_two_factor_token(user)}

    AUTH_EVENTS.labels(event="login_success").inc()
    await issue_session(session, response, user, request)
    return {"message": "Logged in", "user": me_payload(user)}


async def _revoke_family(session: AsyncSession, user_id: int, family_id: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.family_id == family_id)
        .values(revoked=True)
    )


async def _revoke_all(session: AsyncSession, user_id: int, keep_family: Optional[str] = None):
    stmt = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)
    )
    if keep_family:
        stmt = stmt.where(
            or_(RefreshToken.family_id.is_(None), RefreshToken.family_id != keep_family)
        )
    await session.execute(stmt.values(revoked=True))


@router.post("/refresh", summary="Обновить пару токенов (ротация + reuse detection)")
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest = Body(default_factory=RefreshRequest),
    session: AsyncSession = Depends(get_db),
) -> dict:
    token = request.cookies.get(REFRESH_COOKIE) or payload.refresh_token
    if not token:
        raise credentials_exception("Refresh token missing")
    claims = decode_token(token, "refresh")
    stored = await session.get(RefreshToken, claims.get("jti", ""))
    if stored is None or stored.user_id != claims.get("uid"):
        AUTH_EVENTS.labels(event="refresh_rejected").inc()
        raise credentials_exception()
    if stored.revoked:
        family = stored.family_id or stored.jti
        alive = await session.execute(
            select(RefreshToken.jti).where(
                RefreshToken.family_id == family, RefreshToken.revoked.is_(False)
            ).limit(1)
        )
        if alive.first() is None:
            # Сессию завершили штатно (выход, смена пароля, отзыв в настройках):
            # это не кража, просто 401 — остальные сессии не трогаем.
            clear_session_cookies(response)
            raise credentials_exception("Session ended")
        # Reuse detection: токен уже заменён ротацией, а в семье есть более
        # новый. Значит, копия у кого-то ещё (кража) — отзываем ВСЁ.
        await _revoke_all(session, stored.user_id)
        await session.commit()
        AUTH_EVENTS.labels(event="refresh_reuse").inc()
        logger.warning("Повторное использование refresh-токена, user_id=%s", stored.user_id)
        clear_session_cookies(response)
        raise credentials_exception("Refresh token reuse detected")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise credentials_exception()

    stored.revoked = True  # ротация: каждый refresh-токен одноразовый
    AUTH_EVENTS.labels(event="refresh").inc()
    await issue_session(
        session, response, user, request,
        family_id=stored.family_id or stored.jti,
        started_at=stored.session_started_at or stored.created_at,
    )
    return {"message": "Refreshed"}


async def _current_sid(request: Request, bearer: Optional[str]) -> Optional[dict]:
    token = extract_access_token(request, bearer)
    if not token:
        return None
    try:
        return decode_token(token, "access")
    except HTTPException:
        return None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Завершить текущую сессию")
async def logout(
    request: Request,
    response: Response,
    payload: RefreshRequest = Body(default_factory=RefreshRequest),
    bearer: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> Response:
    # refresh_token в cookie сюда не приходит (path=/auth/refresh), поэтому
    # сессию находим по sid из access-токена; API-клиент может передать refresh.
    claims = await _current_sid(request, bearer)
    if claims and claims.get("sid"):
        await _revoke_family(session, claims["uid"], claims["sid"])
    elif payload.refresh_token:
        try:
            rclaims = decode_token(payload.refresh_token, "refresh")
            stored = await session.get(RefreshToken, rclaims.get("jti", ""))
            if stored is not None:
                await _revoke_family(session, stored.user_id, stored.family_id or stored.jti)
                stored.revoked = True
        except HTTPException:
            pass
    await session.commit()
    AUTH_EVENTS.labels(event="logout").inc()
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(out)
    return out


@router.post(
    "/logout-all", status_code=status.HTTP_204_NO_CONTENT, summary="Выйти со всех устройств"
)
async def logout_all(
    current_user: TokenData = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> Response:
    await _revoke_all(session, current_user.user_id)
    await session.commit()
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(out)
    return out


@router.get("/sessions", response_model=List[SessionOut], summary="Активные сессии")
async def list_sessions(
    current_user: TokenData = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> List[SessionOut]:
    rows = await session.execute(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == current_user.user_id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > _utcnow(),
        )
        .order_by(RefreshToken.created_at.desc())
    )
    seen: dict[str, SessionOut] = {}
    for t in rows.scalars():
        fam = t.family_id or t.jti
        if fam in seen:
            continue
        seen[fam] = SessionOut(
            id=fam,
            user_agent=t.user_agent,
            ip_address=t.ip_address,
            started_at=t.session_started_at or t.created_at,
            last_active_at=t.created_at,
            expires_at=t.expires_at,
            current=fam == current_user.session_id,
        )
    return list(seen.values())


@router.delete(
    "/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Отозвать сессию"
)
async def revoke_session(
    session_id: str,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    exists = await session.execute(
        select(RefreshToken.jti).where(
            RefreshToken.user_id == current_user.user_id, RefreshToken.family_id == session_id
        ).limit(1)
    )
    if exists.first() is None:
        # Чужие и несуществующие сессии неотличимы (BOLA).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сессия не найдена")
    await _revoke_family(session, current_user.user_id, session_id)
    await session.commit()
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    if session_id == current_user.session_id:
        clear_session_cookies(out)
    return out


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сменить пароль (все остальные сессии отзываются)",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    user = await session.get(User, current_user.user_id)
    # Текущий пароль спрашиваем даже у авторизованного: иначе любой, кто
    # получил доступ к открытой вкладке (или украл cookie), сменил бы пароль
    # и отобрал аккаунт. 400, а не 401: 401 фронтенд воспринял бы как
    # «сессия истекла» и попытался обновить токен.
    if user is None or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль неверен")
    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Новый пароль совпадает с текущим")
    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = _utcnow()
    # Украденный refresh-токен не должен пережить смену пароля: отзываем все
    # сессии, кроме текущей (пользователь не выкидывается из своей вкладки).
    await _revoke_all(session, user.id, keep_family=current_user.session_id)
    await session.commit()
    AUTH_EVENTS.labels(event="password_changed").inc()


@router.get("/me", response_model=MeOut, summary="Текущий пользователь")
async def read_users_me(
    current_user: TokenData = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> dict:
    user = await session.get(User, current_user.user_id)
    return me_payload(user)
