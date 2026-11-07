"""
ORM-модели пользователей, сессий и аватаров (лабораторные № 5 и № 8).

Какие поля хранятся и зачем — см. раздел «Какие данные мы храним» в README.
Коротко: всё, что можно украсть и использовать (пароль, секрет 2FA, коды
восстановления, токен подтверждения email), хранится только в виде хэша или
в зашифрованном виде.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    # Email для входа, подтверждения и уведомлений. NULL допустим только у
    # bootstrap-администратора, созданного из Secret без почты.
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True, unique=True)
    # bcrypt-хэш; пароль в открытом виде нигде не хранится и не логируется.
    hashed_password: Mapped[str] = mapped_column(String(100), nullable=False)
    # client | moderator | admin. Назначает только администратор (Mass Assignment).
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="client")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Связь «пользователь → студент»: на ней строится защита от BOLA.
    student_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # --- Профиль (шаг 8) ---
    display_name: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    # Ссылка на аватар внутри API (/users/{id}/avatar?v=...), не внешний URL.
    avatar_url: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    username_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # --- 2FA / TOTP (шаг 1) ---
    # Секрет зашифрован (Fernet, ключ из TOTP_ENCRYPTION_KEY / SECRET_KEY).
    totp_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    totp_enabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Номер последнего принятого 30-секундного интервала: один код нельзя
    # предъявить дважды (защита от повторного использования перехваченного кода).
    totp_last_timestep: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # JSON-список SHA-256 хэшей одноразовых кодов восстановления.
    totp_recovery_codes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Подтверждение email (шаг 9) ---
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # SHA-256 от токена из письма; сам токен в БД не попадает.
    email_verification_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    email_verification_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # --- Возрастная верификация (шаг 10) ---
    # Храним только результат «прошёл/не прошёл» и порог, но не фото,
    # не дату рождения и не оценённый возраст (минимизация данных).
    is_age_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    age_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    minimum_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # True — аккаунт не активируется, пока возраст не подтверждён.
    # Пользователь может отказаться: тогда False, а контент 18+ ему скрыт.
    age_verification_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class RefreshToken(Base):
    """
    Выданные refresh-токены (по jti). Хранение в БД позволяет отозвать токен
    (logout, смена пароля, подозрение на кражу) — чистый JWT этого не умеет.

    family_id — «сессия»: при ротации jti меняется, а family_id остаётся.
    Список активных сессий в настройках аккаунта — это список семейств.
    """

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    # Для списка сессий: устройство (User-Agent, обрезан) и IP входа.
    user_agent: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Когда сессия началась (вход паролем) — переносится при ротации.
    session_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserAvatar(Base):
    """
    Аватар пользователя. Картинка перекодируется сервером в WebP 256×256
    (≈10–30 КБ), поэтому хранится прямо в БД: не нужен отдельный бакет, а
    удаление пользователя каскадно удаляет и аватар.
    """

    __tablename__ = "user_avatars"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="image/webp")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
