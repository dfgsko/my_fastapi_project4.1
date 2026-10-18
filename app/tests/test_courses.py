"""
Тесты для /courses: CRUD на реальной (тестовой) БД + кэширование
GET /courses?instructor=... через фейковый Redis.
"""

from httpx import AsyncClient

SAMPLE_COURSE = {
    "title": "Введение в базы данных",
    "description": "Основы реляционных СУБД и SQL.",
    "instructor": "Иванов И.И.",
    "duration_hours": 36,
}

ANOTHER_COURSE = {
    "title": "Веб-технологии",
    "description": "FastAPI, REST, HTTP.",
    "instructor": "Петров П.П.",
    "duration_hours": 48,
}


async def create_course(client: AsyncClient, payload: dict = SAMPLE_COURSE) -> dict:
    response = await client.post("/courses", json=payload)
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------
# POST /courses
# ---------------------------------------------------------------------

async def test_create_course_returns_201_and_assigns_id(client: AsyncClient):
    course = await create_course(client)
    assert course["id"] == 1
    assert course["title"] == SAMPLE_COURSE["title"]
    assert course["duration_hours"] == 36


async def test_create_course_with_invalid_duration_returns_422(client: AsyncClient):
    invalid = {**SAMPLE_COURSE, "duration_hours": -5}
    response = await client.post("/courses", json=invalid)
    assert response.status_code == 422


async def test_create_course_missing_field_returns_422(client: AsyncClient):
    invalid = {k: v for k, v in SAMPLE_COURSE.items() if k != "title"}
    response = await client.post("/courses", json=invalid)
    assert response.status_code == 422


# ---------------------------------------------------------------------
# GET /courses/{course_id}
# ---------------------------------------------------------------------

async def test_get_course_by_id(client: AsyncClient):
    created = await create_course(client)
    response = await client.get(f"/courses/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


async def test_get_nonexistent_course_returns_404(client: AsyncClient):
    response = await client.get("/courses/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------
# GET /courses (+ фильтрация)
# ---------------------------------------------------------------------

async def test_list_courses_empty(client: AsyncClient):
    response = await client.get("/courses")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_courses_returns_all(client: AsyncClient):
    await create_course(client, SAMPLE_COURSE)
    await create_course(client, ANOTHER_COURSE)

    response = await client.get("/courses")
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_courses_filter_by_instructor(client: AsyncClient):
    await create_course(client, SAMPLE_COURSE)
    await create_course(client, ANOTHER_COURSE)

    response = await client.get("/courses", params={"instructor": "Петров"})
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["instructor"] == "Петров П.П."


async def test_list_courses_filter_by_duration_range(client: AsyncClient):
    await create_course(client, SAMPLE_COURSE)   # 36 часов
    await create_course(client, ANOTHER_COURSE)  # 48 часов

    response = await client.get(
        "/courses", params={"min_duration": 40, "max_duration": 50}
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["duration_hours"] == 48


async def test_list_courses_invalid_duration_range_returns_400(client: AsyncClient):
    response = await client.get(
        "/courses", params={"min_duration": 50, "max_duration": 10}
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------
# PUT /courses/{course_id}
# ---------------------------------------------------------------------

async def test_update_course(client: AsyncClient):
    created = await create_course(client)
    updated_payload = {**SAMPLE_COURSE, "title": "Базы данных (обновлено)"}

    response = await client.put(f"/courses/{created['id']}", json=updated_payload)
    assert response.status_code == 200
    assert response.json()["title"] == "Базы данных (обновлено)"
    assert response.json()["id"] == created["id"]


async def test_update_nonexistent_course_returns_404(client: AsyncClient):
    response = await client.put("/courses/999", json=SAMPLE_COURSE)
    assert response.status_code == 404


# ---------------------------------------------------------------------
# DELETE /courses/{course_id}
# ---------------------------------------------------------------------

async def test_delete_course(client: AsyncClient):
    created = await create_course(client)

    response = await client.delete(f"/courses/{created['id']}")
    assert response.status_code == 204

    response = await client.get(f"/courses/{created['id']}")
    assert response.status_code == 404


async def test_delete_nonexistent_course_returns_404(client: AsyncClient):
    response = await client.delete("/courses/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------
# Кэширование GET /courses?instructor=...
# ---------------------------------------------------------------------

async def test_instructor_filter_is_cached(client: AsyncClient, fake_redis):
    await create_course(client, SAMPLE_COURSE)

    # Первый запрос — кладёт результат в кэш.
    first = await client.get("/courses", params={"instructor": "Иванов"})
    assert first.status_code == 200
    assert len(first.json()) == 1

    # Ключ кэша должен появиться в фейковом Redis.
    cached_keys = [k async for k in fake_redis.scan_iter(match="courses:list:*")]
    assert len(cached_keys) == 1

    # Создание нового курса должно инвалидировать кэш (POST /courses
    # вызывает _invalidate_courses_cache()) — иначе следующий запрос
    # вернул бы устаревший результат из первого вызова (1 курс).
    await create_course(
        client, {**SAMPLE_COURSE, "title": "Другой курс", "instructor": "Иванов И.И."}
    )

    response_after_create = await client.get("/courses", params={"instructor": "Иванов"})
    assert response_after_create.status_code == 200
    assert len(response_after_create.json()) == 2


async def test_instructor_filter_cache_invalidated_on_update(
    client: AsyncClient, fake_redis
):
    created = await create_course(client, SAMPLE_COURSE)

    first = await client.get("/courses", params={"instructor": "Иванов"})
    assert len(first.json()) == 1

    # Меняем преподавателя — кэш должен инвалидироваться, и старый
    # преподаватель больше не должен находиться в списке.
    updated_payload = {**SAMPLE_COURSE, "instructor": "Сидоров С.С."}
    await client.put(f"/courses/{created['id']}", json=updated_payload)

    response = await client.get("/courses", params={"instructor": "Иванов"})
    assert response.json() == []
