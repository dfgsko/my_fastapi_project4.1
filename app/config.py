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
    return int(_env("PASSWORD_MIN_LENGTH", "12"))  # ≥ 12 (лаб. № 8)


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


# ---------------------------------------------------------------------------
# Аккаунты, 2FA, сессии на cookies, email и возраст (лабораторная № 8)
# ---------------------------------------------------------------------------


def _bool(name: str, default: str) -> bool:
    return _env(name, default).lower() == "true"


def cookie_secure() -> bool:
    """
    Флаг Secure у cookie. В production/staging — всегда True (только HTTPS).
    Локально на http://localhost браузер не сохранил бы Secure-cookie, поэтому
    по умолчанию для development — False (COOKIE_SECURE переопределяет).
    """
    if "COOKIE_SECURE" in os.environ:
        return _bool("COOKIE_SECURE", "false")
    return environment() in _PROD_ENVS


def cookie_samesite() -> str:
    value = _env("COOKIE_SAMESITE", "strict").lower()
    if value not in ("strict", "lax"):
        # SameSite=None требует Secure и отключает защиту от CSRF — запрещаем.
        raise RuntimeError(f"Недопустимый COOKIE_SAMESITE: {value!r}")
    return value


def two_factor_temp_token_minutes() -> int:
    """Срок жизни temp_token между вводом пароля и вводом кода 2FA."""
    return int(_env("TWO_FACTOR_TEMP_TOKEN_MINUTES", "5"))


def registration_token_minutes() -> int:
    """Срок жизни токена незавершённой регистрации (шаг проверки возраста)."""
    return int(_env("REGISTRATION_TOKEN_MINUTES", "30"))


def totp_issuer() -> str:
    return _env("TOTP_ISSUER", "Educational Platform")


def totp_encryption_key() -> str:
    """
    Ключ шифрования секретов TOTP в БД. Отдельный ключ лучше (его можно
    ротировать независимо от ключа JWT); если не задан, ключ выводится из
    SECRET_KEY, чтобы локальный запуск работал без дополнительной настройки.
    """
    return _env("TOTP_ENCRYPTION_KEY") or get_secret_key()


def frontend_url() -> str:
    """Адрес SPA: из него строится ссылка в письме подтверждения."""
    return _env("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def email_verification_required() -> bool:
    """Блокировать вход до подтверждения email (EMAIL_VERIFICATION_REQUIRED)."""
    return _bool("EMAIL_VERIFICATION_REQUIRED", "true")


def email_token_hours() -> int:
    return int(_env("EMAIL_VERIFICATION_TOKEN_HOURS", "24"))


def email_resend_cooldown_seconds() -> int:
    return int(_env("EMAIL_RESEND_COOLDOWN_SECONDS", "60"))


def smtp_settings() -> dict:
    """
    SMTP для писем. Пустой SMTP_HOST — «режим разработки»: письмо не
    отправляется, а ссылка пишется в лог воркера (удобно без почтового
    сервера). В docker-compose письма ловит Mailpit (http://localhost:8025).
    """
    return {
        "host": _env("SMTP_HOST"),
        "port": int(_env("SMTP_PORT", "587")),
        "user": _env("SMTP_USER"),
        "password": _env("SMTP_PASSWORD"),
        "from": _env("SMTP_FROM", "no-reply@edu-platform.local"),
        "starttls": _bool("SMTP_STARTTLS", "true"),
    }


def age_verification_enabled() -> bool:
    """Есть ли в системе проверка возраста вообще (контент 18+)."""
    return _bool("AGE_VERIFICATION_ENABLED", "true")


def age_verification_on_registration() -> bool:
    """
    Спрашивать возраст сразу после регистрации (до отправки письма). Если
    в системе нет контента 18+, требование можно выключить.
    """
    return age_verification_enabled() and _bool("AGE_VERIFICATION_ON_REGISTRATION", "true")


def age_minimum() -> int:
    return int(_env("AGE_MINIMUM", "18"))


def age_estimator_backend() -> str:
    """
    betterageverify — локальная библиотека BetterAgeVerify (нужны torch и
    веса моделей); mock — демо-оценщик для разработки и тестов.
    """
    return _env("AGE_ESTIMATOR_BACKEND", "mock").lower()


def age_min_confidence() -> float:
    """Ниже этой уверенности модели результат не принимается (повторить фото)."""
    return float(_env("AGE_MIN_CONFIDENCE", "0.5"))


def avatar_max_bytes() -> int:
    return int(_env("AVATAR_MAX_BYTES", str(5 * 1024 * 1024)))


def username_change_cooldown_days() -> int:
    return int(_env("USERNAME_CHANGE_COOLDOWN_DAYS", "180"))
