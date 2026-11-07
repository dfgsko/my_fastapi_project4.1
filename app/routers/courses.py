"""
Роутер /courses — CRUD для сущности "Курс", теперь на постоянном
хранилище (таблица courses через SQLAlchemy) вместо in-memory словаря.

Кэширование: результат GET /courses?instructor=... кэшируется в Redis
на 3 минуты (COURSES_CACHE_TTL_SECONDS). При создании, обновлении или
удалении курса кэш инвалидируется целиком (все варианты фильтров),
так как заранее неизвестно, под какие фильтры мог попасть
изменившийся курс.

Лабораторная № 8:
  • создавать, изменять и удалять курсы могут moderator и admin
    (require_moderator), клиент получает 403 — даже если отправит запрос
    в обход интерфейса;
  • курсы с min_age > 0 (18+) видят только пользователи с подтверждённым
    возрастом (и модераторы). Фильтрация — в SQL-запросе, а не на фронтенде:
    иначе ограничение обходилось бы прямым запросом к API. Сколько курсов
    скрыто, сообщает заголовок X-Age-Restricted-Hidden — по нему интерфейс
    показывает плашку «подтвердите возраст».
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenData, get_current_user, require_moderator
from app.database import get_db
from app.db_models.course import Course as CourseORM
from app.models.course import Course, CourseCreate, CourseUpdate
from app.redis_client import cache_delete_pattern, cache_get, cache_set

router = APIRouter(prefix="/courses", tags=["courses"])

COURSES_CACHE_TTL_SECONDS = 180  # 3 минуты, как указано в задании
COURSES_CACHE_PREFIX = "courses:list"


def can_see_restricted(user: TokenData) -> bool:
    return user.is_age_verified or user.is_moderator


def _list_cache_key(
    instructor: Optional[str], min_duration: Optional[int], max_duration: Optional[int],
    adult: bool = True,
) -> str:
    # adult входит в ключ: иначе клиент без проверки возраста получил бы
    # из кэша список, собранный для взрослого.
    return (
        f"{COURSES_CACHE_PREFIX}:adult={int(adult)}:instructor={instructor or ''}"
        f":min={min_duration if min_duration is not None else ''}"
        f":max={max_duration if max_duration is not None else ''}"
    )


async def _invalidate_courses_cache() -> None:
    await cache_delete_pattern(f"{COURSES_CACHE_PREFIX}:*")


@router.get(
    "",
    response_model=List[Course],
    summary="Получить список курсов (нужна аутентификация)",
    description="Список курсов с опциональной фильтрацией по преподавателю "
    "и диапазону длительности. Результат запроса с фильтром по "
    "преподавателю кэшируется в Redis на 3 минуты.",
)
async def list_courses(
    response: Response,
    instructor: Optional[str] = Query(
        default=None,
        description="Фильтр по преподавателю (частичное совпадение, без учёта регистра)",
    ),
    min_duration: Optional[int] = Query(
        default=None, ge=0, description="Минимальная длительность курса в часах"
    ),
    max_duration: Optional[int] = Query(
        default=None, ge=0, description="Максимальная длительность курса в часах"
    ),
    session: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
) -> List[Course]:
    adult = can_see_restricted(current_user)
    if (
        min_duration is not None
        and max_duration is not None
        and min_duration > max_duration
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_duration не может быть больше max_duration",
        )

    # По заданию кэшируется именно запрос со списком курсов конкретного
    # преподавателя (GET /courses?instructor=...).
    cache_key = None
    if instructor is not None:
        cache_key = _list_cache_key(instructor, min_duration, max_duration, adult)
        cached = await cache_get(cache_key)
        if cached is not None and isinstance(cached, dict):
            response.headers["X-Age-Restricted-Hidden"] = str(cached.get("hidden", 0))
            return cached["items"]

    stmt = select(CourseORM)
    if instructor is not None:
        stmt = stmt.where(CourseORM.instructor.ilike(f"%{instructor}%"))
    if min_duration is not None:
        stmt = stmt.where(CourseORM.duration_hours >= min_duration)
    if max_duration is not None:
        stmt = stmt.where(CourseORM.duration_hours <= max_duration)
    hidden = 0
    if not adult:
        count_stmt = stmt.where(CourseORM.min_age > 0).with_only_columns(func.count())
        hidden = (await session.execute(count_stmt)).scalar_one()
        stmt = stmt.where(CourseORM.min_age <= 0)
    stmt = stmt.order_by(CourseORM.id)

    result = await session.execute(stmt)
    courses = [Course.model_validate(row).model_dump(mode="json") for row in result.scalars().all()]

    if cache_key is not None:
        await cache_set(cache_key, {"items": courses, "hidden": hidden}, COURSES_CACHE_TTL_SECONDS)

    response.headers["X-Age-Restricted-Hidden"] = str(hidden)
    return courses


@router.get(
    "/{course_id}",
    response_model=Course,
    summary="Получить курс по ID",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Курс не найден"},
        status.HTTP_403_FORBIDDEN: {"description": "Курс 18+, возраст не подтверждён"},
    },
)
async def get_course(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
) -> Course:
    course = await session.get(CourseORM, course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Курс с id={course_id} не найден",
        )
    if course.min_age > 0 and not can_see_restricted(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Для доступа подтвердите возраст",
            headers={"X-Error-Code": "age_verification_required"},
        )
    return course


@router.post(
    "",
    dependencies=[Depends(require_moderator)],
    response_model=Course,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый курс (moderator, admin)",
)
async def create_course(
    course_in: CourseCreate, session: AsyncSession = Depends(get_db)
) -> Course:
    course = CourseORM(**course_in.model_dump())
    session.add(course)
    await session.commit()
    await session.refresh(course)

    await _invalidate_courses_cache()
    return course


@router.put(
    "/{course_id}",
    dependencies=[Depends(require_moderator)],
    response_model=Course,
    summary="Обновить курс (moderator, admin)",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Курс не найден"}},
)
async def update_course(
    course_id: int, course_in: CourseUpdate, session: AsyncSession = Depends(get_db)
) -> Course:
    course = await session.get(CourseORM, course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Курс с id={course_id} не найден",
        )

    for field, value in course_in.model_dump().items():
        setattr(course, field, value)

    await session.commit()
    await session.refresh(course)

    await _invalidate_courses_cache()
    return course


@router.delete(
    "/{course_id}",
    dependencies=[Depends(require_moderator)],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить курс (moderator, admin)",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Курс не найден"}},
)
async def delete_course(
    course_id: int, session: AsyncSession = Depends(get_db)
) -> None:
    course = await session.get(CourseORM, course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Курс с id={course_id} не найден",
        )

    await session.delete(course)
    await session.commit()

    await _invalidate_courses_cache()
