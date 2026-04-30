from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        action: str,
        result: str,
        actor_employee_id: int | None = None,
        trace_id: str | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        tool_name: str | None = None,
        diff_summary: dict[str, Any] | None = None,
    ) -> AuditLog:
        row = AuditLog(
            trace_id=trace_id,
            actor_employee_id=actor_employee_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            tool_name=tool_name,
            result=result,
            diff_summary=diff_summary or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row
