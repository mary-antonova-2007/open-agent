from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.infrastructure.db.models import Department, Employee, Permission, Role
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
    async with async_session_factory() as session:
        role = await session.scalar(select(Role).where(Role.name == "admin"))
        if role is None:
            role = Role(name="admin", description="System administrator")
            session.add(role)
            await session.flush()
        department = await session.scalar(select(Department).where(Department.name == "Admin"))
        if department is None:
            department = Department(name="Admin")
            session.add(department)
            await session.flush()
        for code in DEFAULT_PERMISSIONS:
            permission = await session.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code, description=f"Permission {code}")
                session.add(permission)
                await session.flush()
            if permission not in role.permissions:
                role.permissions.append(permission)
        if settings.admin_telegram_user_id is not None:
            employee = await session.scalar(
                select(Employee).where(Employee.telegram_user_id == settings.admin_telegram_user_id)
            )
            if employee is None:
                session.add(
                    Employee(
                        telegram_user_id=settings.admin_telegram_user_id,
                        full_name=settings.admin_full_name,
                        role_id=role.id,
                        department_id=department.id,
                        is_active=True,
                    )
                )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
