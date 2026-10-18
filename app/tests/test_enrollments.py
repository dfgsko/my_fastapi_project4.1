"""
Тесты для /enrollments:

- запись студента на курс, включая проверку 404 и дубликатов;
- rate limiting: не более 5 запросов записи в минуту для одного студента
  (проверяется через фейковый Redis, реальная логика INCR+EXPIRE);
- завершение курса (PATCH .../complete) и генерация сертификата
  фоновой Celery-задачей (выполняется синхронно благодаря
  CELERY_TASK_ALWAYS_EAGER=true, выставленному в conftest.py).
"""

import os
import shutil
from typing import Tuple

import pytest
from httpx import AsyncClient

from app.tasks import CERTIFICATES_DIR

COURSE_PAYLOAD = {
    "title": "Введение в базы данных",
    "description": "Основы реляционных СУБД и SQL.",
    "instructor": "Иванов И.И.",
    "duration_hours": 36,
}

STUDENT_PAYLOAD = {
    "full_name": "Смирнова Анна Сергеевна",
    "email": "anna.smirnova@example.com",
}


@pytest.fixture(autouse=True)
def cleanup_certificates_dir():
    yield
    shutil.rmtree(CERTIFICATES_DIR, ignore_errors=True)


async def _create_course_and_student(client: AsyncClient) -> Tuple[dict, dict]:
    course = (await client.post("/courses", json=COURSE_PAYLOAD)).json()
    student = (await client.post("/students", json=STUDENT_PAYLOAD)).json()
    return course, student


# ---------------------------------------------------------------------
# POST /enrollments
# ---------------------------------------------------------------------

async def test_enroll_student_returns_201(client: AsyncClient):
    course, student = await _create_course_and_student(client)

    response = await client.post(
        "/enrollments", json={"student_id": student["id"], "course_id": course["id"]}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["student_id"] == student["id"]
    assert body["course_id"] == course["id"]
    assert body["status"] == "in_progress"
    assert body["grade"] is None


async def test_enroll_nonexistent_student_returns_404(client: AsyncClient):
    course = (await client.post("/courses", json=COURSE_PAYLOAD)).json()
    response = await client.post(
        "/enrollments", json={"student_id": 999, "course_id": course["id"]}
    )
    assert response.status_code == 404


async def test_enroll_nonexistent_course_returns_404(client: AsyncClient):
    student = (await client.post("/students", json=STUDENT_PAYLOAD)).json()
    response = await client.post(
        "/enrollments", json={"student_id": student["id"], "course_id": 999}
    )
    assert response.status_code == 404


async def test_enroll_duplicate_returns_400(client: AsyncClient):
    course, student = await _create_course_and_student(client)
    payload = {"student_id": student["id"], "course_id": course["id"]}

    first = await client.post("/enrollments", json=payload)
    assert first.status_code == 201

    second = await client.post("/enrollments", json=payload)
    assert second.status_code == 400


# ---------------------------------------------------------------------
# Rate limiting: не более 5 запросов в минуту для одного студента
# ---------------------------------------------------------------------

async def test_enroll_rate_limit_blocks_sixth_request(client: AsyncClient):
    student = (await client.post("/students", json=STUDENT_PAYLOAD)).json()

    # Создаём 6 разных курсов, чтобы каждый запрос записи был валидным
    # (не упирался в дубликат), и записываем студента на первые 5 —
    # это должно пройти, а шестой запрос — получить 429.
    statuses = []
    for i in range(6):
        course = (
            await client.post(
                "/courses",
                json={**COURSE_PAYLOAD, "title": f"Курс {i}"},
            )
        ).json()
        response = await client.post(
            "/enrollments",
            json={"student_id": student["id"], "course_id": course["id"]},
        )
        statuses.append(response.status_code)

    assert statuses[:5] == [201] * 5
    assert statuses[5] == 429


# ---------------------------------------------------------------------
# GET /enrollments
# ---------------------------------------------------------------------

async def test_list_enrollments_filter_by_student(client: AsyncClient):
    course, student = await _create_course_and_student(client)
    await client.post(
        "/enrollments", json={"student_id": student["id"], "course_id": course["id"]}
    )

    response = await client.get("/enrollments", params={"student_id": student["id"]})
    assert response.status_code == 200
    assert len(response.json()) == 1


# ---------------------------------------------------------------------
# PATCH /enrollments/{id}/complete — завершение курса + сертификат
# ---------------------------------------------------------------------

async def test_complete_enrollment_generates_certificate(client: AsyncClient):
    course, student = await _create_course_and_student(client)
    enrollment = (
        await client.post(
            "/enrollments",
            json={"student_id": student["id"], "course_id": course["id"]},
        )
    ).json()

    response = await client.patch(
        f"/enrollments/{enrollment['id']}/complete", json={"grade": 92.5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["grade"] == 92.5

    # Задача выполняется синхронно (CELERY_TASK_ALWAYS_EAGER=true), поэтому
    # к моменту ответа файл сертификата уже должен существовать на диске.
    generated_files = os.listdir(CERTIFICATES_DIR)
    assert any(f"certificate_{enrollment['id']}" in name for name in generated_files)


async def test_complete_already_completed_enrollment_returns_400(client: AsyncClient):
    course, student = await _create_course_and_student(client)
    enrollment = (
        await client.post(
            "/enrollments",
            json={"student_id": student["id"], "course_id": course["id"]},
        )
    ).json()

    await client.patch(f"/enrollments/{enrollment['id']}/complete", json={"grade": 80})

    second = await client.patch(
        f"/enrollments/{enrollment['id']}/complete", json={"grade": 85}
    )
    assert second.status_code == 400


async def test_complete_nonexistent_enrollment_returns_404(client: AsyncClient):
    response = await client.patch("/enrollments/999/complete", json={"grade": 80})
    assert response.status_code == 404
