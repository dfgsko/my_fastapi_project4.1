"""ORM-модели пользователей и refresh-токенов (лабораторная № 5)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    # bcrypt-хэш; пароль в открытом виде нигде не хранится и не логируется.
    hashed_password: Mapped[str] = mapped_column(String(100), nullable=False)
    # admin | user — роль назначает только администратор (защита от Mass Assignment).
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Связь «пользователь → студент»: на ней строится защита от BOLA.
    student_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class RefreshToken(Base):
    """
    Выданные refresh-токены (по jti). Хранение в БД позволяет отозвать токен
    (logout, смена пароля, подозрение на кражу) — чистый JWT этого не умеет.
    """

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
