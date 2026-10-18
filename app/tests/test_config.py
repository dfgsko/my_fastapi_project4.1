"""Тесты сборки строк подключения из переменных окружения (ConfigMap/Secret)."""

import pytest

from app import config

ENV_NAMES = [
    "DATABASE_URL", "DATABASE_USER", "DATABASE_PASSWORD", "DATABASE_HOST",
    "DATABASE_PORT", "DATABASE_NAME", "REDIS_URL", "REDIS_HOST",
    "CELERY_BROKER_URL", "RABBITMQ_HOST", "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS", "CELERY_RESULT_BACKEND",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_database_url_from_parts(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "postgres-cluster-rw")
    monkeypatch.setenv("DATABASE_USER", "appuser")
    monkeypatch.setenv("DATABASE_PASSWORD", "p@ss/word")
    monkeypatch.setenv("DATABASE_NAME", "appdb")
    assert config.get_database_url() == (
        "postgresql+asyncpg://appuser:p%40ss%2Fword@postgres-cluster-rw:5432/appdb"
    )


def test_database_url_has_priority(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("DATABASE_HOST", "ignored")
    assert config.get_database_url() == "sqlite+aiosqlite://"


def test_default_driver_is_async_asyncpg():
    assert config.get_database_url().startswith("postgresql+asyncpg://")


def test_broker_url_from_parts(monkeypatch):
    monkeypatch.setenv("RABBITMQ_HOST", "rabbitmq")
    monkeypatch.setenv("RABBITMQ_DEFAULT_USER", "u")
    monkeypatch.setenv("RABBITMQ_DEFAULT_PASS", "p")
    assert config.get_broker_url() == "amqp://u:p@rabbitmq:5672//"


def test_redis_url_and_result_backend(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "redis")
    assert config.get_redis_url() == "redis://redis:6379/0"
    assert config.get_result_backend_url() == "redis://redis:6379/0"
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://other:6379/1")
    assert config.get_result_backend_url() == "redis://other:6379/1"
