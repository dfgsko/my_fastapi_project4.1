"""Pydantic-схемы пользователей, сессий и профиля (лабораторные № 5 и № 8)."""

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth import validate_password_policy


class StrictModel(BaseModel):
    """
    Запрещает лишние поля во входных данных (защита от Mass Assignment,
    OWASP API3): {"role": "admin"} в теле регистрации даст 422, а не молча
    проигнорируется — и не окажется в БД, если кто-то добавит поле в ORM.
    """

    model_config = ConfigDict(extra="forbid")


_USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")


def _check_username(v: str) -> str:
    if not _USERNAME.match(v):
        raise ValueError("Логин: 3–50 символов (латиница, цифры, _ . -)")
    return v.lower()


class RegisterRequest(StrictModel):
    username: str = Field(..., examples=["anna_s"])
    email: EmailStr
    password: str = Field(..., examples=["Str0ng-passw0rd"])
    # ФИО студента; если не указано, в карточку студента пойдёт логин.
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return _check_username(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_policy(v)


class RegisterResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    requires_age_verification: bool
    message: str


class RefreshRequest(StrictModel):
    """Для API-клиентов без cookie; SPA передаёт refresh-токен в cookie."""

    refresh_token: Optional[str] = None


class ChangePasswordRequest(StrictModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_policy(v)


class TwoFactorVerifyRequest(StrictModel):
    temp_token: str
    code: str = Field(..., min_length=6, max_length=20)


class TwoFactorCodeRequest(StrictModel):
    code: str = Field(..., min_length=6, max_length=20)


class CompleteRegistrationRequest(StrictModel):
    # True — пользователь отказался от проверки возраста: аккаунт
    # активируется, а контент 18+ ему будет скрыт.
    skip_age_verification: bool = False


class ResendVerificationRequest(StrictModel):
    email: Optional[EmailStr] = None


class SessionOut(BaseModel):
    id: str
    user_agent: Optional[str]
    ip_address: Optional[str]
    started_at: Optional[datetime]
    last_active_at: datetime
    expires_at: datetime
    current: bool


class MeOut(BaseModel):
    """Профиль текущего пользователя (GET /auth/me). Ни хэшей, ни секретов."""

    id: int
    username: str
    email: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    student_id: Optional[int]
    created_at: datetime
    password_changed_at: Optional[datetime]
    username_changed_at: Optional[datetime]
    next_username_change_at: Optional[datetime]
    totp_enabled: bool
    totp_enabled_at: Optional[datetime]
    recovery_codes_left: int
    is_email_verified: bool
    email_verified_at: Optional[datetime]
    is_age_verified: bool
    age_verified_at: Optional[datetime]
    minimum_age: Optional[int]
    age_verification_required: bool
    # Проверка возраста включена в системе (её можно пройти из настроек).
    age_verification_available: bool = True


class UserOut(BaseModel):
    """Пользователь в списках (модерация). Без хэша пароля и секретов 2FA."""

    id: int
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: str
    is_active: bool
    student_id: Optional[int] = None
    is_email_verified: bool = False
    totp_enabled: bool = False
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserAdminUpdate(StrictModel):
    """Что может менять администратор. Больше ничего изменить нельзя."""

    role: Optional[str] = Field(default=None, pattern="^(admin|moderator|client)$")
    is_active: Optional[bool] = None


class ProfileUpdate(StrictModel):
    """PATCH /users/me/profile. avatar_url принимает только null (удалить аватар)."""

    display_name: Optional[str] = Field(default=None, max_length=60)
    avatar_url: Optional[str] = Field(default="__keep__")

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = " ".join(v.split())
        if any(ord(ch) < 32 for ch in v):
            raise ValueError("Недопустимые символы")
        return v or None

    @field_validator("avatar_url")
    @classmethod
    def _avatar(cls, v: Optional[str]) -> Optional[str]:
        # Произвольный внешний URL аватара — это трекинг-пиксель и SSRF у
        # тех, кто будет его загружать. Аватар ставится только загрузкой.
        if v not in (None, "__keep__"):
            raise ValueError("Аватар загружается через POST /users/me/avatar")
        return v


class UsernameChange(StrictModel):
    new_username: str

    @field_validator("new_username")
    @classmethod
    def _username(cls, v: str) -> str:
        return _check_username(v)


class UserListOut(BaseModel):
    items: List[UserOut]
