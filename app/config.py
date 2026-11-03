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


# ---------------------------------------------------------------------------
# Безопасность (лабораторная № 5)
# ---------------------------------------------------------------------------

_DEV_SECRET = "dev-secret-change-me"
_PROD_ENVS = {"production", "prod", "staging"}


def environment() -> str:
    return _env("ENVIRONMENT", "development").lower()


def get_secret_key() -> str:
    """
    Ключ подписи JWT. В Kubernetes приходит из Secret app-secrets, который
    заполняет Vault (VaultStaticSecret). Dev-значение допустимо только для
    разработки: в production/staging слабый ключ — это Broken Authentication
    (OWASP API2), поэтому приложение отказывается стартовать.
    """
    key = _env("SECRET_KEY", _DEV_SECRET)
    if environment() in _PROD_ENVS and (key == _DEV_SECRET or len(key) < 32):
        raise RuntimeError(
            "SECRET_KEY не задан или короче 32 символов — запуск в "
            f"ENVIRONMENT={environment()} запрещён"
        )
    return key


def jwt_algorithm() -> str:
    alg = _env("JWT_ALGORITHM", "HS256")
    # Только симметричные HMAC-алгоритмы: 'none' и RS*/ES* с ключом из HMAC —
    # классические приёмы подделки токена.
    if alg not in ("HS256", "HS384", "HS512"):
        raise RuntimeError(f"Недопустимый JWT_ALGORITHM: {alg!r}")
    return alg


def access_token_expire_minutes() -> int:
    return int(_env("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


def refresh_token_expire_days() -> int:
    return int(_env("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def bcrypt_rounds() -> int:
    return int(_env("BCRYPT_ROUNDS", "12"))


def password_min_length() -> int:
    return int(_env("PASSWORD_MIN_LENGTH", "10"))


def auth_rate_limit() -> tuple[int, int]:
    """(число попыток, окно в секундах) для /auth/token: защита от брутфорса."""
    return int(_env("AUTH_RATE_LIMIT_MAX", "10")), int(_env("AUTH_RATE_LIMIT_WINDOW", "60"))


def admin_bootstrap() -> tuple[str, str]:
    return _env("ADMIN_BOOTSTRAP_USERNAME"), _env("ADMIN_BOOTSTRAP_PASSWORD")


DEV_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def cors_origins() -> list[str]:
    """
    Разрешённые origin'ы CORS. Всегда явный список, никогда "*".

    Если CORS_ORIGINS не задана вообще и окружение development, разрешаются
    адреса dev-сервера Vite (лаб. № 6: фронтенд на npm run dev → :5173).
    Явная пустая строка (как в k8s/01-configmap.yaml) отключает CORS: в кластере
    фронтенд будет отдаваться с того же origin (следующая лабораторная).
    """
    if "CORS_ORIGINS" not in os.environ and environment() == "development":
        return list(DEV_CORS_ORIGINS)
    return [o.strip() for o in _env("CORS_ORIGINS").split(",") if o.strip()]


def trusted_hosts() -> list[str]:
    hosts = [h.strip().lower() for h in _env("TRUSTED_HOSTS", "*").split(",") if h.strip()]
    return hosts or ["*"]


def secure_headers_enabled() -> bool:
    return _env("SECURE_HEADERS_ENABLED", "true").lower() == "true"


def metrics_block_proxied() -> bool:
    """Не отдавать /metrics запросам, пришедшим через Ingress (есть X-Forwarded-For)."""
    return _env("METRICS_BLOCK_PROXIED", "true").lower() == "true"


def registration_enabled() -> bool:
    return _env("REGISTRATION_ENABLED", "true").lower() == "true"


def docs_enabled() -> bool:
    """Swagger/OpenAPI в production лучше скрывать (OWASP API9: инвентаризация)."""
    return _env("DOCS_ENABLED", "true").lower() == "true"
