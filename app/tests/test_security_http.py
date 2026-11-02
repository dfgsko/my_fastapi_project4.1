"""Заголовки безопасности, Host, /metrics за Ingress, конфигурация секретов, bootstrap."""

import pytest

from app import config
from app.bootstrap import ensure_bootstrap_admin
from app.db_models.user import User


async def test_security_headers_present(anon_client):
    resp = await anon_client.get("/")
    h = resp.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "strict-transport-security" not in h  # только за HTTPS


async def test_hsts_behind_https_proxy(anon_client):
    resp = await anon_client.get("/", headers={"x-forwarded-proto": "https"})
    assert "max-age=31536000" in resp.headers["strict-transport-security"]


async def test_swagger_is_not_broken_by_csp(anon_client):
    resp = await anon_client.get("/docs")
    assert resp.status_code == 200
    assert "content-security-policy" not in resp.headers


async def test_secure_headers_can_be_disabled(anon_client, monkeypatch):
    monkeypatch.setenv("SECURE_HEADERS_ENABLED", "false")
    assert "x-frame-options" not in (await anon_client.get("/")).headers


async def test_trusted_hosts_enforced_but_probes_exempt(anon_client, monkeypatch):
    monkeypatch.setenv("TRUSTED_HOSTS", "fastapi.local,*.example.com")
    bad = await anon_client.get("/", headers={"host": "evil.test"})
    assert bad.status_code == 400
    assert (await anon_client.get("/", headers={"host": "fastapi.local"})).status_code == 200
    assert (await anon_client.get("/", headers={"host": "api.example.com:443"})).status_code == 200
    # kubelet ходит по IP пода — пробы не должны ломаться.
    assert (await anon_client.get("/health", headers={"host": "10.1.2.3:8000"})).status_code == 200
    assert (
        await anon_client.get("/metrics", headers={"host": "10.1.2.3:8000"})
    ).status_code == 200


async def test_metrics_hidden_from_ingress_traffic(anon_client):
    assert (await anon_client.get("/metrics")).status_code == 200  # Prometheus внутри кластера
    via_ingress = await anon_client.get("/metrics", headers={"x-forwarded-for": "203.0.113.5"})
    assert via_ingress.status_code == 404
    via_real_ip = await anon_client.get("/metrics", headers={"x-real-ip": "203.0.113.5"})
    assert via_real_ip.status_code == 404


# ---------------------------------------------------------- секреты и конфиг
def test_weak_secret_refused_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me")
    with pytest.raises(RuntimeError):
        config.get_secret_key()
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(RuntimeError):
        config.get_secret_key()
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    assert config.get_secret_key() == "x" * 40


def test_weak_secret_allowed_in_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me")
    assert config.get_secret_key() == "dev-secret-change-me"


def test_insecure_jwt_algorithm_refused(monkeypatch):
    for alg in ("none", "RS256", "ES256"):
        monkeypatch.setenv("JWT_ALGORITHM", alg)
        with pytest.raises(RuntimeError):
            config.jwt_algorithm()


# ------------------------------------------------------------------ bootstrap
async def test_bootstrap_admin_created_once(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "Root")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "Bootstrap-passw0rd")
    assert await ensure_bootstrap_admin(db_session) is True
    assert await ensure_bootstrap_admin(db_session) is False  # идемпотентно
    async with db_session() as s:
        from sqlalchemy import select

        user = (await s.execute(select(User).where(User.username == "root"))).scalar_one()
    assert user.role == "admin" and user.hashed_password.startswith("$2")
    assert "Bootstrap-passw0rd" not in user.hashed_password


async def test_bootstrap_skipped_without_credentials_or_with_weak_password(
    db_session, monkeypatch
):
    monkeypatch.delenv("ADMIN_BOOTSTRAP_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    assert await ensure_bootstrap_admin(db_session) is False
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "root")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "weak")
    assert await ensure_bootstrap_admin(db_session) is False
