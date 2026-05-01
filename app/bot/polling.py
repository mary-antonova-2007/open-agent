from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message

from app.agents.orchestrator import AgentOrchestrator
from app.bot.telegram_service import TelegramUpdateService
from app.core.config import get_settings
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
