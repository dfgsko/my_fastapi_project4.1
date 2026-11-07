#!/usr/bin/env python3
"""
Демо-данные для фронтенда (лаб. № 6–8): курсы (в том числе курс 18+) и
пользователи с разными ролями. Идемпотентно — повторный запуск ничего не
дублирует.

Пишет прямо в БД (как bootstrap-администратор), а не через API: с лаб. № 8
новый пользователь не может войти, пока не подтвердит email по ссылке из
письма, а демо-аккаунты нужны сразу.

    DATABASE_URL=sqlite+aiosqlite:///./app.db python scripts/seed_demo.py

Аккаунты (пароли можно переопределить переменными окружения):
    student / Student-passw0rd    — client, возраст не подтверждён
    moder   / Moder-passw0rd-1    — moderator
    admin   — bootstrap-администратор из ADMIN_BOOTSTRAP_*
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.bootstrap import ensure_bootstrap_admin  # noqa: E402
from app.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.db_models.course import Course  # noqa: E402
from app.db_models.student import Student  # noqa: E402
from app.db_models.user import User  # noqa: E402

COURSES = [
    ("Основы FastAPI", "REST API, Pydantic, зависимости и асинхронная БД", "Иванов И.И.", 24, 0),
    ("Kubernetes для разработчиков", "Pod, Deployment, Service, Helm и GitOps", "Петрова А.С.", 32, 0),
    ("Наблюдаемость", "Prometheus, Grafana, Loki и алерты", "Сидоров П.П.", 16, 0),
    (
        "Безопасность веб-приложений",
        "OWASP API Top 10, JWT, 2FA, Vault, Network Policies",
        "Кузнецова Е.В.",
        20,
        0,
    ),
    ("Vue.js: первый SPA", "Vite, Pinia, Vue Router и Axios", "Смирнов Д.А.", 12, 0),
    (
        "Сомелье: основы дегустации",
        "Сорта винограда, регионы и дегустация вин. Курс 18+.",
        "Виноградова О.Н.",
        8,
        18,
    ),
]

USERS = [
    # username, password, role, full_name, email, age_verified
    ("student", os.environ.get("DEMO_STUDENT_PASSWORD", "Student-passw0rd"), "client",
     "Студент Демо", "student@example.com", False),
    ("moder", os.environ.get("DEMO_MODER_PASSWORD", "Moder-passw0rd-1"), "moderator",
     "Модератор Демо", "moder@example.com", True),
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def main() -> int:
    if os.environ.get("AUTO_CREATE_TABLES", "true").lower() == "true":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await ensure_bootstrap_admin()

    async with AsyncSessionLocal() as session:
        existing = set((await session.execute(select(Course.title))).scalars())
        for title, description, instructor, hours, min_age in COURSES:
            if title not in existing:
                session.add(Course(title=title, description=description, instructor=instructor,
                                   duration_hours=hours, min_age=min_age))
                print(f"курс создан: {title}{' (18+)' if min_age else ''}")

        for username, password, role, full_name, email, age_ok in USERS:
            found = await session.execute(select(User).where(User.username == username))
            if found.scalar_one_or_none() is not None:
                continue
            student = Student(full_name=full_name, email=email)
            session.add(student)
            await session.flush()
            session.add(User(
                username=username, email=email, hashed_password=hash_password(password),
                role=role, student_id=student.id, is_email_verified=True,
                email_verified_at=_now(), is_age_verified=age_ok,
                age_verified_at=_now() if age_ok else None, minimum_age=18 if age_ok else None,
                password_changed_at=_now(),
            ))
            print(f"пользователь создан: {username} / {password} ({role})")
        await session.commit()

    await engine.dispose()
    print("Готово: откройте http://localhost:5173")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
