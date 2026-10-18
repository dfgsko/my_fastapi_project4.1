"""
ORM-модель зачисления (Enrollment).

Реализует связь Many-to-Many между Course и Student через паттерн
"association object" (а не просто association table), потому что
самой связи нужны дополнительные атрибуты: дата зачисления, оценка,
статус и путь к сгенерированному сертификату.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import EnrollmentStatus

if TYPE_CHECKING:
    from app.db_models.course import Course
    from app.db_models.student import Student


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        # Студент не может быть записан на один и тот же курс дважды.
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_date: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    grade: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[EnrollmentStatus] = mapped_column(
        String(20), default=EnrollmentStatus.IN_PROGRESS, nullable=False
    )
    certificate_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    student: Mapped["Student"] = relationship(back_populates="enrollments")
    course: Mapped["Course"] = relationship(back_populates="enrollments")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Enrollment(id={self.id!r}, student_id={self.student_id!r}, "
            f"course_id={self.course_id!r}, status={self.status!r})"
        )
