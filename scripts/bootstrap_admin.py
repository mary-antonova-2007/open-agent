from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.db.session import async_session_factory

DEFAULT_PERMISSIONS = [
    "*",
    "task.create",
    "task.read",
    "task.update.self",
    "task.update.any",
    "project.read",
    "contract.read",
    "memory.update",
    "memory.note.append",
    "knowledge.search",
    "counterparty.read",
    "item.read",
    "file.read",
    "file.write",
    "file.archive",
]


async def main() -> None:
    settings = get_settings()
    if settings.admin_telegram_user_id is None:
        msg = "ADMIN_TELEGRAM_USER_ID is required"
        raise RuntimeError(msg)

    async with async_session_factory() as session:
        await session.execute(
            text(
                """
                insert into roles (name, description)
                values (:name, :description)
                on conflict (name) do update set description=excluded.description
                """
            ),
            {"name": "admin", "description": "System administrator"},
        )
        await session.execute(
            text(
                """
                insert into departments (name)
                values (:name)
                on conflict (name) do nothing
                """
            ),
            {"name": "Admin"},
        )
        for code in DEFAULT_PERMISSIONS:
            await session.execute(
                text(
                    """
                    insert into permissions (code, description)
                    values (:code, :description)
                    on conflict (code) do update set description=excluded.description
                    """
                ),
                {"code": code, "description": f"Permission {code}"},
            )
        await session.execute(
            text(
                """
                insert into role_permissions (role_id, permission_id)
                select r.id, p.id
                from roles r
                cross join permissions p
                where r.name=:role
                on conflict do nothing
                """
            ),
            {"role": "admin"},
        )
        await session.execute(
            text(
                """
                insert into employees (
                    telegram_user_id,
                    full_name,
                    role_id,
                    department_id,
                    timezone,
                    is_active
                )
                select :telegram_user_id, :full_name, r.id, d.id, :timezone, true
                from roles r
                cross join departments d
                where r.name=:role and d.name=:department
                on conflict (telegram_user_id) do update set
                    full_name=excluded.full_name,
                    role_id=excluded.role_id,
                    department_id=excluded.department_id,
                    timezone=excluded.timezone,
                    is_active=true
                """
            ),
            {
                "telegram_user_id": settings.admin_telegram_user_id,
                "full_name": settings.admin_full_name,
                "timezone": "Europe/Moscow",
                "role": "admin",
                "department": "Admin",
            },
        )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
