from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import dramatiq
import httpx
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings
from app.infrastructure.db.models import Employee, Reminder, Task
from app.infrastructure.db.session import async_session_factory

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

redis_broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(redis_broker)


@dramatiq.actor
def send_telegram_reminder(reminder_id: int) -> None:
    asyncio.run(_send_telegram_reminder(reminder_id))


async def _send_telegram_reminder(reminder_id: int) -> None:
    settings = get_settings()
    async with async_session_factory() as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder is None:
            return
        if reminder.status not in {"queued", "scheduled"}:
            return

        employee = await session.get(Employee, reminder.recipient_id)
        task = await session.get(Task, reminder.task_id) if reminder.task_id else None
        if task is not None and task.status in {"done", "cancelled", "archived"}:
            reminder.status = "cancelled"
            await session.commit()
            return
        if employee is None or employee.telegram_user_id is None:
            reminder.status = "failed"
            reminder.metadata_ = {
                **(reminder.metadata_ or {}),
                "error": "recipient has no telegram_user_id",
            }
            await session.commit()
            return

        text = _format_reminder_text(reminder, task)
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": employee.telegram_user_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            reminder.status = "failed"
            reminder.metadata_ = {
                **(reminder.metadata_ or {}),
                "error": str(exc),
                "failed_at": datetime.now(UTC).isoformat(),
            }
            await session.commit()
            return

        reminder.status = "sent"
        reminder.sent_at = datetime.now(UTC)
        reminder.metadata_ = {
            **(reminder.metadata_ or {}),
            "telegram_sent": True,
        }
        await session.commit()


def _format_reminder_text(reminder: Reminder, task: Task | None) -> str:
    if task is not None:
        return f"Напоминание: {task.title}"
    return f"Напоминание: {reminder.message}"
