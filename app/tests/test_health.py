"""Тесты health-check эндпоинтов (liveness / readiness)."""

import app.redis_client as redis_client


async def test_health_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_ok_when_db_and_redis_available(client):
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_ready_503_when_redis_down(client):
    redis_client._redis_client = None
    redis_client._redis_available = False

    response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not ready"
    assert "redis" in body["detail"]
    # liveness при этом остаётся зелёным — под не нужно перезапускать.
    assert (await client.get("/health")).status_code == 200
