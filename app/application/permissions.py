from __future__ import annotations

from dataclasses import dataclass

from app.application.schemas import EmployeeContext


class PermissionDeniedError(Exception):
    pass


@dataclass(frozen=True)
class PermissionGuard:
    """Application-level permission checks independent from LLM prompts."""

    def require(self, employee: EmployeeContext, permission: str) -> None:
        if permission not in employee.permissions and "*" not in employee.permissions:
            msg = f"Employee {employee.id} lacks permission {permission}"
            raise PermissionDeniedError(msg)

    def can(self, employee: EmployeeContext, permission: str) -> bool:
        return permission in employee.permissions or "*" in employee.permissions
