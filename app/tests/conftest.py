"""
Общие фикстуры для тестов.

- db_session   — создаёт чистую SQLite-БД в памяти для каждого теста
                  и подменяет зависимость get_db приложения.
- fake_redis   — подменяет реальный Redis-клиент модуля app.redis_client
                  на лёгкую in-memory имитацию (autouse — применяется
                  ко всем тестам автоматически).
- client       — асинхронный HTTP-клиент (httpx), обращающийся к
                  приложению напрямую через ASGI-транспорт, без
                  реального сетевого сервера.

CELERY_TASK_ALWAYS_EAGER=true выставляется до импорта app.main, чтобы
Celery выполняла задачи синхронно, в процессе теста, без реального
брокера/воркера.
"""

import os

# Тесты работают на SQLite in-memory, а не на PostgreSQL из окружения.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("CERTIFICATES_DIR", "test_certificates")
# В тестах нет RabbitMQ: коллектор длины очереди (/metrics) не подключаем.
os.environ.setdefault("CELERY_QUEUE_METRICS", "false")
os.environ.setdefault("S3_BUCKET", "fastapi-files")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.redis_client as redis_client
from app.database import Base, get_db
from app.main import app
from app.tests.fake_redis import FakeRedis

TEST_DATABASE_URL = "sqlite+aiosqlite://"  # SQLite полностью в памяти


@pytest_asyncio.fixture()
async def db_session():
    """Создаёт свежую in-memory БД и переопределяет get_db на неё."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    yield test_session_local

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture(autouse=True)
def fake_redis():
    """Подменяет глобальный Redis-клиент на in-memory имитацию для каждого теста."""
    fake = FakeRedis()
    redis_client._redis_client = fake
    redis_client._redis_available = True
    yield fake
    redis_client._redis_client = None
    redis_client._redis_available = False


@pytest_asyncio.fixture()
async def client(db_session):
    """Асинхронный HTTP-клиент, обращающийся к приложению напрямую (без сети)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class FakeS3:
    """In-memory имитация boto3 S3-клиента (put/get/delete/list/presign)."""

    def __init__(self):
        self.objects: dict[str, tuple[bytes, str | None]] = {}

    def put_object(self, Bucket, Key, Body, ContentType=None, **_):
        self.objects[Key] = (Body, ContentType)

    def get_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        import io

        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        body, ctype = self.objects[Key]
        return {"Body": io.BytesIO(body), "ContentType": ctype}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def list_objects_v2(self, Bucket, Prefix=""):
        return {
            "Contents": [
                {"Key": k, "Size": len(v[0])}
                for k, v in sorted(self.objects.items())
                if k.startswith(Prefix)
            ]
        }

    def generate_presigned_url(self, op, Params, ExpiresIn):
        host = "http://seaweedfs-s3:8333"
        return f"{host}/{Params['Bucket']}/{Params['Key']}?X-Amz-Expires={ExpiresIn}"

    def head_bucket(self, Bucket):
        return {}


@pytest.fixture()
def fake_s3(monkeypatch):
    """Подменяет boto3-клиент модуля app.s3_client на FakeS3."""
    import app.s3_client as s3_client

    fake = FakeS3()
    monkeypatch.setattr(s3_client, "get_s3_client", lambda read_only=False: fake)
    return fake
