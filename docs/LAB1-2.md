# Educational Platform API — Курсы, студенты и зачисления

Лабораторная работа № 1 «Разработка REST API на FastAPI» +
Лабораторная работа № 2 «Продвинутый REST API: БД, кэширование и
фоновые задачи».
Вариант 8: **Курсы и студенты**.

## Что реализовано (Лаб. №2, 5 улучшений)

1. **Постоянное хранилище.** In-memory словарь из лабораторной №1
   заменён на таблицы SQLAlchemy (async): `courses`, `students`,
   `enrollments`. `enrollments` — association object для связи
   Many-to-Many между курсом и студентом, хранящий дату зачисления,
   оценку и статус.
2. **Кэширование.** `GET /courses?instructor=...` кэшируется в Redis
   на 3 минуты. При создании/обновлении/удалении курса кэш
   инвалидируется.
3. **Rate limiting.** `POST /enrollments` (запись на курс) ограничен
   5 запросами в минуту на одного студента (по `student_id`, схема
   Redis `INCR` + `EXPIRE`).
4. **Фоновая задача (Celery).** При завершении курса
   (`PATCH /enrollments/{id}/complete`) в очередь ставится задача,
   генерирующая PDF-сертификат — не блокирует ответ API.
5. **Админ-панель.** `GET /admin` — HTML-дашборд с рейтингом
   популярности курсов по количеству записей;
   `GET /admin/courses/popularity` — тот же рейтинг в JSON.

Если Redis недоступен (не запущен), приложение не падает — кэш и
rate limiting просто отключаются (fail-open), об этом пишется
предупреждение в лог. Это удобно для локальной разработки/тестов без
поднятого Redis.

## Модель данных

| Таблица       | Поля                                                                 |
|---------------|-----------------------------------------------------------------------|
| `courses`     | `id`, `title`, `description`, `instructor`, `duration_hours`         |
| `students`    | `id`, `full_name`, `email` (уникальный)                              |
| `enrollments` | `id`, `student_id`, `course_id`, `enrollment_date`, `grade`, `status` (`in_progress`/`completed`), `certificate_path`. Уникальна пара `(student_id, course_id)`. |

## Эндпоинты

### Курсы

| Метод  | Путь                  | Описание                                                        |
|--------|-----------------------|-------------------------------------------------------------------|
| GET    | `/courses`             | Список курсов. Параметры: `instructor`, `min_duration`, `max_duration`. Кэш 3 мин. при фильтре `instructor` |
| GET    | `/courses/{course_id}` | Получить курс по ID                                               |
| POST   | `/courses`              | Создать курс (инвалидирует кэш)                                   |
| PUT    | `/courses/{course_id}` | Обновить курс (инвалидирует кэш)                                  |
| DELETE | `/courses/{course_id}` | Удалить курс (инвалидирует кэш)                                   |

### Студенты

| Метод | Путь               | Описание                     |
|-------|--------------------|-------------------------------|
| GET   | `/students`         | Список студентов              |
| GET   | `/students/{id}`    | Студент по ID                 |
| POST  | `/students`          | Зарегистрировать студента (email уникален) |

### Зачисления

| Метод | Путь                                | Описание                                                    |
|-------|-------------------------------------|-----------------------------------------------------------------|
| POST  | `/enrollments`                       | Записать студента на курс. **Лимит: 5 запросов/мин на студента** |
| GET   | `/enrollments`                       | Список записей. Фильтры: `student_id`, `course_id`              |
| PATCH | `/enrollments/{id}/complete`         | Завершить курс, выставить оценку → фоновая генерация сертификата |

### Админ-панель

| Метод | Путь                        | Описание                              |
|-------|-----------------------------|-----------------------------------------|
| GET   | `/admin`                     | HTML-дашборд: рейтинг популярности курсов |
| GET   | `/admin/courses/popularity`  | Тот же рейтинг в JSON                    |

Коды ответа: `200`, `201`, `204`, `400`, `404`, `422`, `429 Too Many Requests`.

## Установка

```bash
pip install -r requirements.txt
```

## Запуск без Docker (минимально — без Redis/Celery)

```bash
uvicorn app.main:app --reload
```

Приложение полностью работоспособно и без Redis: SQLite-БД создаётся
автоматически при старте, а кэширование/rate limiting просто
отключаются с предупреждением в лог. Фоновая задача в этом случае
всё равно будет вызвана через `.delay()`, но без запущенного
Celery-воркера и брокера она не выполнится — для её реальной работы
нужен Redis + воркер (см. ниже).

## Запуск с Redis и Celery (полная схема)

### Через docker-compose (рекомендуется)

```bash
docker compose up --build
```

