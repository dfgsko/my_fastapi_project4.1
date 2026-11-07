"""
/users — профиль, аватар, смена username и модерация (лабораторные № 5 и № 8).

Свой профиль:
  PATCH  /users/me/profile          — display_name (и удаление аватара)
  POST   /users/me/avatar           — загрузка аватара (JPEG/PNG/WebP ≤ 5 МБ)
  DELETE /users/me/avatar           — удалить аватар
  PATCH  /users/me/username         — смена username: раз в 6 месяцев (429)
  GET    /users/{id}/avatar         — картинка аватара (любой вошедший)

Модерация (модератор — только над клиентами, администратор — над всеми):
  GET    /users                     — список пользователей
  POST   /users/{id}/reset-username — принудительный сброс username без кулдауна
  POST   /users/{id}/block, /unblock — санкции: блокировка аккаунта

Администратор:
  PATCH  /users/{id}                — сменить роль / заблокировать
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_LEVEL,
    TokenData,
    get_current_user,
    require_admin,
    require_moderator,
)
from app.config import avatar_max_bytes, username_change_cooldown_days
from app.database import get_db
from app.db_models.user import RefreshToken, User, UserAvatar
from app.images import process_avatar
from app.models.user import MeOut, ProfileUpdate, UserAdminUpdate, UsernameChange, UserOut
from app.routers.auth import me_payload

router = APIRouter(prefix="/users", tags=["users"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _me(session: AsyncSession, current: TokenData) -> User:
    return await session.get(User, current.user_id)


async def _revoke_all(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True)
    )


async def _username_taken(session: AsyncSession, username: str, exclude_id: int) -> bool:
    res = await session.execute(
        select(User.id).where(func.lower(User.username) == username.lower(), User.id != exclude_id)
    )
    return res.first() is not None


# --------------------------------------------------------------- свой профиль
@router.patch("/me/profile", response_model=MeOut, summary="Обновить никнейм / удалить аватар")
async def update_profile(
    payload: ProfileUpdate,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    user = await _me(session, current_user)
    fields = payload.model_fields_set
    if "display_name" in fields:
        user.display_name = payload.display_name
    if "avatar_url" in fields and payload.avatar_url is None:
        user.avatar_url = None
        avatar = await session.get(UserAvatar, user.id)
        if avatar is not None:
            await session.delete(avatar)
    await session.commit()
    return me_payload(user)


@router.post("/me/avatar", response_model=MeOut, summary="Загрузить аватар")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    limit = avatar_max_bytes()
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "Файл больше 5 МБ")
    try:
        webp = process_avatar(data)  # магические байты, запрет SVG, перекодирование
    except ValueError as exc:
        raise HTTPException(415, str(exc))
    user = await _me(session, current_user)
    avatar = await session.get(UserAvatar, user.id)
    if avatar is None:
        session.add(UserAvatar(user_id=user.id, content=webp, content_type="image/webp"))
    else:
        avatar.content, avatar.updated_at = webp, _utcnow()
    # v= меняется при каждой загрузке: браузер не покажет старую картинку из кэша.
    version = hashlib.sha256(webp).hexdigest()[:12]
    user.avatar_url = f"/users/{user.id}/avatar?v={version}"
    await session.commit()
    return me_payload(user)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить аватар")
async def delete_avatar(
    current_user: TokenData = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> None:
    user = await _me(session, current_user)
    avatar = await session.get(UserAvatar, user.id)
    if avatar is not None:
        await session.delete(avatar)
    user.avatar_url = None
    await session.commit()


@router.get(
    "/{user_id}/avatar",
    summary="Аватар пользователя",
    responses={200: {"content": {"image/webp": {}}}, 404: {"description": "Аватара нет"}},
    dependencies=[Depends(get_current_user)],
)
async def get_avatar(user_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    avatar = await session.get(UserAvatar, user_id)
    if avatar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Аватар не найден")
    return Response(
        content=avatar.content,
        media_type=avatar.content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            # Даже если бы в БД оказался HTML, браузер не исполнит его как страницу.
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-site",
        },
    )


@router.patch(
    "/me/username",
    response_model=MeOut,
    summary="Сменить username (не чаще раза в 6 месяцев)",
    responses={409: {"description": "Занят"}, 429: {"description": "Кулдаун ещё не прошёл"}},
)
async def change_username(
    payload: UsernameChange,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    user = await _me(session, current_user)
    if payload.new_username == user.username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Это ваш текущий username")
    if user.username_changed_at:
        cooldown_end = user.username_changed_at + timedelta(days=username_change_cooldown_days())
        if _utcnow() < cooldown_end:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Username можно менять раз в 6 месяцев. "
                f"Следующая смена доступна {cooldown_end.date().isoformat()}",
                headers={"Retry-After": str(int((cooldown_end - _utcnow()).total_seconds()))},
            )
    if await _username_taken(session, payload.new_username, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    user.username = payload.new_username
    user.username_changed_at = _utcnow()
    await session.commit()
    return me_payload(user)


# ----------------------------------------------------------------- модерация
def _ensure_can_moderate(actor: TokenData, target: User) -> None:
    """Модератор применяет санкции только к клиентам; к равным и старшим — нет."""
    if target.id == actor.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя применить к себе")
    if not actor.is_admin and ROLE_LEVEL.get(target.role, 0) >= ROLE_LEVEL.get(actor.role, 0):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для этого пользователя")


async def _target(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Пользователь id={user_id} не найден")
    return user


@router.get("", response_model=List[UserOut], summary="Список пользователей (moderator, admin)")
async def list_users(
    _: TokenData = Depends(require_moderator), session: AsyncSession = Depends(get_db)
) -> List[User]:
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post(
    "/{user_id}/reset-username",
    response_model=UserOut,
    summary="Сбросить username пользователя (moderator, без кулдауна)",
)
async def reset_username(
    user_id: int,
    actor: TokenData = Depends(require_moderator),
    session: AsyncSession = Depends(get_db),
) -> User:
    user = await _target(session, user_id)
    _ensure_can_moderate(actor, user)
    # Нейтральный уникальный ник; кулдаун снимается — пользователь сразу
    # может выбрать новый, нормальный username сам.
    new_name = f"user{user.id}"
    while await _username_taken(session, new_name, user.id):
        new_name = f"user{user.id}_{secrets.token_hex(2)}"
    user.username = new_name
    user.username_changed_at = None
    if user.display_name:
        user.display_name = None  # обычно сбрасывают за оскорбительный ник
    await session.commit()
    await session.refresh(user)
    return user


async def _set_active(user_id: int, active: bool, actor: TokenData, session: AsyncSession) -> User:
    user = await _target(session, user_id)
    _ensure_can_moderate(actor, user)
    user.is_active = active
    if not active:
        await _revoke_all(session, user.id)  # блокировка = выход со всех устройств
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/{user_id}/block", response_model=UserOut, summary="Заблокировать (moderator)")
async def block_user(
    user_id: int, actor: TokenData = Depends(require_moderator),
    session: AsyncSession = Depends(get_db),
) -> User:
    return await _set_active(user_id, False, actor, session)


@router.post("/{user_id}/unblock", response_model=UserOut, summary="Разблокировать (moderator)")
async def unblock_user(
    user_id: int, actor: TokenData = Depends(require_moderator),
    session: AsyncSession = Depends(get_db),
) -> User:
    return await _set_active(user_id, True, actor, session)


@router.patch("/{user_id}", response_model=UserOut, summary="Сменить роль / заблокировать (admin)")
async def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> User:
    user = await _target(session, user_id)
    if user.id == admin.user_id and (
        (payload.role is not None and payload.role != ROLE_ADMIN) or payload.is_active is False
    ):
        # Защита от блокировки доступа: админ не может лишить себя прав.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя понизить или заблокировать себя")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(user, field, value)
    if payload.is_active is False or payload.role is not None:
        # Смена роли или блокировка → все выданные refresh-токены недействительны.
        await _revoke_all(session, user.id)
    await session.commit()
    await session.refresh(user)
    return user


__all__ = ["router", "ROLE_CLIENT"]
