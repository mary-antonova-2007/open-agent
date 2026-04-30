from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import AgentOrchestrator
from app.application.employee_service import EmployeeService
from app.infrastructure.idempotency import IdempotencyStore, MemoryIdempotencyStore
from app.infrastructure.db.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


class TelegramUpdateService:
    def __init__(
        self,
        session: AsyncSession,
        orchestrator: AgentOrchestrator,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self.session = session
        self.orchestrator = orchestrator
        self.idempotency_store = idempotency_store or MemoryIdempotencyStore()

    async def handle_update(self, update: dict[str, Any]) -> str:
        update_id = update.get("update_id")
        if update_id is not None:
            first_seen = await self.idempotency_store.mark_once(
                f"telegram:update:{update_id}", ttl_seconds=86_400
            )
            if not first_seen:
                return "duplicate"
        message = update.get("message") or update.get("edited_message") or {}
        from_user = message.get("from") or {}
        text = message.get("text") or message.get("caption") or ""
        chat = message.get("chat") or {}
        telegram_user_id = from_user.get("id")
        telegram_chat_id = chat.get("id")
        if telegram_user_id is None:
            return "ignored"
        employee = await EmployeeService(self.session).get_by_telegram_user_id(
            int(telegram_user_id)
        )
        if employee is None:
            logger.warning(
                "Unauthorized Telegram user attempted access: telegram_user_id=%s username=%s full_name=%s",
                telegram_user_id,
                from_user.get("username"),
                " ".join(
                    part
                    for part in [from_user.get("first_name"), from_user.get("last_name")]
                    if part
                ),
            )
            return "unauthorized"
        session = await self._get_or_create_session(
            telegram_chat_id=int(telegram_chat_id or telegram_user_id), employee_id=employee.id
        )
        self.session.add(
            ChatMessage(
                session_id=session.id,
                direction="in",
                message_text=text,
                telegram_message_id=message.get("message_id"),
            )
        )
        response = await self.orchestrator.handle_text(
            employee=employee, text=text, source="telegram", session_id=session.id
        )
        return response

    async def _get_or_create_session(
        self, *, telegram_chat_id: int, employee_id: int
    ) -> ChatSession:
        stmt = select(ChatSession).where(
            ChatSession.telegram_chat_id == telegram_chat_id,
            ChatSession.employee_id == employee_id,
        )
        session = await self.session.scalar(stmt)
        if session is not None:
            return session
        session = ChatSession(telegram_chat_id=telegram_chat_id, employee_id=employee_id)
        self.session.add(session)
        await self.session.flush()
        return session