Поднимает: `api` (http://127.0.0.1:8000), `redis`, `celery-worker`,
`flower` (мониторинг задач, http://127.0.0.1:5555).

### Вручную (без Docker)

```bash
# Терминал 1 — Redis (например, через локальную установку)
redis-server

# Терминал 2 — приложение
export REDIS_URL=redis://localhost:6379/0
export CELERY_BROKER_URL=redis://localhost:6379/0
uvicorn app.main:app --reload

# Терминал 3 — Celery-воркер (генерирует сертификаты)
export CELERY_BROKER_URL=redis://localhost:6379/0
celery -A app.celery_app.celery_app worker --loglevel=info

# Терминал 4 (опционально) — Flower, мониторинг задач
celery -A app.celery_app.celery_app flower --port=5555
```

Документация: http://127.0.0.1:8000/docs · Админ-панель: http://127.0.0.1:8000/admin

## Миграции (Alembic)

Схема БД описана как в ORM-моделях (`app/db_models/`, применяются
автоматически при старте через `create_all` — удобно для лабораторной
работы), так и в виде миграции Alembic (`migrations/versions/0001_initial.py`)
— для случая, когда БД уже существует и её нужно обновлять
контролируемо, как в production:

```bash
# Применить все миграции к БД, заданной в alembic.ini
alembic upgrade head

# Создать новую миграцию после изменения моделей в app/db_models/
alembic revision --autogenerate -m "описание изменений"
```

## Примеры запросов

Создать курс:

```bash
curl -X POST http://127.0.0.1:8000/courses \
  -H "Content-Type: application/json" \
  -d '{"title":"Введение в базы данных","description":"Основы SQL","instructor":"Иванов И.И.","duration_hours":36}'
```

Зарегистрировать студента:

```bash
curl -X POST http://127.0.0.1:8000/students \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Смирнова Анна Сергеевна","email":"anna@example.com"}'
```

Записать студента (id=1) на курс (id=1):

```bash
curl -X POST http://127.0.0.1:8000/enrollments \
  -H "Content-Type: application/json" \
  -d '{"student_id":1,"course_id":1}'
```

Завершить курс с оценкой (запустит генерацию сертификата в фоне):

```bash
curl -X PATCH http://127.0.0.1:8000/enrollments/1/complete \
  -H "Content-Type: application/json" \
  -d '{"grade":92.5}'
```

Рейтинг популярности курсов:

```bash
curl http://127.0.0.1:8000/admin/courses/popularity
```

## Тесты

```bash
pytest -v
```

Тесты используют:
- **SQLite in-memory** вместо файла `app.db` — каждая проверка
  получает чистую БД (`app/tests/conftest.py`, фикстура `db_session`).
- **Лёгкую in-memory имитацию Redis** (`app/tests/fake_redis.py`) —
  без внешних зависимостей и без поднятого сервера, но с реальной
  логикой `INCR`/`EXPIRE`/`TTL`, поэтому тест rate limiting и тест
  инвалидации кэша проверяют настоящее поведение, а не заглушки.
- **`CELERY_TASK_ALWAYS_EAGER=true`** — фоновая задача генерации
  сертификата выполняется синхронно в процессе теста, без брокера и
  воркера.

Файлы тестов:
- `app/tests/test_courses.py` — CRUD + кэширование фильтра по преподавателю.
- `app/tests/test_students.py` — CRUD, уникальность email.
- `app/tests/test_enrollments.py` — запись на курс, дубликаты, 404,
  **rate limiting (5/мин)**, завершение курса и генерация сертификата.
- `app/tests/test_admin.py` — рейтинг популярности курсов.

## Структура проекта

```
my_fastapi_project/
├── app/
│   ├── main.py                    # FastAPI-приложение, lifespan (БД + Redis)
│   ├── database.py                # асинхронный движок SQLAlchemy, get_db
│   ├── enums.py                   # EnrollmentStatus
│   ├── redis_client.py            # кэширование + rate limiting (fail-open)
│   ├── celery_app.py              # конфигурация Celery
│   ├── tasks.py                   # генерация PDF-сертификата
│   ├── db_models/                 # ORM-модели SQLAlchemy
│   │   ├── course.py
│   │   ├── student.py
│   │   └── enrollment.py          # association object (M2M + доп. поля)
│   ├── models/                    # Pydantic-схемы (request/response)
│   │   ├── course.py
│   │   ├── student.py
│   │   └── enrollment.py
│   ├── routers/
│   │   ├── courses.py             # CRUD + кэш
│   │   ├── students.py            # CRUD
│   │   ├── enrollments.py         # запись, rate limit, завершение курса
│   │   └── admin.py                # рейтинг популярности (HTML + JSON)
│   └── tests/
│       ├── conftest.py            # фикстуры: тестовая БД, fake Redis, client
│       ├── fake_redis.py
│       ├── test_courses.py
│       ├── test_students.py
│       ├── test_enrollments.py
│       └── test_admin.py
├── migrations/                    # Alembic
│   ├── env.py
│   ├── script.py.mako
│   └── versions/0001_initial.py
├── alembic.ini
├── Dockerfile
├── docker-compose.yml             # api + redis + celery-worker + flower
├── requirements.txt
└── README.md
```

## Примечания по реализации

- **Почему `status` в `enrollments` хранится как `String`, а не
  `sa.Enum`?** Для простоты и переносимости между SQLite и PostgreSQL
  без дополнительной миграции типа. На уровне приложения используется
  строгий enum `app.enums.EnrollmentStatus` — Pydantic и Python-код
  работают с ним типобезопасно, в БД просто попадает его строковое
  значение.
- **Почему `enrollments`, а не `secondary=` в `relationship`?**
  Задание требует хранить дату зачисления и оценку на самой связи —
  для этого используется паттерн **association object**
  (полноценная модель `Enrollment` с `relationship` в обе стороны), а
  не «чистая» many-to-many таблица без дополнительных атрибутов.
- **Fail-open для Redis.** Решение осознанное: недоступность
  кэша/rate limiter не должна останавливать основной функционал API.
  В production это стоит обсуждать отдельно (иногда rate limiting
  должен быть fail-closed из соображений безопасности) — здесь выбран
  вариант, удобный для лабораторной работы и тестирования.
- **Сертификаты.** Если `reportlab` не установлен, задача создаёт
  текстовую заглушку вместо PDF — сама механика фоновой задачи
  (постановка в очередь, retry при ошибке) при этом не меняется.
