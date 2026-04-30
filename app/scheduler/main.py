from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler


async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
