from __future__ import annotations

from typing import Protocol


class IdempotencyStore(Protocol):
    async def mark_once(self, key: str, *, ttl_seconds: int) -> bool:
        """Return True only for the first successful mark."""


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def mark_once(self, key: str, *, ttl_seconds: int) -> bool:
        _ = ttl_seconds
        if key in self._keys:
            return False
        self._keys.add(key)
        return True


class RedisIdempotencyStore:
    def __init__(self, redis_client: object) -> None:
        self.redis_client = redis_client

    async def mark_once(self, key: str, *, ttl_seconds: int) -> bool:
        # redis-py asyncio returns True for SET NX success and None otherwise.
        result = await self.redis_client.set(key, "1", ex=ttl_seconds, nx=True)
        return bool(result)
