from __future__ import annotations

from fastapi import FastAPI

from app.api.dependencies import lifespan
from app.api.routes import health, telegram
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(telegram.router)
    return app
