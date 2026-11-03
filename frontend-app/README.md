# Фронтенд «Курсы и студенты» (лабораторная № 6)

MVP-интерфейс на **Vue 3 + Vite**: вход по JWT через FastAPI, главный экран со списком курсов из БД,
защита маршрутов. Фронтенд запускается **на компьютере** (`npm run dev`), а не в Kubernetes.

| Что | Где |
|-----|-----|
| HTTP-клиент (Axios, JWT, обработка 401) | `src/api/client.js` |
| Состояние входа (Pinia) | `src/stores/auth.js` |
| Маршруты и guard | `src/router/index.js` |
| Экраны | `src/views/LoginView.vue`, `HomeView.vue`, `NotFoundView.vue` |
| Шапка и навигация | `src/App.vue` |
| Тесты (Vitest) | `src/**/__tests__/*.spec.js` |

## Требования

* **Node.js ^22.18 или ≥ 24.12** (этого требует актуальный `create-vue`; Node 18 из методички уже не подходит) и npm ≥ 11.
  С npm 10.9 установка может падать с ошибкой `Cannot read properties of null (reading 'edgesOut')` — обновите npm: `npm install -g npm@11`.
* Запущенный бэкенд из лабораторной № 5 на `http://localhost:8000`.

## 1. Запуск бэкенда

Вариант А — без Docker (SQLite, Redis не обязателен):

```bash
cd ..                                   # корень репозитория
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite+aiosqlite:///./app.db
export ADMIN_BOOTSTRAP_USERNAME=admin ADMIN_BOOTSTRAP_PASSWORD=ChangeMe-Admin-2026
uvicorn app.main:app --reload           # http://localhost:8000/docs
python scripts/seed_demo.py             # демо-курсы и пользователь student / Student-passw0rd
```

Вариант Б — Docker Compose (PostgreSQL, Redis, RabbitMQ): `docker compose up --build`, затем `python scripts/seed_demo.py`.

CORS: при `ENVIRONMENT=development` (по умолчанию) и незаданной `CORS_ORIGINS` бэкенд разрешает
`http://localhost:5173` и `http://127.0.0.1:5173`. Проверка (шаг 2 методички):

```bash
curl -i -X OPTIONS http://localhost:8000/courses \
  -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: GET"
# access-control-allow-origin: http://localhost:5173
```

## 2. Запуск фронтенда

```bash
cd frontend-app
npm install
cp .env.example .env.local              # VITE_API_BASE_URL=http://localhost:8000
npm run dev                             # http://localhost:5173
```

Переменные окружения:

| Переменная | Значение по умолчанию | Назначение |
|------------|-----------------------|------------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | адрес FastAPI; префикс `VITE_` обязателен, иначе Vite не передаст её в браузер |

`.env.local` не коммитится (правило `*.local` в `.gitignore`). Порт 5173 закреплён (`strictPort`): если он занят,
Vite не уйдёт молча на 5174, где бэкенд не разрешает CORS.

Учётные записи: `admin / ChangeMe-Admin-2026` (bootstrap-администратор), `student / Student-passw0rd` (создаёт `seed_demo.py`).

## 3. Сквозной сценарий

| Шаг | Ожидаемое поведение | Скриншот |
|-----|---------------------|----------|
| Открыть `http://localhost:5173/` | редирект на `/login` | `docs/screenshots/01-redirect-login.png` |
| Ввести неверный пароль | «Invalid username or password» | `docs/screenshots/02-invalid-password.png` |
| Ввести верный пароль | редирект на `/`, список курсов из БД | `docs/screenshots/03-home-list.png` |
| DevTools → Network | `OPTIONS /courses` 200, `GET /courses` 200 с `Authorization: Bearer …` | `docs/screenshots/04-network.png` |
| Обновить страницу | список остаётся (токен в `localStorage`) | — |
| Создать курс в Swagger и обновить | новый курс в списке | `docs/screenshots/05-new-course.png` |
| Нажать Logout | редирект на `/login` | `docs/screenshots/06-logout.png` |

<!-- Вставьте скриншоты после прохождения сценария, например:
![Редирект на /login](../docs/screenshots/01-redirect-login.png)
-->

Если что-то не работает:

| Симптом | Причина |
|---------|---------|
| «Сервер недоступен или запрос заблокирован (CORS)» при входе | бэкенд не запущен, либо фронтенд открыт не с `http://localhost:5173` (CORS), либо `CORS_ORIGINS=""` |
| В консоли `blocked by CORS policy` | origin фронтенда не в `CORS_ORIGINS`; проверьте порт и `localhost` против `127.0.0.1` |
| Не редиректит на `/login` | в `localStorage` остался старый `access_token` — удалите его в DevTools → Application |
| После 30 минут перекидывает на `/login` | истёк access-токен (так задумано: refresh-токен в MVP не используется) |
| «Слишком много попыток входа» | сработал лимит попыток входа бэкенда (лаб. № 5), подождите минуту |

## Тесты и проверки

```bash
npm run test:unit          # Vitest в режиме watch
npm run test:run           # однократный прогон (53 теста)
npm run lint:check         # oxlint + ESLint без автоисправлений
npm run format:check       # Prettier
npm run build              # production-сборка в dist/
```

«Живой» сквозной тест против настоящего бэкенда: jsdom работает с origin `http://localhost:5173` и выполняет
CORS-проверки как браузер, поэтому без настроенного CORS тест падает.

```bash
uvicorn app.main:app --port 8000      # в корне репозитория
python scripts/seed_demo.py
npm run test:live                     # login → JWT → список из БД → logout; новый курс виден после обновления
```
