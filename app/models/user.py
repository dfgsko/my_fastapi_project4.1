"""Pydantic-схемы пользователей и токенов (лабораторная № 5)."""

import re
from typing import Optional

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


class RegisterRequest(StrictModel):
    username: str = Field(..., examples=["anna_s"])
    password: str = Field(..., examples=["Str0ng-passw0rd"])
    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        if not _USERNAME.match(v):
            raise ValueError("Логин: 3–50 символов (латиница, цифры, _ . -)")
        return v.lower()

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_policy(v)


class RefreshRequest(StrictModel):
    refresh_token: str


class ChangePasswordRequest(StrictModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_policy(v)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """Пользователь без хэша пароля (его нельзя отдавать клиенту никогда)."""

    id: int
    username: str
    role: str
    is_active: bool
    student_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class UserAdminUpdate(StrictModel):
    """Что может менять администратор. Больше ничего изменить нельзя."""

    role: Optional[str] = Field(default=None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None
