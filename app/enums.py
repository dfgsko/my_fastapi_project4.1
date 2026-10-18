"""
Общие перечисления проекта.

Вынесены в отдельный модуль, чтобы избежать дублирования между
SQLAlchemy-моделями (app/db_models) и Pydantic-схемами (app/models):
оба слоя импортируют один и тот же enum.
"""

import enum


class EnrollmentStatus(str, enum.Enum):
    """Статус записи студента на курс."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
