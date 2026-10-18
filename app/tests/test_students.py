"""Тесты для /students."""

from httpx import AsyncClient

SAMPLE_STUDENT = {
    "full_name": "Смирнова Анна Сергеевна",
    "email": "anna.smirnova@example.com",
}


async def test_create_student_returns_201(client: AsyncClient):
    response = await client.post("/students", json=SAMPLE_STUDENT)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["full_name"] == SAMPLE_STUDENT["full_name"]
    assert body["email"] == SAMPLE_STUDENT["email"]


async def test_create_student_invalid_email_returns_422(client: AsyncClient):
    response = await client.post(
        "/students", json={**SAMPLE_STUDENT, "email": "not-an-email"}
    )
    assert response.status_code == 422


async def test_create_student_duplicate_email_returns_400(client: AsyncClient):
    await client.post("/students", json=SAMPLE_STUDENT)
    response = await client.post("/students", json=SAMPLE_STUDENT)
    assert response.status_code == 400


async def test_get_student_by_id(client: AsyncClient):
    created = (await client.post("/students", json=SAMPLE_STUDENT)).json()
    response = await client.get(f"/students/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


async def test_get_nonexistent_student_returns_404(client: AsyncClient):
    response = await client.get("/students/999")
    assert response.status_code == 404


async def test_list_students(client: AsyncClient):
    await client.post("/students", json=SAMPLE_STUDENT)
    await client.post(
        "/students",
        json={"full_name": "Петров Пётр Петрович", "email": "petrov@example.com"},
    )

    response = await client.get("/students")
    assert response.status_code == 200
    assert len(response.json()) == 2
