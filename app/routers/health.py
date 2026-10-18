"""
Health-check эндпоинты для Kubernetes-проб.

• GET /health — liveness: процесс жив и event loop отвечает. Никаких
  внешних зависимостей не проверяет: если Postgres недоступен, убивать
  под API бессмысленно (он не починит чужую БД), поэтому проба должна
  оставаться «зелёной».
• GET /ready — readiness: приложение готово принимать трафик, то есть
  отвечают PostgreSQL и Redis. При сбое возвращается 503, и Kubernetes
  временно исключает под из балансировки (но не перезапускает его).
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.redis_client import redis_ping

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness-проба")
async def health() -> dict:
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness-проба (БД + Redis)",
    responses={503: {"description": "Зависимость недоступна"}},
)
async def ready(session: AsyncSession = Depends(get_db)):
    problems: dict[str, str] = {}

    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        problems["database"] = str(exc)

    if not await redis_ping():
        problems["redis"] = "недоступен"

    if problems:
        return JSONResponse(
            status_code=503, content={"status": "not ready", "detail": problems}
        )
    return {"status": "ready"}
