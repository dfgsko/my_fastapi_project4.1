"""
Роутер /enrollments — запись студентов на курсы (Many-to-Many между
Student и Course, реализованная через association object Enrollment).

• POST   /enrollments                  — записать студента на курс.
  Ограничено rate limiting: не более 5 запросов в минуту на одного
  студента (защита от накрутки записей).
• GET    /enrollments                  — список записей (можно
  фильтровать по student_id / course_id).
• PATCH  /enrollments/{id}/complete    — отметить курс завершённым и
  поставить оценку. Запускает фоновую Celery-задачу генерации
  PDF-сертификата, не блокируя ответ API.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenData, get_current_user, require_admin
from app.database import get_db
from app.db_models.course import Course as CourseORM
from app.db_models.enrollment import Enrollment as EnrollmentORM
from app.db_models.student import Student as StudentORM
from app.enums import EnrollmentStatus
from app.models.enrollment import Enrollment, EnrollmentCompleteRequest, EnrollmentCreate
from app.redis_client import rate_limit_check
from app.tasks import generate_certificate_task

router = APIRouter(prefix="/enrollments", tags=["enrollments"])

ENROLL_RATE_LIMIT_MAX_REQUESTS = 5
ENROLL_RATE_LIMIT_WINDOW_SECONDS = 60


@router.post(
    "",
    response_model=Enrollment,
    status_code=status.HTTP_201_CREATED,
    summary="Записать студента на курс",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Студент или курс не найден"},
        status.HTTP_400_BAD_REQUEST: {"description": "Студент уже записан на этот курс"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Превышен лимит запросов"},
    },
)
async def enroll_student(
    payload: EnrollmentCreate,
    session: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
) -> Enrollment:
    # BOLA: записать на курс можно только себя (админ — любого студента).
    if not current_user.is_admin and payload.student_id != current_user.student_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Можно записывать только себя")
    # Rate limiting: не более 5 запросов на запись в минуту для одного студента.
    await rate_limit_check(
        key=f"rate_limit:enroll:{payload.student_id}",
        max_requests=ENROLL_RATE_LIMIT_MAX_REQUESTS,
        window_seconds=ENROLL_RATE_LIMIT_WINDOW_SECONDS,
    )

    student = await session.get(StudentORM, payload.student_id)
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Студент с id={payload.student_id} не найден",
        )

    course = await session.get(CourseORM, payload.course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Курс с id={payload.course_id} не найден",
        )

    existing = await session.execute(
        select(EnrollmentORM).where(
            EnrollmentORM.student_id == payload.student_id,
            EnrollmentORM.course_id == payload.course_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Студент уже записан на этот курс",
        )

    enrollment = EnrollmentORM(
        student_id=payload.student_id,
        course_id=payload.course_id,
        enrollment_date=datetime.now(timezone.utc),
        status=EnrollmentStatus.IN_PROGRESS,
    )
    session.add(enrollment)
    await session.commit()
    await session.refresh(enrollment)
    return enrollment


@router.get("", response_model=List[Enrollment], summary="Получить список записей")
async def list_enrollments(
    student_id: Optional[int] = Query(default=None, description="Фильтр по студенту"),
    course_id: Optional[int] = Query(default=None, description="Фильтр по курсу"),
    session: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
) -> List[Enrollment]:
    if not current_user.is_admin:
        # BOLA: пользователь видит только свои записи; чужой student_id — 403.
        if student_id is not None and student_id != current_user.student_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к записям другого студента")
        if current_user.student_id is None:
            return []
        student_id = current_user.student_id
    stmt = select(EnrollmentORM)
    if student_id is not None:
        stmt = stmt.where(EnrollmentORM.student_id == student_id)
    if course_id is not None:
        stmt = stmt.where(EnrollmentORM.course_id == course_id)
    stmt = stmt.order_by(EnrollmentORM.id)

    result = await session.execute(stmt)
    return result.scalars().all()


@router.patch(
    "/{enrollment_id}/complete",
    response_model=Enrollment,
    summary="Отметить курс завершённым и выставить оценку (admin)",
    dependencies=[Depends(require_admin)],
    description="Помечает запись как завершённую и запускает фоновую "
    "Celery-задачу генерации PDF-сертификата.",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Запись не найдена"},
        status.HTTP_400_BAD_REQUEST: {"description": "Курс уже отмечен как завершённый"},
    },
)
async def complete_enrollment(
    enrollment_id: int,
    payload: EnrollmentCompleteRequest,
    session: AsyncSession = Depends(get_db),
) -> Enrollment:
    enrollment = await session.get(EnrollmentORM, enrollment_id)
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Запись с id={enrollment_id} не найдена",
        )

    if enrollment.status == EnrollmentStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Курс уже отмечен как завершённый",
        )

    enrollment.status = EnrollmentStatus.COMPLETED
    enrollment.grade = payload.grade
    await session.commit()
    await session.refresh(enrollment)

    student = await session.get(StudentORM, enrollment.student_id)
    course = await session.get(CourseORM, enrollment.course_id)

    # Фоновая генерация сертификата — не блокирует ответ API.
    # .delay() ставит задачу в очередь Celery (или выполняет её сразу
    # синхронно, если CELERY_TASK_ALWAYS_EAGER=true, как в тестах).
    generate_certificate_task.delay(
        enrollment_id=enrollment.id,
        student_name=student.full_name,
        course_title=course.title,
        grade=enrollment.grade,
    )

    return enrollment
