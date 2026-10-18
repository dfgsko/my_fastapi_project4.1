"""Конфигурация S3 из переменных окружения."""

from app.config import get_s3_settings, metrics_enabled


def test_s3_defaults(monkeypatch):
    for name in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_READ_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    cfg = get_s3_settings()
    assert cfg["endpoint"] == "http://seaweedfs-s3:8333"
    assert cfg["bucket"] == "fastapi-files"
    assert cfg["max_upload_bytes"] == 10 * 1024 * 1024


def test_read_keys_fall_back_to_admin(monkeypatch):
    monkeypatch.setenv("S3_ACCESS_KEY", "adm")
    monkeypatch.setenv("S3_SECRET_KEY", "adm-secret")
    monkeypatch.delenv("S3_READ_ACCESS_KEY", raising=False)
    monkeypatch.delenv("S3_READ_SECRET_KEY", raising=False)
    cfg = get_s3_settings()
    assert cfg["read_access_key"] == "adm"
    monkeypatch.setenv("S3_READ_ACCESS_KEY", "ro")
    monkeypatch.setenv("S3_READ_SECRET_KEY", "ro-secret")
    cfg = get_s3_settings()
    assert (cfg["read_access_key"], cfg["read_secret_key"]) == ("ro", "ro-secret")


def test_metrics_flag(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "false")
    assert metrics_enabled() is False
