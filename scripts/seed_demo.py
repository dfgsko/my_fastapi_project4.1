#!/usr/bin/env python3
"""
Демо-данные для главного экрана фронтенда (лаб. № 6): курсы и обычный
пользователь-студент. Идемпотентно — существующие курсы и пользователь не
дублируются.

    uvicorn app.main:app --reload            # бэкенд на :8000
    python scripts/seed_demo.py              # логин admin из ADMIN_BOOTSTRAP_*

Переменные: API_URL (по умолчанию http://localhost:8000), API_USER /
API_PASSWORD (по умолчанию bootstrap-администратор).
"""

import os
import sys

import httpx

API = os.environ.get("API_URL", "http://localhost:8000")
ADMIN = os.environ.get("API_USER", os.environ.get("ADMIN_BOOTSTRAP_USERNAME", "admin"))
PASSWORD = os.environ.get(
    "API_PASSWORD", os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "ChangeMe-Admin-2026")
)

COURSES = [
    ("Основы FastAPI", "REST API, Pydantic, зависимости и асинхронная БД", "Иванов И.И.", 24),
    ("Kubernetes для разработчиков", "Pod, Deployment, Service, Helm и GitOps", "Петрова А.С.", 32),
    ("Наблюдаемость", "Prometheus, Grafana, Loki и алерты", "Сидоров П.П.", 16),
    (
        "Безопасность веб-приложений",
        "OWASP API Top 10, JWT, Vault, Network Policies",
        "Кузнецова Е.В.",
        20,
    ),
    ("Vue.js: первый SPA", "Vite, Pinia, Vue Router и Axios", "Смирнов Д.А.", 12),
]
STUDENT = {
    "username": "student",
    "password": "Student-passw0rd",
    "full_name": "Студент Демо",
    "email": "student@example.com",
}


def main() -> int:
    with httpx.Client(base_url=API, timeout=10) as client:
        login = client.post("/auth/token", data={"username": ADMIN, "password": PASSWORD})
        if login.status_code != 200:
            print(f"Вход {ADMIN!r} не удался ({login.status_code}): {login.text}", file=sys.stderr)
            return 1
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        existing = {c["title"] for c in client.get("/courses").json()}
        for title, description, instructor, hours in COURSES:
            if title in existing:
                continue
            resp = client.post(
                "/courses",
                json={
                    "title": title,
                    "description": description,
                    "instructor": instructor,
                    "duration_hours": hours,
                },
            )
            resp.raise_for_status()
            print(f"курс создан: {title}")

        # Обычный пользователь — чтобы проверить вход не только админом.
        reg = httpx.post(f"{API}/auth/register", json=STUDENT, timeout=10)
        if reg.status_code == 201:
            print(f"пользователь создан: {STUDENT['username']} / {STUDENT['password']}")
        elif reg.status_code != 409:
            print(f"регистрация: {reg.status_code} {reg.text}", file=sys.stderr)

    print("Готово: откройте http://localhost:5173")
    return 0


if __name__ == "__main__":
    sys.exit(main())
