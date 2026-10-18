"""
Pydantic-модели (схемы) для сущности "Курс".

CourseBase   — общие поля, используемые и при создании, и при чтении.
CourseCreate — модель для создания курса (POST /courses).
CourseUpdate — модель для обновления курса (PUT /courses/{course_id}).
Course       — полная модель курса, возвращаемая клиенту (содержит id).
CoursePopularity — курс + количество записавшихся студентов (для админ-панели).
"""

from pydantic import BaseModel, ConfigDict, Field


class CourseBase(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Название курса",
        examples=["Введение в базы данных"],
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Описание курса",
        examples=["Курс знакомит студентов с основами реляционных БД."],
    )
    instructor: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="ФИО преподавателя",
        examples=["Иванов И.И."],
    )
    duration_hours: int = Field(
        ...,
        gt=0,
        le=1000,
        description="Длительность курса в часах",
        examples=[36],
    )


class CourseCreate(CourseBase):
    """Модель, используемая при создании курса (POST /courses)."""
    pass


class CourseUpdate(BaseModel):
    """
    Модель для обновления курса (PUT /courses/{course_id}).

    Все поля обязательны — эндпоинт реализует полную замену ресурса
    (semantics PUT).
    """
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    instructor: str = Field(..., min_length=1, max_length=200)
    duration_hours: int = Field(..., gt=0, le=1000)


class Course(CourseBase):
    """Полная модель курса, отдаваемая клиенту — включает id."""

    id: int = Field(..., description="Уникальный идентификатор курса")

    # from_attributes=True позволяет строить модель прямо из ORM-объекта
    # SQLAlchemy (Course.model_validate(course_orm_instance)).
    model_config = ConfigDict(from_attributes=True)


class CoursePopularity(BaseModel):
    """Курс с количеством записей — используется в админ-панели."""

    id: int
    title: str
    instructor: str
    enrollment_count: int

    model_config = ConfigDict(from_attributes=True)
