"""ORM-модель курса."""

from typing import TYPE_CHECKING, List

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.db_models.enrollment import Enrollment


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    instructor: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    # Связь Many-to-Many со студентами через промежуточную таблицу
    # enrollments (association object — хранит дату зачисления и оценку).
    enrollments: Mapped[List["Enrollment"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Course(id={self.id!r}, title={self.title!r})"
