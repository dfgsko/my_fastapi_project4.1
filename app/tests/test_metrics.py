"""Тесты /metrics: HTTP-метрики, бизнес-метрики файлов, очередь Celery."""

from prometheus_client import CollectorRegistry

from app.metrics import CeleryQueueCollector


async def test_metrics_endpoint_exposes_http_metrics(client):
    await client.get("/courses")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "http_requests_total" in text
    assert "http_request_duration_seconds_bucket" in text
    assert "http_requests_in_progress" in text


async def test_status_codes_are_not_grouped(client):
    """Алерт HighErrorRate использует status=~"5.." — нужны «404», а не «4xx»."""
    await client.get("/courses/999999")
    text = (await client.get("/metrics")).text
    assert 'status="404"' in text
    assert 'status="4xx"' not in text


async def test_probes_and_metrics_are_excluded(client):
    await client.get("/health")
    await client.get("/ready")
    text = (await client.get("/metrics")).text
    assert 'handler="/health"' not in text
    assert 'handler="/metrics"' not in text


async def test_file_metrics_counted(client, fake_s3):
    await client.post("/files/upload", files={"file": ("a.txt", b"12345", "text/plain")})
    text = (await client.get("/metrics")).text
    assert 'files_operations_total{operation="upload",result="ok"}' in text
    assert 'files_bytes_total{direction="upload"}' in text


def test_queue_collector_publishes_length(monkeypatch):
    import app.metrics as metrics

    monkeypatch.setattr(metrics, "get_queue_length", lambda queue, timeout=2.0: 42)
    registry = CollectorRegistry()
    registry.register(CeleryQueueCollector())
    assert registry.get_sample_value("celery_queue_length", {"queue": "celery"}) == 42


def test_queue_collector_skips_when_broker_down(monkeypatch):
    import app.metrics as metrics

    monkeypatch.setattr(metrics, "get_queue_length", lambda queue, timeout=2.0: None)
    registry = CollectorRegistry()
    registry.register(CeleryQueueCollector())
    assert registry.get_sample_value("celery_queue_length", {"queue": "celery"}) is None
