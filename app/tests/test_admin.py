"""Тесты для /admin — рейтинг популярности курсов."""

from httpx import AsyncClient

COURSE_A = {
    "title": "Введение в базы данных",
    "description": "Основы реляционных СУБД и SQL.",
    "instructor": "Иванов И.И.",
    "duration_hours": 36,
}

COURSE_B = {
    "title": "Веб-технологии",
    "description": "FastAPI, REST, HTTP.",
    "instructor": "Петров П.П.",
    "duration_hours": 48,
}


async def _enroll(client: AsyncClient, student_email: str, course_id: int) -> None:
    student = (
        await client.post(
            "/students",
            json={"full_name": f"Студент {student_email}", "email": student_email},
        )
    ).json()
    response = await client.post(
        "/enrollments", json={"student_id": student["id"], "course_id": course_id}
    )
    assert response.status_code == 201


async def test_courses_popularity_orders_by_enrollment_count(client: AsyncClient):
    course_a = (await client.post("/courses", json=COURSE_A)).json()
    course_b = (await client.post("/courses", json=COURSE_B)).json()

    # У course_b будет 2 записи, у course_a — 1.
    await _enroll(client, "s1@example.com", course_a["id"])
    await _enroll(client, "s2@example.com", course_b["id"])
    await _enroll(client, "s3@example.com", course_b["id"])

    response = await client.get("/admin/courses/popularity")
    assert response.status_code == 200
    data = response.json()

    assert data[0]["id"] == course_b["id"]
    assert data[0]["enrollment_count"] == 2
    assert data[1]["id"] == course_a["id"]
    assert data[1]["enrollment_count"] == 1


async def test_courses_popularity_includes_courses_with_zero_enrollments(
    client: AsyncClient,
):
    await client.post("/courses", json=COURSE_A)

    response = await client.get("/admin/courses/popularity")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["enrollment_count"] == 0


async def test_admin_dashboard_returns_html(client: AsyncClient):
    await client.post("/courses", json=COURSE_A)

    response = await client.get("/admin")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert COURSE_A["title"] in response.text
