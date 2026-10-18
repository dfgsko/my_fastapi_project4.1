"""
Точка входа приложения.

Локальный запуск без PostgreSQL (SQLite) — см. README:

    DATABASE_URL=sqlite+aiosqlite:///./app.db uvicorn app.main:app --reload

Полный стек: docker compose up --build (Compose) или Minikube
(k8s/, helm/). Probes для Kubernetes: /health (liveness), /ready.

Документация:
    http://127.0.0.1:8000/docs   (Swagger UI)
    http://127.0.0.1:8000/redoc  (ReDoc)

Админ-панель:
    http://127.0.0.1:8000/admin
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import auto_create_tables
from app.database import Base, engine
from app.redis_client import close_redis, init_redis
from app.metrics import setup_metrics
from app.routers import admin, courses, enrollments, files, health, students

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # Локально/в тестах таблицы создаются автоматически (create_all).
    # В Kubernetes AUTO_CREATE_TABLES=false: схему применяет Job
    # `alembic upgrade head`, а реплики API не конкурируют за DDL.
    if auto_create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await init_redis()

    yield

    # --- Shutdown ---
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Educational Platform API",
    description=(
        "REST API для образовательной платформы: курсы, студенты и "
        "зачисления, с кэшированием (Redis), rate limiting, фоновой "
        "генерацией сертификатов (Celery), файлами в S3 (SeaweedFS) и "
        "метриками Prometheus (/metrics)."
    ),
    version="4.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(courses.router)
app.include_router(students.router)
app.include_router(enrollments.router)
app.include_router(admin.router)
app.include_router(files.router)

# /metrics для Prometheus (лабораторная № 4): запросы, задержки, очередь Celery.
setup_metrics(app)


@app.get("/", tags=["health"], summary="Проверка работоспособности сервера")
def root() -> dict:
    return {"status": "ok", "service": "Educational Platform API", "version": "4.0.0"}
