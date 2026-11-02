"""RBAC и защита от BOLA / Mass Assignment (OWASP API Top 10) на ресурсах проекта."""

import pytest

COURSE = {
    "title": "Kubernetes",
    "description": "Основы",
    "instructor": "Иванов",
    "duration_hours": 8,
}


async def _make_course(client):
    return (await client.post("/courses", json=COURSE)).json()["id"]


# ---------------------------------------------------------------- 401 / 403
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/courses"),
        ("GET", "/courses/1"),
        ("POST", "/courses"),
        ("GET", "/students"),
        ("GET", "/students/1"),
        ("POST", "/students"),
        ("GET", "/enrollments"),
        ("POST", "/enrollments"),
        ("PATCH", "/enrollments/1/complete"),
        ("GET", "/admin"),
        ("GET", "/admin/courses/popularity"),
        ("GET", "/files"),
        ("POST", "/files/upload"),
        ("GET", "/files/download/x"),
        ("GET", "/users"),
        ("GET", "/auth/me"),
    ],
)
async def test_endpoints_require_authentication(anon_client, method, path):
    resp = await anon_client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} открыт без токена"


async def test_public_endpoints_stay_public(anon_client):
    assert (await anon_client.get("/")).status_code == 200
    assert (await anon_client.get("/health")).status_code == 200


async def test_user_cannot_modify_courses(user_client, client):
    course_id = await _make_course(client)
    assert (await user_client.get("/courses")).status_code == 200
    assert (await user_client.get(f"/courses/{course_id}")).status_code == 200
    assert (await user_client.post("/courses", json=COURSE)).status_code == 403
    assert (await user_client.put(f"/courses/{course_id}", json=COURSE)).status_code == 403
    assert (await user_client.delete(f"/courses/{course_id}")).status_code == 403
    assert (await client.delete(f"/courses/{course_id}")).status_code == 204


async def test_admin_area_is_admin_only(user_client, client):
    assert (await user_client.get("/admin")).status_code == 403
    assert (await user_client.get("/admin/courses/popularity")).status_code == 403
    assert (await user_client.get("/users")).status_code == 403
    assert (await client.get("/admin")).status_code == 200
    assert (await client.get("/users")).status_code == 200


async def test_admin_dashboard_escapes_html(client):
    await client.post("/courses", json={**COURSE, "title": "<script>alert(1)</script>"})
    html = (await client.get("/admin")).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# -------------------------------------------------------------------- BOLA
async def test_student_card_is_visible_only_to_owner_and_admin(user_client, client, make_user):
    other = await make_user("mallory")
    own = user_client.info["student_id"]
    assert (await user_client.get(f"/students/{own}")).status_code == 200
    # Чужой и несуществующий id неотличимы (нельзя перебирать ID).
    assert (await user_client.get(f"/students/{other['student_id']}")).status_code == 403
    assert (await user_client.get("/students/99999")).status_code == 403
    assert (await client.get(f"/students/{other['student_id']}")).status_code == 200
    assert (await client.get("/students/99999")).status_code == 404


async def test_user_cannot_list_or_create_students(user_client):
    assert (await user_client.get("/students")).status_code == 403
    resp = await user_client.post("/students", json={"full_name": "X", "email": "x@example.com"})
    assert resp.status_code == 403


async def test_user_can_enroll_only_himself(user_client, client, make_user):
    course_id = await _make_course(client)
    other = await make_user("mallory")
    mine = await user_client.post(
        "/enrollments", json={"student_id": user_client.info["student_id"], "course_id": course_id}
    )
    assert mine.status_code == 201
    stolen = await user_client.post(
        "/enrollments", json={"student_id": other["student_id"], "course_id": course_id}
    )
    assert stolen.status_code == 403


async def test_user_sees_only_own_enrollments(user_client, client, make_user):
    course_id = await _make_course(client)
    other = await make_user("mallory")
    await client.post(
        "/enrollments", json={"student_id": user_client.info["student_id"], "course_id": course_id}
    )
    await client.post(
        "/enrollments", json={"student_id": other["student_id"], "course_id": course_id}
    )

    own = (await user_client.get("/enrollments")).json()
    assert [e["student_id"] for e in own] == [user_client.info["student_id"]]
    # Попытка подставить чужой student_id или обойти фильтр.
    assert (
        await user_client.get(f"/enrollments?student_id={other['student_id']}")
    ).status_code == 403
    assert len((await client.get("/enrollments")).json()) == 2


async def test_only_admin_completes_enrollments(user_client, client):
    course_id = await _make_course(client)
    enr = (
        await user_client.post(
            "/enrollments",
            json={"student_id": user_client.info["student_id"], "course_id": course_id},
        )
    ).json()
    # Студент не может сам себе поставить оценку.
    assert (
        await user_client.patch(f"/enrollments/{enr['id']}/complete", json={"grade": 100})
    ).status_code == 403
    assert (
        await client.patch(f"/enrollments/{enr['id']}/complete", json={"grade": 90})
    ).status_code == 200


# ----------------------------------------------------------- Mass Assignment
async def test_extra_fields_rejected_on_inputs(client):
    assert (await client.post("/courses", json={**COURSE, "id": 999})).status_code == 422
    assert (
        await client.post("/students", json={"full_name": "A", "email": "a@example.com", "id": 5})
    ).status_code == 422
    assert (
        await client.post(
            "/enrollments",
            json={"student_id": 1, "course_id": 1, "grade": 100, "status": "completed"},
        )
    ).status_code == 422


async def test_admin_user_update_allows_only_role_and_active(client, user_client):
    uid = user_client.info["id"]
    bad = await client.patch(f"/users/{uid}", json={"hashed_password": "x"})
    assert bad.status_code == 422
    assert (await client.patch(f"/users/{uid}", json={"role": "superuser"})).status_code == 422
    ok = await client.patch(f"/users/{uid}", json={"role": "admin"})
    assert ok.status_code == 200 and ok.json()["role"] == "admin"
    assert "hashed_password" not in ok.json()


async def test_admin_cannot_lock_himself_out(client, admin):
    resp = await client.patch(f"/users/{admin['id']}", json={"role": "user"})
    assert resp.status_code == 400


async def test_role_change_is_effective_immediately(user_client, client):
    assert (await user_client.get("/users")).status_code == 403
    await client.patch(f"/users/{user_client.info['id']}", json={"role": "admin"})
    assert (await user_client.get("/users")).status_code == 200  # без перевыпуска токена
