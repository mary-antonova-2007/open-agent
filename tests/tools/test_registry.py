from __future__ import annotations

from pydantic import BaseModel
import pytest

from app.application.permissions import PermissionDeniedError
from app.application.schemas import EmployeeContext, ToolResult
from app.domain.enums import DangerLevel
from app.tools.registry import ToolDefinition, ToolRegistry


class DemoInput(BaseModel):
    value: str


async def handler(
    _actor: EmployeeContext, payload: BaseModel, _trace_id: str | None
) -> ToolResult:
    parsed = DemoInput.model_validate(payload)
    return ToolResult(ok=True, data={"value": parsed.value})


async def test_registry_requires_permission() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition("demo", "Demo", DemoInput, "demo.run", DangerLevel.safe, handler)
    )
    actor = EmployeeContext(id=1, full_name="User", telegram_user_id=1, permissions=set())
    with pytest.raises(PermissionDeniedError):
        await registry.execute(name="demo", actor=actor, payload={"value": "x"})


async def test_registry_blocks_unconfirmed_dangerous_tool() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition("demo", "Demo", DemoInput, "demo.run", DangerLevel.dangerous, handler)
    )
    actor = EmployeeContext(id=1, full_name="Admin", telegram_user_id=1, permissions={"demo.run"})
    result = await registry.execute(name="demo", actor=actor, payload={"value": "x"})
    assert result.ok is False
    assert result.code == "needs_confirmation"


async def test_registry_executes_confirmed_tool() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition("demo", "Demo", DemoInput, "demo.run", DangerLevel.dangerous, handler)
    )
    actor = EmployeeContext(id=1, full_name="Admin", telegram_user_id=1, permissions={"demo.run"})
    result = await registry.execute(
        name="demo", actor=actor, payload={"value": "x"}, confirmed=True
    )
    assert result.ok is True
    assert result.data == {"value": "x"}
