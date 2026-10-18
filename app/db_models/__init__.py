"""
ORM-модели проекта (SQLAlchemy).

Импортируем все модули с моделями здесь, чтобы при простом
`import app.db_models` все классы регистрировались в
Base.metadata — это важно для `Base.metadata.create_all` в
app/main.py и для Alembic autogenerate в migrations/env.py.
"""

from app.db_models import course, student, enrollment  # noqa: F401
