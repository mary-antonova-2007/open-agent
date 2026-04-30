from __future__ import annotations

import pytest

from app.application.permissions import PermissionDeniedError, PermissionGuard
from app.application.schemas import EmployeeContext


def test_permission_guard_allows_known_permission() -> None:
    actor = EmployeeContext(
        id=1,
        full_name="Admin",
        telegram_user_id=1,
        permissions={"task.create"},
    )
    PermissionGuard().require(actor, "task.create")


def test_permission_guard_denies_missing_permission() -> None:
    actor = EmployeeContext(id=1, full_name="User", telegram_user_id=1, permissions=set())
    with pytest.raises(PermissionDeniedError):
        PermissionGuard().require(actor, "task.create")


def test_permission_guard_allows_wildcard() -> None:
    actor = EmployeeContext(id=1, full_name="Admin", telegram_user_id=1, permissions={"*"})
    PermissionGuard().require(actor, "anything")
