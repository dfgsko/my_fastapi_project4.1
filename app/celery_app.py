"""
Конфигурация Celery для фоновых задач.

Брокер — RabbitMQ (AMQP), backend результатов — Redis. Очередь по
умолчанию называется "celery": именно её длину отслеживает KEDA
(k8s/keda/scaledobject.yaml) для автомасштабирования воркеров.
URL-ы собираются в app/config.py из переменных окружения.

CELERY_TASK_ALWAYS_EAGER=true заставляет задачи выполняться синхронно,
в том же процессе, без реального брокера — это используется в тестах
(см. app/tests/conftest.py), чтобы не поднимать Redis/воркер для
проверки бизнес-логики.
"""

import os

from celery import Celery

from app.config import get_broker_url, get_result_backend_url

BROKER_URL = get_broker_url()

celery_app = Celery(
    "worker",
    broker=BROKER_URL,
    backend=get_result_backend_url(),
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # События задач нужны Flower (метрики flower_* в Prometheus, лаб. № 4).
    worker_send_task_events=True,
    task_send_sent_event=True,
    # Задача подтверждается брокеру после выполнения: если под воркера
    # убьют посреди работы, RabbitMQ вернёт сообщение в очередь.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_retry_delay=30,
    task_max_retries=3,
    task_always_eager=os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower()
    == "true",
    task_eager_propagates=True,
)
