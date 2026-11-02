"""
Роутер /admin — простая админ-панель.

Показывает рейтинг популярности курсов по количеству записей
(enrollments). Есть JSON-вариант (для программного доступа/тестов) и
HTML-страница (для сотрудника, который открывает её в браузере).

Полноценный fastapi-admin/sqladmin в рамках лабораторной работы не
подключается — вместо этого реализован минимальный, но рабочий
дашборд, демонстрирующий тот же принцип: сотрудник открывает страницу
и видит агрегированные данные по сущностям.
"""

from html import escape as html_escape
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.db_models.course import Course as CourseORM
from app.db_models.enrollment import Enrollment as EnrollmentORM
from app.models.course import CoursePopularity

# Весь раздел — только для роли admin (зависимость на уровне роутера).
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


async def _fetch_popularity(session: AsyncSession) -> List[CoursePopularity]:
    stmt = (
        select(
            CourseORM.id,
            CourseORM.title,
            CourseORM.instructor,
            func.count(EnrollmentORM.id).label("enrollment_count"),
        )
        .outerjoin(EnrollmentORM, EnrollmentORM.course_id == CourseORM.id)
        .group_by(CourseORM.id)
        .order_by(func.count(EnrollmentORM.id).desc())
    )
    result = await session.execute(stmt)
    return [
        CoursePopularity(
            id=row.id,
            title=row.title,
            instructor=row.instructor,
            enrollment_count=row.enrollment_count,
        )
        for row in result.all()
    ]


@router.get(
    "/courses/popularity",
    response_model=List[CoursePopularity],
    summary="Рейтинг популярности курсов по количеству записей",
)
async def courses_popularity(
    session: AsyncSession = Depends(get_db),
) -> List[CoursePopularity]:
    return await _fetch_popularity(session)


@router.get(
    "",
    response_class=HTMLResponse,
    summary="HTML-дашборд администратора",
)
async def admin_dashboard(session: AsyncSession = Depends(get_db)) -> HTMLResponse:
    courses = await _fetch_popularity(session)

    if courses:
        rows_html = "".join(
            # html.escape: названия курсов приходят от пользователей (XSS).
            f"<tr><td>{c.id}</td><td>{html_escape(c.title)}</td>"
            f"<td>{html_escape(c.instructor)}</td>"
            f"<td>{c.enrollment_count}</td></tr>"
            for c in courses
        )
    else:
        rows_html = "<tr><td colspan='4'>Курсов пока нет</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Админ-панель — Популярность курсов</title>
  <style>
    body {{ font-family: -apple-system, Arial, sans-serif; margin: 40px; color: #1a1a1a; }}
    h1 {{ font-size: 20px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
    th {{ background: #f4f4f4; }}
    tr:nth-child(even) {{ background: #fafafa; }}
  </style>
</head>
<body>
  <h1>Рейтинг популярности курсов</h1>
  <table>
    <thead>
      <tr><th>ID</th><th>Название</th><th>Преподаватель</th><th>Записей на курс</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(content=html)
