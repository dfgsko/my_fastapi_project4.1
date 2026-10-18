"""
Конфигурация приложения из переменных окружения (12-factor).

В Kubernetes настройки приходят из ConfigMap (неконфиденциальные:
DATABASE_HOST, REDIS_HOST, ...) и Secret (DATABASE_USER, пароли), а
в docker-compose / локально проще задать готовые строки подключения
(DATABASE_URL, REDIS_URL, CELERY_BROKER_URL). Модуль поддерживает оба
варианта: готовый URL имеет приоритет, иначе URL собирается из частей.
Благодаря этому образ не нужно пересобирать при смене окружения.
"""

import os
from urllib.parse import quote_plus


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def get_database_url() -> str:
    """Асинхронный URL БД (SQLAlchemy + asyncpg по умолчанию)."""
    url = _env("DATABASE_URL")
    if url:
        return url
    user = quote_plus(_env("DATABASE_USER", "appuser"))
    password = quote_plus(_env("DATABASE_PASSWORD", "apppass"))
    host = _env("DATABASE_HOST", "localhost")
    port = _env("DATABASE_PORT", "5432")
    name = _env("DATABASE_NAME", "appdb")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def get_redis_url() -> str:
    """URL Redis (кэш, rate limiting, backend результатов Celery)."""
    url = _env("REDIS_URL")
    if url:
        return url
    host = _env("REDIS_HOST", "localhost")
    port = _env("REDIS_PORT", "6379")
    return f"redis://{host}:{port}/0"


def get_broker_url() -> str:
    """URL брокера Celery (RabbitMQ по протоколу AMQP)."""
    url = _env("CELERY_BROKER_URL")
    if url:
        return url
    user = quote_plus(_env("RABBITMQ_DEFAULT_USER", "guest"))
    password = quote_plus(_env("RABBITMQ_DEFAULT_PASS", "guest"))
    host = _env("RABBITMQ_HOST", "localhost")
    port = _env("RABBITMQ_PORT", "5672")
    return f"amqp://{user}:{password}@{host}:{port}//"


def get_result_backend_url() -> str:
    """Backend результатов Celery — Redis (RabbitMQ для этого не подходит)."""
    return _env("CELERY_RESULT_BACKEND") or get_redis_url()


def auto_create_tables() -> bool:
    """
    Создавать ли таблицы через create_all при старте.

    Локально и в тестах — да (удобно). В Kubernetes отключается
    (AUTO_CREATE_TABLES=false): схему создаёт Job с `alembic upgrade head`,
    иначе несколько реплик API одновременно гонялись бы за create_all.
    """
    return _env("AUTO_CREATE_TABLES", "true").lower() == "true"


# ---------------------------------------------------------------------------
# S3 (SeaweedFS) и метрики — лабораторная № 4
# ---------------------------------------------------------------------------


def get_s3_settings() -> dict:
    """
    Параметры S3-хранилища (SeaweedFS). Endpoint, бакет и регион приходят из
    ConfigMap (k8s/s3-config.yaml), ключи доступа — из Secret app-s3-secrets.

    Ключи разделены по принципу наименьших привилегий: admin-ключ нужен
    только для загрузки и удаления, read-only ключ — для скачивания.
    """
    admin_key = _env("S3_ACCESS_KEY")
    admin_secret = _env("S3_SECRET_KEY")
    return {
        "endpoint": _env("S3_ENDPOINT", "http://seaweedfs-s3:8333"),
        "bucket": _env("S3_BUCKET", "fastapi-files"),
        "region": _env("S3_REGION", "us-east-1"),
        "access_key": admin_key,
        "secret_key": admin_secret,
        # Если read-only ключи не заданы, скачивание идёт под admin-ключами.
        "read_access_key": _env("S3_READ_ACCESS_KEY") or admin_key,
        "read_secret_key": _env("S3_READ_SECRET_KEY") or admin_secret,
        "max_upload_bytes": int(_env("S3_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
    }


def metrics_enabled() -> bool:
    """Экспортировать ли метрики Prometheus на /metrics."""
    return _env("METRICS_ENABLED", "true").lower() == "true"


def queue_metrics_enabled() -> bool:
    """Публиковать ли длину очереди Celery (celery_queue_length) на /metrics."""
    return _env("CELERY_QUEUE_METRICS", "true").lower() == "true"
