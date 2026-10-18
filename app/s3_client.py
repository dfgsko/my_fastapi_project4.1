"""
Клиент S3-совместимого хранилища SeaweedFS (boto3).

boto3 — синхронная библиотека, поэтому каждый вызов выполняется в потоке
(`asyncio.to_thread`): иначе загрузка файла блокировала бы event loop и
все остальные запросы API ждали бы её окончания.

Два набора ключей (принцип наименьших привилегий):
  • admin     — upload_file / delete_file / ensure_bucket;
  • read-only — download_file / list_files / presigned_url.
"""

import asyncio
import logging
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import get_s3_settings

logger = logging.getLogger(__name__)


def _client(read_only: bool = False):
    cfg = get_s3_settings()
    access = cfg["read_access_key"] if read_only else cfg["access_key"]
    secret = cfg["read_secret_key"] if read_only else cfg["secret_key"]
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=access or None,
        aws_secret_access_key=secret or None,
        region_name=cfg["region"],
        # SeaweedFS ожидает path-style адреса (host/bucket/key), а не bucket.host.
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=10,
            retries={"max_attempts": 2},
        ),
    )


def get_s3_client(read_only: bool = False):
    """Фабрика клиента (подменяется в тестах через monkeypatch)."""
    return _client(read_only)


def _bucket() -> str:
    return get_s3_settings()["bucket"]


class FileNotFoundInStorage(Exception):
    """Объект отсутствует в бакете."""


def upload_file_sync(
    content: bytes, object_name: str, content_type: Optional[str] = None
) -> str:
    """Синхронная загрузка — для Celery-воркера (там нет event loop)."""
    extra = {"ContentType": content_type} if content_type else {}
    get_s3_client().put_object(
        Bucket=_bucket(), Key=object_name, Body=content, **extra
    )
    return f"{_bucket()}/{object_name}"


async def upload_file(
    content: bytes, object_name: str, content_type: Optional[str] = None
) -> str:
    """Загружает объект и возвращает путь вида `<bucket>/<key>`."""
    extra = {"ContentType": content_type} if content_type else {}

    def _put() -> None:
        get_s3_client().put_object(
            Bucket=_bucket(), Key=object_name, Body=content, **extra
        )

    await asyncio.to_thread(_put)
    return f"{_bucket()}/{object_name}"


async def download_file(object_name: str) -> tuple[bytes, Optional[str]]:
    """Возвращает (содержимое, content-type). Бросает FileNotFoundInStorage."""

    def _get() -> tuple[bytes, Optional[str]]:
        try:
            resp = get_s3_client(read_only=True).get_object(
                Bucket=_bucket(), Key=object_name
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                raise FileNotFoundInStorage(object_name) from exc
            raise
        return resp["Body"].read(), resp.get("ContentType")

    return await asyncio.to_thread(_get)


async def delete_file(object_name: str) -> None:
    def _delete() -> None:
        get_s3_client().delete_object(Bucket=_bucket(), Key=object_name)

    await asyncio.to_thread(_delete)


async def list_files(prefix: str = "") -> list[dict]:
    def _list() -> list[dict]:
        resp = get_s3_client(read_only=True).list_objects_v2(
            Bucket=_bucket(), Prefix=prefix
        )
        return [
            {"name": o["Key"], "size": o["Size"]} for o in resp.get("Contents", [])
        ]

    return await asyncio.to_thread(_list)


async def presigned_url(object_name: str, expires: int = 3600) -> str:
    """Временная ссылка для скачивания напрямую из S3, минуя API."""

    def _sign() -> str:
        return get_s3_client(read_only=True).generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket(), "Key": object_name},
            ExpiresIn=expires,
        )

    return await asyncio.to_thread(_sign)


async def s3_ping() -> bool:
    """Проверка доступности хранилища (используется в /ready при желании)."""

    def _head() -> bool:
        try:
            get_s3_client(read_only=True).head_bucket(Bucket=_bucket())
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("S3 недоступен: %s", exc)
            return False

    return await asyncio.to_thread(_head)
