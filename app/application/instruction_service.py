from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.permissions import PermissionGuard
from app.application.schemas import EmployeeContext
from app.infrastructure.db.models import AgentInstruction


class AgentInstructionService:
    def __init__(self, session: AsyncSession, guard: PermissionGuard | None = None) -> None:
        self.session = session
        self.guard = guard or PermissionGuard()

    async def retrieve(
        self,
        actor: EmployeeContext,
        *,
        query: str,
        scopes: list[str] | None = None,
        limit: int = 6,
    ) -> list[dict[str, str | int]]:
        self.guard.require(actor, "agent_instruction.read")
        scopes = scopes or self._infer_scopes(query)
        stmt = (
            select(AgentInstruction)
            .where(
                AgentInstruction.status == "approved",
                or_(
                    AgentInstruction.scope.in_(scopes),
                    AgentInstruction.scope == "global",
                ),
            )
            .order_by(AgentInstruction.priority.desc(), AgentInstruction.id)
            .limit(limit)
        )
        rows = list((await self.session.scalars(stmt)).all())
        return [
            {
                "id": row.id,
                "title": row.title,
                "scope": row.scope,
                "priority": row.priority,
                "content": row.content,
            }
            for row in rows
        ]

    @staticmethod
    def _infer_scopes(query: str) -> list[str]:
        lowered = query.lower()
        scopes = ["global"]
        if any(word in lowered for word in ("файл", "диск", "папк", "кдз", "кдп", "фото")):
            scopes.append("files")
        if any(word in lowered for word in ("задач", "напом")):
            scopes.append("tasks")
        if any(word in lowered for word in ("договор", "проект", "издел", "контрагент")):
            scopes.append("crm")
        return scopes
