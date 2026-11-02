"""
Роутер /students — базовый CRUD для сущности "Студент".

Нужен для того, чтобы было на кого записываться на курсы
(POST /enrollments ссылается на student_id).
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenData, get_current_user, require_admin
from app.database import get_db
from app.db_models.student import Student as StudentORM
from app.models.student import Student, StudentCreate

router = APIRouter(prefix="/students", tags=["students"])


@router.get(
    "",
    response_model=List[Student],
    summary="Получить список студентов (admin)",
    dependencies=[Depends(require_admin)],
)
async def list_students(session: AsyncSession = Depends(get_db)) -> List[Student]:
    result = await session.execute(select(StudentORM).order_by(StudentORM.id))
    return result.scalars().all()


@router.get(
    "/{student_id}",
    response_model=Student,
    summary="Получить студента по ID (admin или владелец)",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Студент не найден"}},
)
async def get_student(
    student_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
) -> Student:
    # BOLA (OWASP API1): обычный пользователь видит только СВОЮ карточку.
    # 403 одинаков для чужого и несуществующего id — перебор ID ничего не раскрывает.
    if not current_user.is_admin and current_user.student_id != student_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому студенту")
    student = await session.get(StudentORM, student_id)
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Студент с id={student_id} не найден",
        )
    return student


@router.post(
    "",
    response_model=Student,
    status_code=status.HTTP_201_CREATED,
    summary="Создать студента (admin; пользователи регистрируются через /auth/register)",
    dependencies=[Depends(require_admin)],
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Email уже используется"}
    },
)
async def create_student(
    student_in: StudentCreate, session: AsyncSession = Depends(get_db)
) -> Student:
    student = StudentORM(**student_in.model_dump())
    session.add(student)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Студент с email={student_in.email} уже зарегистрирован",
        )
    await session.refresh(student)
    return student
