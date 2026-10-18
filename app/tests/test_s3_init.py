"""app.s3_init: бакет создаётся один раз, повторный запуск ничего не ломает."""

from botocore.exceptions import ClientError

import app.s3_init as s3_init


class FakeAdmin:
    def __init__(self, exists):
        self.exists = exists
        self.created = []

    def head_bucket(self, Bucket):
        if not self.exists:
            raise ClientError({"Error": {"Code": "404", "Message": "no"}}, "HeadBucket")

    def create_bucket(self, Bucket):
        self.created.append(Bucket)
        self.exists = True


def test_creates_missing_bucket(monkeypatch):
    fake = FakeAdmin(exists=False)
    monkeypatch.setattr(s3_init, "get_s3_client", lambda read_only=False: fake)
    assert s3_init.ensure_bucket(attempts=1, delay=0) is True
    assert fake.created == ["fastapi-files"]
    assert s3_init.ensure_bucket(attempts=1, delay=0) is True
    assert fake.created == ["fastapi-files"]  # второй запуск — без повторного создания


def test_gives_up_when_s3_unavailable(monkeypatch):
    class Down:
        def head_bucket(self, Bucket):
            raise ClientError({"Error": {"Code": "500", "Message": "down"}}, "HeadBucket")

    monkeypatch.setattr(s3_init, "get_s3_client", lambda read_only=False: Down())
    assert s3_init.ensure_bucket(attempts=2, delay=0) is False
