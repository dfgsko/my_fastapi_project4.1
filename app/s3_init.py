"""
Создание бакета S3 при старте стенда (Docker Compose: сервис s3-init).

    python -m app.s3_init

В Kubernetes бакет создаёт оператор (CRD Bucket), здесь — только для
локального SeaweedFS без оператора. Идемпотентно: существующий бакет не
трогается. Пока S3 не поднялся, делает несколько попыток.
"""

import sys
import time

from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_s3_settings
from app.s3_client import get_s3_client


def ensure_bucket(attempts: int = 30, delay: float = 2.0) -> bool:
    bucket = get_s3_settings()["bucket"]
    for attempt in range(1, attempts + 1):
        try:
            client = get_s3_client()
            try:
                client.head_bucket(Bucket=bucket)
                print(f"Бакет {bucket!r} уже существует")
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code not in ("404", "NoSuchBucket", "NotFound"):
                    raise
                client.create_bucket(Bucket=bucket)
                print(f"Бакет {bucket!r} создан")
            return True
        except (ClientError, BotoCoreError) as exc:
            print(f"[{attempt}/{attempts}] S3 ещё не готов: {exc.__class__.__name__}")
            time.sleep(delay)
    return False


if __name__ == "__main__":
    sys.exit(0 if ensure_bucket() else 1)
