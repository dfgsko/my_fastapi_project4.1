#!/usr/bin/env python3
"""
Генератор нагрузки для демонстрации автомасштабирования KEDA.

Каждое завершение курса (PATCH /enrollments/{id}/complete) кладёт в
очередь RabbitMQ одну Celery-задачу (генерация сертификата). Скрипт
создаёт курс и N студентов, записывает каждого на курс и завершает
запись — получается N задач в очереди. Студентов именно N, потому что
POST /enrollments ограничен rate limiting-ом (5/мин на студента).

    kubectl port-forward svc/fastapi-service 8000:80 -n fastapi-app
    python scripts/load_test.py --count 100

С лаб. № 5 API требует JWT: скрипт входит как администратор (создание
студентов и завершение записей — права admin). Учётные данные — из
ADMIN_BOOTSTRAP_USERNAME / ADMIN_BOOTSTRAP_PASSWORD (k8s/02-secrets.yaml)
или аргументов --username / --password.

В соседнем терминале:
    kubectl get pods -l app=celery-worker -n fastapi-app -w
"""

import argparse
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx


def run_one(client: httpx.Client, course_id: int, run_id: str, index: int) -> bool:
    student = client.post(
        "/students",
        json={"full_name": f"Нагрузка {index}", "email": f"load-{run_id}-{index}@example.com"},
    )
    student.raise_for_status()
    enrollment = client.post(
        "/enrollments",
        json={"student_id": student.json()["id"], "course_id": course_id},
    )
    enrollment.raise_for_status()
    done = client.patch(
        f"/enrollments/{enrollment.json()['id']}/complete", json={"grade": 90.0}
    )
    done.raise_for_status()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--count", type=int, default=100, help="сколько задач создать")
    parser.add_argument("--workers", type=int, default=10, help="параллельных запросов")
    parser.add_argument("--username", default=os.environ.get("API_USER", "admin"))
    parser.add_argument(
        "--password", default=os.environ.get("API_PASSWORD", "ChangeMe-Admin-2026")
    )
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:8]
    started = time.monotonic()

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        login = client.post(
            "/auth/token", data={"username": args.username, "password": args.password}
        )
        if login.status_code != 200:
            print(f"Не удалось войти ({login.status_code}): {login.text}", file=sys.stderr)
            return 2
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        course = client.post(
            "/courses",
            json={
                "title": f"Нагрузочный курс {run_id}",
                "description": "Создан scripts/load_test.py",
                "instructor": "Load Test",
                "duration_hours": 10,
            },
        )
        course.raise_for_status()
        course_id = course.json()["id"]

        ok = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(run_one, client, course_id, run_id, i)
                for i in range(args.count)
            ]
            for future in futures:
                try:
                    ok += future.result()
                except httpx.HTTPError as exc:
                    print(f"ошибка запроса: {exc}", file=sys.stderr)

    elapsed = time.monotonic() - started
    print(f"Поставлено задач: {ok}/{args.count} за {elapsed:.1f} с (курс id={course_id})")
    return 0 if ok == args.count else 1


if __name__ == "__main__":
    sys.exit(main())
