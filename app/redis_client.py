"""
Обёртка над Redis для двух задач:

1. Кэширование ответов GET-эндпоинтов (cache_get / cache_set /
   cache_delete_pattern).
2. Rate limiting по схеме INCR + EXPIRE (rate_limit_check).

Особенность реализации: если Redis недоступен (не запущен, сеть
недоступна и т.п.), приложение не падает — кэширование и
rate limiting просто отключаются (fail-open), а в лог пишется
предупреждение. Это удобно для разработки/тестов без поднятого
Redis-сервера и не мешает демонстрации самого механизма в
production-конфигурации (docker-compose поднимает настоящий Redis).
"""

import json
import logging
from typing import Any, Optional

from fastapi import HTTPException, status

from app.config import get_redis_url

logger = logging.getLogger(__name__)

REDIS_URL = get_redis_url()

# Заполняются в init_redis() / тестовых фикстурах.
_redis_client: Optional[Any] = None
_redis_available: bool = False


async def init_redis(url: str = REDIS_URL) -> None:
    """Подключается к Redis. Вызывается из lifespan в app/main.py."""
    global _redis_client, _redis_available
    try:
        import redis.asyncio as redis  # локальный импорт: не обязателен для тестов

        client = redis.Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=1
        )
        await client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("Redis подключён: %s", url)
    except Exception as exc:  # noqa: BLE001 — любой сбой подключения не критичен
        logger.warning(
            "Redis недоступен (%s). Кэширование и rate limiting отключены.", exc
        )
        _redis_client = None
        _redis_available = False


async def close_redis() -> None:
    """Закрывает соединение с Redis. Вызывается из lifespan при остановке."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception:  # noqa: BLE001
            pass
    _redis_client = None
    _redis_available = False


def is_redis_available() -> bool:
    return _redis_available


async def redis_ping() -> bool:
    """Реальная проверка связи с Redis (для readiness-пробы /ready)."""
    if _redis_client is None:
        return False
    try:
        await _redis_client.ping()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis ping не прошёл: %s", exc)
        return False


async def cache_get(key: str) -> Optional[Any]:
    """Вернуть закэшированное значение или None, если его нет/кэш выключен."""
    if not _redis_available:
        return None
    try:
        raw = await _redis_client.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка чтения из кэша (%s): %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    """Сохранить значение в кэш на ttl_seconds секунд."""
    if not _redis_available:
        return
    try:
        await _redis_client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка записи в кэш (%s): %s", key, exc)


async def cache_delete_pattern(pattern: str) -> int:
    """Инвалидировать (удалить) все ключи, подходящие под pattern (например 'courses:list:*')."""
    if not _redis_available:
        return 0
    try:
        keys = [key async for key in _redis_client.scan_iter(match=pattern)]
        if not keys:
            return 0
        return await _redis_client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка инвалидации кэша (%s): %s", pattern, exc)
        return 0


async def rate_limit_check(key: str, max_requests: int, window_seconds: int) -> None:
    """
    Атомарный (в рамках Redis) rate limiter по схеме INCR + EXPIRE.

    Бросает HTTPException(429), если лимит превышен. Если Redis
    недоступен, ограничение не применяется (fail-open) — приложение
    остаётся доступным, но об этом честно предупреждает лог.
    """
    if not _redis_available:
        return
    try:
        current = await _redis_client.incr(key)
        if current == 1:
            await _redis_client.expire(key, window_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка rate limiting (%s): %s", key, exc)
        return

    if current > max_requests:
        try:
            retry_after = await _redis_client.ttl(key)
        except Exception:  # noqa: BLE001
            retry_after = window_seconds
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Слишком много запросов: лимит {max_requests} за "
                f"{window_seconds} сек. Повторите через {max(retry_after, 0)} сек."
            ),
        )
