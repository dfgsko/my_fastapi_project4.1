"""
Роутер /files — загрузка и скачивание файлов через S3 API (SeaweedFS).

Типичные сценарии платформы: аватар студента, методические материалы
курса, PDF-сертификаты. Объекты складываются в бакет `fastapi-files`
под ключом `<папка>/<uuid>_<имя файла>`, чтобы одинаковые имена не
перезаписывали друг друга.
"""

import re
import uuid
from urllib.parse import quote

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app import s3_client
from app.config import get_s3_settings
from app.metrics import FILE_BYTES, FILE_OPERATIONS

router = APIRouter(prefix="/files", tags=["files"])

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-]+")


def _safe_filename(name: str) -> str:
    """Убирает путь и спецсимволы: `../../etc/passwd` → `passwd`."""
    base = (name or "file").replace("\\", "/").split("/")[-1]
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "file"
    return cleaned[:100]


def _storage_error(exc: Exception) -> HTTPException:
    FILE_OPERATIONS.labels(operation="error", result="storage_error").inc()
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Хранилище файлов недоступно: {exc.__class__.__name__}",
    )


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл в S3 (SeaweedFS)",
    responses={
        413: {"description": "Файл больше лимита S3_MAX_UPLOAD_BYTES"},
        502: {"description": "S3-хранилище недоступно"},
    },
)
async def upload(
    file: UploadFile = File(...),
    folder: str = Query("uploads", pattern=r"^[a-z0-9_-]{1,40}$"),
) -> dict:
    limit = get_s3_settings()["max_upload_bytes"]
    content = await file.read(limit + 1)
    if len(content) > limit:
        FILE_OPERATIONS.labels(operation="upload", result="too_large").inc()
        raise HTTPException(
            413,
            f"Файл больше {limit // (1024 * 1024)} МБ",
        )
    key = f"{folder}/{uuid.uuid4().hex[:8]}_{_safe_filename(file.filename)}"
    try:
        path = await s3_client.upload_file(content, key, file.content_type)
    except (ClientError, BotoCoreError) as exc:
        raise _storage_error(exc)
    FILE_OPERATIONS.labels(operation="upload", result="ok").inc()
    FILE_BYTES.labels(direction="upload").inc(len(content))
    return {"path": path, "key": key, "size": len(content)}


@router.get(
    "/download/{object_name:path}",
    summary="Скачать файл (через API)",
    responses={404: {"description": "Файл не найден"}, 502: {"description": "S3 недоступен"}},
)
async def download(object_name: str) -> Response:
    try:
        content, content_type = await s3_client.download_file(object_name)
    except s3_client.FileNotFoundInStorage:
        FILE_OPERATIONS.labels(operation="download", result="not_found").inc()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    except (ClientError, BotoCoreError) as exc:
        raise _storage_error(exc)
    FILE_OPERATIONS.labels(operation="download", result="ok").inc()
    FILE_BYTES.labels(direction="download").inc(len(content))
    filename = object_name.split("/")[-1]
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)
        },
    )


@router.get("/url/{object_name:path}", summary="Presigned URL для прямого скачивания из S3")
async def get_url(object_name: str, expires: int = Query(3600, ge=60, le=86400)) -> dict:
    try:
        url = await s3_client.presigned_url(object_name, expires)
    except (ClientError, BotoCoreError) as exc:
        raise _storage_error(exc)
    return {"url": url, "expires_in": expires}


@router.get("", summary="Список файлов в бакете")
async def list_files(prefix: str = Query("", max_length=100)) -> dict:
    try:
        items = await s3_client.list_files(prefix)
    except (ClientError, BotoCoreError) as exc:
        raise _storage_error(exc)
    return {"files": items, "count": len(items)}


@router.delete(
    "/{object_name:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить файл",
)
async def delete(object_name: str) -> Response:
    try:
        await s3_client.delete_file(object_name)
    except (ClientError, BotoCoreError) as exc:
        raise _storage_error(exc)
    FILE_OPERATIONS.labels(operation="delete", result="ok").inc()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
