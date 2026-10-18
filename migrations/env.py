"""
Alembic env.py (асинхронный вариант).

Приложение работает через asyncpg, поэтому и миграции выполняются
асинхронным движком — отдельный синхронный драйвер (psycopg2) не нужен.
Строка подключения берётся из app.config (DATABASE_URL либо
DATABASE_HOST/USER/PASSWORD/NAME из ConfigMap и Secret), то есть
миграция в Kubernetes использует те же настройки, что и API.

Применение:  alembic upgrade head
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Делаем пакет app/ импортируемым независимо от того, откуда запущен alembic.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_database_url  # noqa: E402
from app.database import Base  # noqa: E402
import app.db_models  # noqa: E402,F401  — регистрирует ORM-модели в metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Если URL явно задан в alembic.ini — используем его, иначе — из окружения.
DB_URL = config.get_main_option("sqlalchemy.url") or get_database_url()
config.set_main_option("sqlalchemy.url", DB_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Генерация SQL без подключения к БД (alembic upgrade head --sql)."""
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Обычный режим — применение миграций к реальной БД."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
