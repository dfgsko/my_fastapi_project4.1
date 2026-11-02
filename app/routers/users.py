"""/users — управление пользователями (только администратор)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenData, require_admin
from app.database import get_db
from app.db_models.user import RefreshToken, User
from app.models.user import UserAdminUpdate, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[UserOut], summary="Список пользователей (admin)")
async def list_users(
    _: TokenData = Depends(require_admin), session: AsyncSession = Depends(get_db)
) -> List[User]:
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.patch("/{user_id}", response_model=UserOut, summary="Сменить роль / заблокировать (admin)")
async def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Пользователь id={user_id} не найден")
    if user.id == admin.user_id and (payload.role == "user" or payload.is_active is False):
        # Защита от блокировки доступа: админ не может лишить себя прав.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя понизить или заблокировать себя")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(user, field, value)
    if payload.is_active is False or payload.role is not None:
        # Смена роли или блокировка → все выданные refresh-токены недействительны.
        await session.execute(
            update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True)
        )
    await session.commit()
    await session.refresh(user)
    return user
