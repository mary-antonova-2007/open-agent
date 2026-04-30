from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message

from app.agents.orchestrator import AgentOrchestrator
from app.bot.telegram_service import TelegramUpdateService
from app.core.config import get_settings
from app.infrastructure.db.session import async_session_factory

router = Router()


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
    await message.answer(result)


async def main() -> None:
    settings = get_settings()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
