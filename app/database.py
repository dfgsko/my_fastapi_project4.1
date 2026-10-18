"""
Настройка асинхронной базы данных с SQLAlchemy.

Начиная с лабораторной №3 основная СУБД — PostgreSQL (асинхронный
драйвер asyncpg). SQLite остаётся доступным для локальной разработки
и тестов:

    DATABASE_URL=sqlite+aiosqlite:///./app.db

URL берётся из окружения (см. app/config.py): либо готовый
DATABASE_URL, либо части DATABASE_HOST / DATABASE_USER / ... из
ConfigMap и Secret Kubernetes. В коде ничего не зашито.
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_database_url

DATABASE_URL = get_database_url()

# echo=True полезно при отладке SQL-запросов; в production лучше выключить.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # чтобы объекты оставались доступны после commit()
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей проекта."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для внедрения сессии БД в эндпоинты через Depends(get_db).

    Коммит выполняется явно внутри эндпоинтов (это даёт больше контроля
    над границами транзакции); здесь мы лишь откатываем сессию при
    необработанном исключении и всегда закрываем её по завершении.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
