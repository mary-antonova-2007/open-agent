from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.application.permissions import PermissionGuard
from app.application.schemas import EmployeeContext, ToolResult
from app.domain.enums import DangerLevel

ToolHandler = Callable[[EmployeeContext, BaseModel, str | None], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: type[BaseModel]
    required_permission: str
    danger_level: DangerLevel
    handler: ToolHandler | None = None

    @property
    def requires_confirmation(self) -> bool:
        return self.danger_level == DangerLevel.dangerous


class ToolRegistry:
    def __init__(self, guard: PermissionGuard | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.guard = guard or PermissionGuard()

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            msg = f"Tool already registered: {definition.name}"
            raise ValueError(msg)
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    async def execute(
        self,
        *,
        name: str,
        actor: EmployeeContext,
        payload: dict[str, Any],
        trace_id: str | None = None,
        confirmed: bool = False,
    ) -> ToolResult:
        definition = self.get(name)
        self.guard.require(actor, definition.required_permission)
        if definition.requires_confirmation and not confirmed:
            return ToolResult(
                ok=False,
                code="needs_confirmation",
                message="Action requires confirmation",
            )
        if definition.handler is None:
            return ToolResult(
                ok=False,
                code="not_implemented",
                message="Tool handler is not wired yet",
            )
        parsed = definition.input_schema.model_validate(payload)
        return await definition.handler(actor, parsed, trace_id)
