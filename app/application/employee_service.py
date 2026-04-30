from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.schemas import EmployeeContext
from app.infrastructure.db.models import Employee, Permission, Role


class EmployeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> EmployeeContext | None:
        stmt = (
            select(Employee)
            .where(Employee.telegram_user_id == telegram_user_id, Employee.is_active.is_(True))
            .options(
                selectinload(Employee.role).selectinload(Role.permissions),
                selectinload(Employee.department),
            )
        )
        employee = await self.session.scalar(stmt)
        if employee is None:
            return None
        permissions: set[str] = set()
        role_name = None
        if employee.role is not None:
            role_name = employee.role.name
            permissions = {permission.code for permission in employee.role.permissions}
        department_name = employee.department.name if employee.department else None
        return EmployeeContext(
            id=employee.id,
            full_name=employee.full_name,
            telegram_user_id=employee.telegram_user_id,
            role=role_name,
            department=department_name,
            permissions=permissions,
            timezone=employee.timezone,
        )

    async def permission_codes(self) -> list[str]:
        rows = await self.session.scalars(select(Permission.code).order_by(Permission.code))
        return list(rows)
