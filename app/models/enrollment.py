"""Pydantic-модели (схемы) для сущности "Зачисление" (Enrollment)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.enums import EnrollmentStatus


class EnrollmentCreate(BaseModel):
    """Модель для записи студента на курс (POST /enrollments)."""

    student_id: int = Field(..., description="ID студента", examples=[1])
    course_id: int = Field(..., description="ID курса", examples=[1])


class EnrollmentCompleteRequest(BaseModel):
    """Модель для отметки курса как завершённого (PATCH .../complete)."""

    grade: float = Field(
        ...,
        ge=0,
        le=100,
        description="Итоговая оценка студента по курсу (0–100)",
        examples=[95.0],
    )


class Enrollment(BaseModel):
    """Полная модель записи, отдаваемая клиенту."""

    id: int
    student_id: int
    course_id: int
    enrollment_date: datetime
    grade: Optional[float] = None
    status: EnrollmentStatus
    certificate_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
