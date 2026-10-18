"""
Простая in-memory имитация Redis для тестов.

Реализует ровно тот минимальный набор команд, который использует
app/redis_client.py (get/set/incr/expire/ttl/scan_iter/delete/ping/
close), так что тесты могут проверять реальную логику кэширования и
rate limiting без поднятого Redis-сервера и без дополнительных
зависимостей (fakeredis и т.п.).
"""

import fnmatch
import time
from typing import Dict, Optional


class FakeRedis:
    def __init__(self) -> None:
        self._store: Dict[str, str] = {}
        self._expiry: Dict[str, float] = {}

    def _purge_if_expired(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and exp < time.monotonic():
            self._store.pop(key, None)
            self._expiry.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def get(self, key: str) -> Optional[str]:
        self._purge_if_expired(key)
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self._store[key] = value
        if ex is not None:
            self._expiry[key] = time.monotonic() + ex
        else:
            self._expiry.pop(key, None)

    async def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        current = int(self._store.get(key, "0")) + 1
        self._store[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> None:
        self._expiry[key] = time.monotonic() + seconds

    async def ttl(self, key: str) -> int:
        exp = self._expiry.get(key)
        if exp is None:
            return -1
        return max(0, int(exp - time.monotonic()))

    async def scan_iter(self, match: str = "*"):
        for key in list(self._store.keys()):
            if fnmatch.fnmatch(key, match):
                yield key

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                self._expiry.pop(key, None)
                count += 1
        return count
