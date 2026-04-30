from __future__ import annotations

import asyncio


async def main() -> None:
    # Dev placeholder. Production uses webhook through FastAPI.
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
