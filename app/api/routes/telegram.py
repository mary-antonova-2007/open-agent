from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import AgentOrchestrator
from app.api.dependencies import get_idempotency_store
from app.bot.telegram_service import TelegramUpdateService
from app.core.config import Settings, get_settings
from app.infrastructure.db.session import get_session
from app.infrastructure.idempotency import IdempotencyStore

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook/{secret}")
async def telegram_webhook(
    secret: str,
    update: dict[str, Any],
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    idempotency_store: IdempotencyStore = Depends(get_idempotency_store),
) -> dict[str, str]:
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")
    service = TelegramUpdateService(
        session=session,
        orchestrator=AgentOrchestrator(session),
        idempotency_store=idempotency_store,
    )
    await service.handle_update(update)
    await session.commit()
    return {"status": "ok"}
