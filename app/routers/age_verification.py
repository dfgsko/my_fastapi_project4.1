"""
POST /auth/verify-age — проверка возраста по фото (лабораторная № 8, шаг 10).

Вариант с локальной библиотекой BetterAgeVerify вместо облачного self.xyz
(см. app/age_estimator.py). Фото принимается multipart/form-data, читается
только в память, нигде не сохраняется и не логируется; в БД попадает лишь
результат: is_age_verified, age_verified_at и порог minimum_age.

Работает и для полноценной сессии (из настроек аккаунта), и для
незавершённой регистрации (cookie registration_token).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.age_estimator import get_estimator, open_image
from app.auth import get_current_or_registering_user
from app.config import age_min_confidence, age_minimum, age_verification_enabled
from app.database import get_db
from app.db_models.user import User
from app.metrics import AUTH_EVENTS
from app.redis_client import rate_limit_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["age-verification"])

MAX_PHOTO_BYTES = 10 * 1024 * 1024


@router.post(
    "/verify-age",
    summary="Подтвердить возраст 18+ по фотографии лица",
    responses={
        400: {"description": "Файл не является изображением JPEG/PNG/WebP"},
        403: {"description": "Оценка возраста ниже порога"},
        422: {"description": "Лицо не найдено или низкая уверенность модели"},
        503: {"description": "Модель оценки возраста недоступна"},
    },
)
async def verify_age(
    photo: UploadFile = File(...),
    user: User = Depends(get_current_or_registering_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if not age_verification_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проверка возраста отключена")
    # Попытки ограничены: иначе можно перебирать фото, пока модель не ошибётся.
    await rate_limit_check(f"rate_limit:age:{user.id}", 5, 600)
    contents = await photo.read(MAX_PHOTO_BYTES + 1)
    if len(contents) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Фото больше 10 МБ")
    try:
        image = open_image(contents)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    finally:
        del contents  # байты фото больше не нужны

    estimator = get_estimator()
    try:
        # Нейросеть — CPU-bound: в отдельном потоке, чтобы не блокировать event loop.
        result = await run_in_threadpool(estimator.estimate, image)
    except RuntimeError as exc:
        logger.error("Оценщик возраста недоступен: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Проверка возраста недоступна")
    finally:
        image.close()

    if not result.success:
        raise HTTPException(
            422,
            "Лицо на фото не найдено. Сделайте фото анфас при хорошем освещении."
            if result.error == "no_face_detected" else (result.message or "Не удалось оценить возраст"),
        )
    if result.confidence < age_min_confidence():
        raise HTTPException(
            422,
            f"Модель не уверена в оценке ({result.confidence:.0%}). Попробуйте другое фото.",
        )

    # Порог 18 — по predicted_age: флаг is_adult в BetterAgeVerify означает ≥ 21.
    threshold = age_minimum()
    if result.predicted_age < threshold:
        AUTH_EVENTS.labels(event="age_rejected").inc()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Возраст не подтверждён: оценка {result.predicted_age:.1f} лет, "
            f"уверенность {result.confidence:.0%}",
        )

    db_user = await session.get(User, user.id)
    db_user.is_age_verified = True
    db_user.age_verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db_user.minimum_age = threshold
    await session.commit()
    AUTH_EVENTS.labels(event="age_verified").inc()
    return {
        "verified": True,
        "predicted_age": round(result.predicted_age, 1),
        "confidence": round(result.confidence, 3),
        "category": result.category,
        "estimator": result.estimator,
    }
