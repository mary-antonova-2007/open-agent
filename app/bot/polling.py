from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message

from app.agents.orchestrator import AgentOrchestrator
from app.bot.telegram_service import TelegramUpdateService
from app.core.config import get_settings
from app.application.employee_service import EmployeeService
from app.application.file_service import FileService
from app.infrastructure.db.models import ChatMessage
from app.infrastructure.db.session import async_session_factory

router = Router()
TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_MESSAGE_LIMIT = 3500


@router.message(F.text | F.caption)
async def handle_message(message: Message) -> None:
    async with async_session_factory() as session:
        service = TelegramUpdateService(
            session=session,
            orchestrator=AgentOrchestrator(session),
        )
        result = await service.handle_update(
            {"message": message.model_dump(mode="json", by_alias=True)}
        )
        await session.commit()
    if result == "unauthorized":
        await message.answer(
            "Вы не зарегистрированы в системе. "
            f"Передайте администратору ваш Telegram ID: {message.from_user.id}."
        )
        return
    if result == "duplicate":
        return
    await answer_safely(message, result)


@router.message(F.document)
async def handle_document(message: Message, bot: Bot) -> None:
    if message.from_user is None or message.document is None:
        return
    async with async_session_factory() as session:
        employee = await EmployeeService(session).get_by_telegram_user_id(message.from_user.id)
        if employee is None:
            await message.answer(
                "Вы не зарегистрированы в системе. "
                f"Передайте администратору ваш Telegram ID: {message.from_user.id}."
            )
            return
        service = TelegramUpdateService(
            session=session,
            orchestrator=AgentOrchestrator(session),
        )
        chat_session = await service._get_or_create_session(
            telegram_chat_id=message.chat.id,
            employee_id=employee.id,
        )
        telegram_file = await bot.get_file(message.document.file_id)
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_tmp = Path(tmp_dir) / (message.document.file_name or "telegram_file")
            await bot.download_file(telegram_file.file_path, destination=local_tmp)
            stored = await FileService(session).save_inbox_file(
                employee,
                source_path=local_tmp,
                original_filename=message.document.file_name or "telegram_file",
                mime_type=message.document.mime_type,
            )
        state = dict(chat_session.state or {})
        state["pending_file"] = {
            "file_object_id": stored.file_object_id,
            "file_version_id": stored.file_version_id,
            "display_name": stored.display_name,
            "object_key": stored.object_key,
        }
        chat_session.state = state
        response = (
            f"Файл «{stored.display_name}» сохранил в твой Inbox.\n"
            "Скажи, что это за документ и куда положить. Например: "
            "«это договор № 123-456 по проекту Жуковка 35 от 26.02.2026» "
            "или «это КДП по изделию ...»."
        )
        session.add(
            ChatMessage(
                session_id=chat_session.id,
                direction="in",
                message_text=f"[file] {stored.display_name}",
                telegram_message_id=message.message_id,
            )
        )
        session.add(ChatMessage(session_id=chat_session.id, direction="out", message_text=response))
        await session.commit()
    await answer_safely(message, response)


async def answer_safely(message: Message, text: str) -> None:
    for chunk in split_telegram_message(text):
        await message.answer(chunk)


def split_telegram_message(text: str) -> list[str]:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= SAFE_MESSAGE_LIMIT:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, SAFE_MESSAGE_LIMIT)
        if split_at < SAFE_MESSAGE_LIMIT // 2:
            split_at = remaining.rfind(" ", 0, SAFE_MESSAGE_LIMIT)
        if split_at < SAFE_MESSAGE_LIMIT // 2:
            split_at = SAFE_MESSAGE_LIMIT
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


async def main() -> None:
    settings = get_settings()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
