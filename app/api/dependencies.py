from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.core.config import get_settings
from app.infrastructure.idempotency import (
    IdempotencyStore,
    MemoryIdempotencyStore,
    RedisIdempotencyStore,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        from redis.asyncio import Redis

        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        app.state.redis_client = redis_client
        app.state.idempotency_store = RedisIdempotencyStore(redis_client)
    except Exception:
        app.state.redis_client = None
        app.state.idempotency_store = MemoryIdempotencyStore()
    try:
        yield
    finally:
        redis_client = getattr(app.state, "redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()


def get_idempotency_store(request: Request) -> IdempotencyStore:
    return request.app.state.idempotency_store
