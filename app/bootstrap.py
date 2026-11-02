"""
Создание первого администратора (bootstrap).

Логин и пароль берутся из ADMIN_BOOTSTRAP_USERNAME / ADMIN_BOOTSTRAP_PASSWORD
(в Kubernetes — Secret app-bootstrap-secrets). Операция идемпотентна: если
пользователь уже есть, ничего не меняется (пароль существующего админа
этим механизмом не перезаписывается). Запускается при старте API и как
`python -m app.bootstrap` после миграций.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import ROLE_ADMIN, hash_password, validate_password_policy
from app.config import admin_bootstrap
from app.db_models.user import User

logger = logging.getLogger(__name__)


async def ensure_bootstrap_admin(session_factory=None) -> bool:
    """True, если администратор создан в этом вызове."""
    username, password = admin_bootstrap()
    if not username or not password:
        return False
    if session_factory is None:
        from app.database import AsyncSessionLocal as session_factory
    try:
        validate_password_policy(password)
        async with session_factory() as session:
            exists = await session.execute(select(User).where(User.username == username.lower()))
            if exists.scalar_one_or_none() is not None:
                return False
            session.add(
                User(username=username.lower(), hashed_password=hash_password(password),
                     role=ROLE_ADMIN)
            )
            await session.commit()
            logger.info("Создан bootstrap-администратор %r", username)
            return True
    except IntegrityError:
        return False  # другая реплика создала его одновременно
    except ValueError as exc:
        logger.error("ADMIN_BOOTSTRAP_PASSWORD не проходит политику паролей: %s", exc)
    except SQLAlchemyError as exc:
        logger.warning("Bootstrap администратора пропущен (схема БД ещё не готова?): %s", exc)
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ensure_bootstrap_admin())
