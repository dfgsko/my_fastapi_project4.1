"""
Метрики Prometheus (лабораторная № 4).

Что экспортируется на GET /metrics:

  • http_requests_total{handler,method,status}      — число запросов
  • http_request_duration_seconds_bucket{handler,…} — гистограмма задержек
  • http_requests_in_progress{handler,method}       — запросы «в полёте»
      (всё это даёт prometheus-fastapi-instrumentator);
  • files_operations_total / files_bytes_total      — бизнес-метрики файлов;
  • celery_queue_length{queue="celery"}             — длина очереди RabbitMQ.

Замечания, из-за которых стандартные запросы из методички не работали бы:
  1. По умолчанию instrumentator группирует статусы («5xx»), а PromQL-фильтр
     `status=~"5.."` ищет «500»/«502». Поэтому should_group_status_codes=False.
  2. Эндпоинты /health, /ready и /metrics исключены: пробы Kubernetes
     дёргают их каждые 10–15 с и «забили» бы реальный трафик.
  3. Celery сам метрик не отдаёт, а Flower длину очереди не публикует.
     Поэтому длину очереди RabbitMQ отдаёт кастомный коллектор ниже
     (пассивный queue_declare — очередь не создаётся и не меняется).
"""

import logging

from fastapi import FastAPI
from prometheus_client import REGISTRY, Counter
from prometheus_client.core import GaugeMetricFamily

from app.config import get_broker_url, metrics_enabled, queue_metrics_enabled

logger = logging.getLogger(__name__)

FILE_OPERATIONS = Counter(
    "files_operations_total",
    "Операции с файлами в S3 (SeaweedFS)",
    ["operation", "result"],
)
FILE_BYTES = Counter(
    "files_bytes_total",
    "Объём переданных в S3 / из S3 данных, байт",
    ["direction"],
)

EXCLUDED_HANDLERS = ["/metrics", "/health", "/ready"]
# Границы гистограммы подобраны под типичный REST-API (5 мс … 5 с).
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)


def get_queue_length(queue: str = "celery", timeout: float = 2.0) -> int | None:
    """
    Число сообщений в очереди RabbitMQ или None, если брокер недоступен.

    queue_declare(passive=True) только читает состояние очереди: если её
    нет (воркер ещё ни разу не запускался), брокер вернёт ошибку — это
    не авария, метрика просто не публикуется.
    """
    from kombu import Connection

    try:
        with Connection(
            get_broker_url(), connect_timeout=timeout, transport_options={}
        ) as conn:
            channel = conn.default_channel
            return int(channel.queue_declare(queue=queue, passive=True).message_count)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Длина очереди %s недоступна: %s", queue, exc)
        return None


class CeleryQueueCollector:
    """Вычисляет celery_queue_length в момент каждого скрейпа."""

    def __init__(self, queues: tuple[str, ...] = ("celery",)) -> None:
        self.queues = queues

    def collect(self):
        gauge = GaugeMetricFamily(
            "celery_queue_length",
            "Сообщений в очереди Celery (RabbitMQ)",
            labels=["queue"],
        )
        for queue in self.queues:
            length = get_queue_length(queue)
            if length is not None:
                gauge.add_metric([queue], length)
        yield gauge


_collector_registered = False


def setup_metrics(app: FastAPI) -> None:
    """Подключает /metrics к приложению (вызывается из app/main.py)."""
    global _collector_registered
    if not metrics_enabled():
        return

    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=EXCLUDED_HANDLERS,
        should_instrument_requests_inprogress=True,
        inprogress_name="http_requests_in_progress",
        inprogress_labels=True,
    ).instrument(app, latency_lowr_buckets=LATENCY_BUCKETS).expose(
        app, include_in_schema=False
    )

    if queue_metrics_enabled() and not _collector_registered:
        REGISTRY.register(CeleryQueueCollector())
        _collector_registered = True
