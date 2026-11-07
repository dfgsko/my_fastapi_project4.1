"""
Оценка возраста по фото (лабораторная № 8, шаг 10, вариант BetterAgeVerify).

Вместо облачного self.xyz используется локальная библиотека BetterAgeVerify:
https://github.com/BetterAgeVerify/BetterAgeVerify (ансамбль WideResNet,
DEX и ViT, детектор лица MTCNN). Модели грузятся ОДИН раз — при первом
обращении, а не в каждом запросе: загрузка занимает секунды и сотни МБ.

Бэкенды (переменная AGE_ESTIMATOR_BACKEND):

  betterageverify — настоящая библиотека. Нужны torch, torchvision, timm,
                    facenet-pytorch и клон репозитория (путь в
                    BETTERAGEVERIFY_PATH) и веса моделей в
                    BETTERAGEVERIFY_WEIGHTS_DIR — см. README.
  mock            — демо-оценщик для разработки, тестов и CI: проверяет,
                    что файл — картинка, и возвращает возраст из
                    AGE_ESTIMATOR_MOCK_AGE. Ответ помечен estimator="mock",
                    а интерфейс показывает «демо-режим».

ВАЖНО (проверено при выполнении работы, ноябрь 2026): в опубликованном
репозитории BetterAgeVerify нет обученных весов — scripts/download_models.py
ссылается на https://example.com/..., а в src/age_estimator.py веса вообще
не загружаются (нет torch.load / load_state_dict). Без весов головы моделей
инициализированы случайно, и «оценка» — случайное число. Поэтому бэкенд
betterageverify требует BETTERAGEVERIFY_WEIGHTS_DIR с файлами весов и
отказывается работать без них, а по умолчанию включён mock.

Порог 18+: флаг is_adult у BetterAgeVerify означает возраст ≥ 21, а не 18,
поэтому решение принимается по predicted_age >= AGE_MINIMUM. Дополнительно
отклоняется результат с низкой уверенностью (confidence < AGE_MIN_CONFIDENCE).
"""

import io
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from PIL import Image, UnidentifiedImageError

from app.config import age_estimator_backend

logger = logging.getLogger(__name__)

MAX_PIXELS = 25_000_000  # защита от «картинок-бомб» (decompression bomb)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass
class AgeEstimate:
    success: bool
    predicted_age: float = 0.0
    confidence: float = 0.0
    uncertainty: float = 0.0
    error: Optional[str] = None
    message: str = ""
    estimator: str = "mock"

    @property
    def category(self) -> str:
        # Границы как в BetterAgeVerify: child < 13 ≤ teen < 21 ≤ adult.
        if self.predicted_age < 13:
            return "CHILD"
        if self.predicted_age < 21:
            return "TEEN"
        return "ADULT"


class AgeEstimator(Protocol):
    name: str

    def estimate(self, image: Image.Image) -> AgeEstimate: ...


class MockAgeEstimator:
    """Демо-оценщик: детерминированный, без нейросетей."""

    name = "mock"

    def estimate(self, image: Image.Image) -> AgeEstimate:
        age = float(os.environ.get("AGE_ESTIMATOR_MOCK_AGE", "25"))
        if image.width < 64 or image.height < 64:
            return AgeEstimate(
                success=False, error="no_face_detected",
                message="Изображение слишком маленькое: нужно лицо не меньше 64×64 px",
                estimator=self.name,
            )
        return AgeEstimate(
            success=True, predicted_age=age, confidence=0.9, uncertainty=2.3,
            message="Демо-режим: возраст задан AGE_ESTIMATOR_MOCK_AGE", estimator=self.name,
        )


class BetterAgeVerifyAdapter:
    """Обёртка над BetterAgeVerifyEstimator: ленивая загрузка и единый формат ответа."""

    name = "betterageverify"

    def __init__(self) -> None:
        self._estimator = None
        self._lock = threading.Lock()

    def _load(self):
        if self._estimator is not None:
            return self._estimator
        with self._lock:
            if self._estimator is not None:
                return self._estimator
            repo = os.environ.get("BETTERAGEVERIFY_PATH", "/opt/betterageverify")
            weights = os.environ.get("BETTERAGEVERIFY_WEIGHTS_DIR")
            if not weights or not any(Path(weights).glob("*.pth")):
                raise RuntimeError(
                    "Не найдены веса моделей BetterAgeVerify (BETTERAGEVERIFY_WEIGHTS_DIR). "
                    "Без весов модель выдаёт случайный возраст — запуск запрещён."
                )
            if repo not in sys.path:
                sys.path.insert(0, repo)
            import torch  # noqa: WPS433 — тяжёлый импорт только в этом бэкенде
            from src.age_estimator import BetterAgeVerifyEstimator  # type: ignore

            est = BetterAgeVerifyEstimator()
            files = {
                "wideresnet": "wideresnet_age.pth",
                "dex": "dex_age.pth",
                "vit": "vit_age_estimation.pth",
            }
            for name, model in est.models.items():
                state = torch.load(Path(weights) / files[name], map_location=est.device)
                model.load_state_dict(state)
                model.eval()
            self._estimator = est
            logger.info("BetterAgeVerify загружен: %s", ", ".join(est.models))
            return est

    def estimate(self, image: Image.Image) -> AgeEstimate:
        result = self._load().estimate_age(image)
        if not result.get("success"):
            return AgeEstimate(
                success=False, error=result.get("error"),
                message=result.get("message", "Не удалось оценить возраст"), estimator=self.name,
            )
        return AgeEstimate(
            success=True,
            predicted_age=float(result["predicted_age"]),
            confidence=float(result["confidence"]),
            uncertainty=float(result.get("uncertainty", 0.0)),
            estimator=self.name,
        )


_estimators: dict[str, AgeEstimator] = {}


def get_estimator() -> AgeEstimator:
    """Один экземпляр на процесс (модели в памяти переиспользуются)."""
    backend = age_estimator_backend()
    if backend not in _estimators:
        if backend == "betterageverify":
            _estimators[backend] = BetterAgeVerifyAdapter()
        elif backend == "mock":
            _estimators[backend] = MockAgeEstimator()
        else:
            raise RuntimeError(f"Неизвестный AGE_ESTIMATOR_BACKEND: {backend!r}")
    return _estimators[backend]


def open_image(data: bytes) -> Image.Image:
    """Открывает фото из памяти; ValueError, если это не JPEG/PNG/WebP."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("Поддерживаются только JPEG, PNG и WebP")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Не удалось прочитать изображение") from exc
    return img.convert("RGB")
