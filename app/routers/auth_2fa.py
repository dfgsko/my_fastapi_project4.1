"""
/auth/2fa — двухфакторная аутентификация по TOTP (лабораторная № 8, шаг 1).

  POST /auth/2fa/enable          — новый секрет + QR-код (2FA ещё НЕ активна)
  POST /auth/2fa/confirm         — первый код из приложения → totp_enabled = true
  POST /auth/2fa/verify          — второй шаг входа: temp_token + код → сессия
  POST /auth/2fa/disable         — нужен действующий код; секрет удаляется
  POST /auth/2fa/recovery-codes  — новые коды восстановления (нужен код)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import totp
from app.auth import TokenData, credentials_exception, decode_token, get_current_user
from app.database import get_db
from app.db_models.user import User
from app.metrics import AUTH_EVENTS
from app.models.user import TwoFactorCodeRequest, TwoFactorVerifyRequest
from app.redis_client import cache_get, cache_set, rate_limit_check
from app.routers.auth import me_payload
from app.sessions import issue_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/2fa", tags=["2fa"])

# Не больше 5 попыток ввести код за 5 минут: 6 цифр — это всего 10⁶
# вариантов, без лимита их перебрали бы за минуты.
CODE_ATTEMPTS, CODE_WINDOW = 5, 300


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _user(session: AsyncSession, current: TokenData) -> User:
    user = await session.get(User, current.user_id)
    if user is None:
        raise credentials_exception()
    return user


@router.post("/enable", summary="Начать включение 2FA: секрет и QR-код")
async def enable_2fa(
    current_user: TokenData = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> dict:
    user = await _user(session, current_user)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA уже включена")
    secret = totp.new_secret()
    user.totp_secret = totp.encrypt_secret(secret)  # в БД — только шифротекст
    user.totp_enabled = False  # не активна до подтверждения первым кодом
    user.totp_last_timestep = None
    await session.commit()
    uri = totp.provisioning_uri(secret, user.email or user.username)
    # Секрет показывается один раз — для ручного ввода, если QR не сканируется.
    return {"qr_code": totp.qr_png_base64(uri), "secret": secret, "otpauth_uri": uri}


@router.post("/confirm", summary="Подтвердить 2FA первым кодом из приложения")
async def confirm_2fa(
    payload: TwoFactorCodeRequest,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await rate_limit_check(f"rate_limit:2fa:{current_user.user_id}", CODE_ATTEMPTS, CODE_WINDOW)
    user = await _user(session, current_user)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA уже включена")
    if not user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сначала вызовите /auth/2fa/enable")
    if not totp.verify_code(user, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid TOTP code")
    user.totp_enabled = True
    user.totp_enabled_at = _utcnow()
    codes = totp.generate_recovery_codes(user)
    await session.commit()
    AUTH_EVENTS.labels(event="2fa_enabled").inc()
    # Коды восстановления показываются один раз; в БД — только их хэши.
    return {"detail": "2FA enabled", "recovery_codes": codes}


@router.post("/verify", summary="Второй шаг входа: temp_token + код → сессия")
async def verify_2fa(
    payload: TwoFactorVerifyRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> dict:
    claims = decode_token(payload.temp_token, "2fa_pending")
    uid = claims.get("uid")
    await rate_limit_check(f"rate_limit:2fa:{uid}", CODE_ATTEMPTS, CODE_WINDOW)
    jti = claims.get("jti", "")
    if await cache_get(f"2fa_used:{jti}"):
        raise credentials_exception("Temp token already used")
    user = await session.get(User, uid) if isinstance(uid, int) else None
    if user is None or not user.is_active or not user.totp_enabled:
        raise credentials_exception()
    if not totp.verify_code_or_recovery(user, payload.code):
        await session.commit()  # мог измениться счётчик — не страшно
        AUTH_EVENTS.labels(event="2fa_failure").inc()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный код")
    await cache_set(f"2fa_used:{jti}", True, 600)  # temp_token одноразовый
    AUTH_EVENTS.labels(event="login_success").inc()
    await issue_session(session, response, user, request)
    return {"message": "Logged in", "user": me_payload(user)}


@router.post("/disable", summary="Отключить 2FA (нужен действующий код)")
async def disable_2fa(
    payload: TwoFactorCodeRequest,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await rate_limit_check(f"rate_limit:2fa:{current_user.user_id}", CODE_ATTEMPTS, CODE_WINDOW)
    user = await _user(session, current_user)
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA не включена")
    # Код требуется даже от авторизованного: украденная сессия не должна
    # позволять снять второй фактор.
    if not totp.verify_code_or_recovery(user, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный код")
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_enabled_at = None
    user.totp_last_timestep = None
    user.totp_recovery_codes = None
    await session.commit()
    AUTH_EVENTS.labels(event="2fa_disabled").inc()
    return {"detail": "2FA disabled"}


@router.post("/recovery-codes", summary="Выпустить новые коды восстановления")
async def regenerate_recovery_codes(
    payload: TwoFactorCodeRequest,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await rate_limit_check(f"rate_limit:2fa:{current_user.user_id}", CODE_ATTEMPTS, CODE_WINDOW)
    user = await _user(session, current_user)
    if not user.totp_enabled or not totp.verify_code(user, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный код")
    codes = totp.generate_recovery_codes(user)
    await session.commit()
    return {"recovery_codes": codes}
