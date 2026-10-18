"""Воркер кладёт сертификат в S3 только при S3_UPLOAD_CERTIFICATES=true."""

from app.tasks import generate_certificate_task


def _run(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.CERTIFICATES_DIR", str(tmp_path))
    return generate_certificate_task.apply(args=(7, "Иван", "Kubernetes", 95.0)).get()


def test_certificate_not_uploaded_by_default(tmp_path, monkeypatch, fake_s3):
    monkeypatch.delenv("S3_UPLOAD_CERTIFICATES", raising=False)
    result = _run(tmp_path, monkeypatch)
    assert result["status"] == "generated"
    assert result["s3_key"] is None
    assert fake_s3.objects == {}


def test_certificate_uploaded_when_enabled(tmp_path, monkeypatch, fake_s3):
    monkeypatch.setenv("S3_UPLOAD_CERTIFICATES", "true")
    result = _run(tmp_path, monkeypatch)
    assert result["s3_key"].startswith("certificates/certificate_7.")
    assert result["s3_key"] in fake_s3.objects


def test_s3_failure_does_not_fail_task(tmp_path, monkeypatch):
    import app.s3_client as s3_client

    class Broken:
        def put_object(self, **_):
            raise RuntimeError("seaweedfs is down")

    monkeypatch.setattr(s3_client, "get_s3_client", lambda read_only=False: Broken())
    monkeypatch.setenv("S3_UPLOAD_CERTIFICATES", "true")
    result = _run(tmp_path, monkeypatch)
    assert result["status"] == "generated" and result["s3_key"] is None
