from __future__ import annotations

import asyncio

from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.infrastructure.db.models import Reminder, Task
from app.infrastructure.db.session import async_session_factory
from app.workers.tasks import send_telegram_reminder


async def enqueue_due_reminders() -> None:
    async with async_session_factory() as session:
        stmt = (
            select(Reminder)
            .where(
                Reminder.status == "scheduled",
                Reminder.delivery_channel == "telegram",
            )
            .order_by(Reminder.remind_at)
            .limit(200)
        )
        now = datetime.now(UTC)
        reminders = list((await session.scalars(stmt)).all())
        for reminder in reminders:
            task = await session.get(Task, reminder.task_id) if reminder.task_id else None
            if task is not None and task.status in {"done", "cancelled", "archived"}:
                reminder.status = "cancelled"
                continue
            if reminder.remind_at > now:
                continue
            reminder.status = "queued"
            send_telegram_reminder.send(reminder.id)
        await session.commit()


async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(enqueue_due_reminders, "interval", seconds=10, max_instances=1)
    scheduler.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
