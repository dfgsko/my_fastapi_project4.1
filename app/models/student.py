"""Pydantic-модели (схемы) для сущности "Студент"."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Mass Assignment: лишние поля → 422

    full_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="ФИО студента",
        examples=["Смирнова Анна Сергеевна"],
    )
    email: EmailStr = Field(
        ...,
        description="Email студента (уникальный)",
        examples=["anna.smirnova@example.com"],
    )


class StudentCreate(StudentBase):
    """Модель для создания студента (POST /students)."""
    pass


class Student(StudentBase):
    """Полная модель студента, отдаваемая клиенту."""

    id: int = Field(..., description="Уникальный идентификатор студента")

    model_config = ConfigDict(from_attributes=True)
