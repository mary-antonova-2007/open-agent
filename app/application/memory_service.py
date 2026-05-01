from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_service import AuditService
from app.application.permissions import PermissionGuard
from app.application.schemas import EmployeeContext, MemoryPatch
from app.infrastructure.db.models import Contract, EntityNote, Project


class EntityMemoryService:
    def __init__(self, session: AsyncSession, guard: PermissionGuard | None = None) -> None:
        self.session = session
        self.guard = guard or PermissionGuard()
        self.audit = AuditService(session)

    async def get_project_memory(
        self, actor: EmployeeContext, project_id: int
    ) -> dict[str, str | None]:
        self.guard.require(actor, "project.read")
        project = await self.session.get(Project, project_id)
        if project is None:
            return {}
        return {
            "summary": project.summary,
            "notes": project.notes,
            "current_issues": project.current_issues,
        }

    async def update_project_memory(
        self,
        actor: EmployeeContext,
        project_id: int,
        patch: MemoryPatch,
        *,
        trace_id: str | None = None,
    ) -> dict[str, str | None]:
        self.guard.require(actor, "memory.update")
        project = await self.session.get(Project, project_id)
        if project is None:
            return {}
        before = self._project_memory(project)
        if patch.summary is not None:
            project.summary = patch.summary
        if patch.notes is not None:
            project.notes = patch.notes
        if patch.current_issues is not None:
            project.current_issues = patch.current_issues
        after = self._project_memory(project)
        await self.audit.record(
            action="memory.project.update",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type="project",
            entity_id=project_id,
            tool_name="update_project_memory",
            diff_summary={"before": before, "after": after},
        )
        await self.session.flush()
        return after

    async def append_project_note(
        self,
        actor: EmployeeContext,
        project_id: int,
        note: str,
        *,
        trace_id: str | None = None,
    ) -> int:
        self.guard.require(actor, "memory.note.append")
        row = EntityNote(entity_type="project", entity_id=project_id, author_id=actor.id, note=note)
        self.session.add(row)
        await self.session.flush()
        await self.audit.record(
            action="memory.project.note.append",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type="project",
            entity_id=project_id,
            tool_name="append_project_note",
            diff_summary={"note_id": row.id},
        )
        return row.id

    async def append_contract_note(
        self,
        actor: EmployeeContext,
        contract_id: int,
        note: str,
        *,
        trace_id: str | None = None,
    ) -> int:
        self.guard.require(actor, "memory.note.append")
        row = EntityNote(
            entity_type="contract",
            entity_id=contract_id,
            author_id=actor.id,
            note=note,
        )
        self.session.add(row)
        await self.session.flush()
        await self.audit.record(
            action="memory.contract.note.append",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type="contract",
            entity_id=contract_id,
            tool_name="append_contract_note",
            diff_summary={"note_id": row.id},
        )
        return row.id

    async def get_contract_memory(
        self, actor: EmployeeContext, contract_id: int
    ) -> dict[str, str | None]:
        self.guard.require(actor, "contract.read")
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            return {}
        return self._contract_memory(contract)

    async def update_contract_memory(
        self,
        actor: EmployeeContext,
        contract_id: int,
        patch: MemoryPatch,
        *,
        trace_id: str | None = None,
    ) -> dict[str, str | None]:
        self.guard.require(actor, "memory.update")
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            return {}
        before = self._contract_memory(contract)
        if patch.summary is not None:
            contract.summary = patch.summary
        if patch.notes is not None:
            contract.notes = patch.notes
        if patch.current_risks is not None:
            contract.current_risks = patch.current_risks
        if patch.important_facts is not None:
            contract.important_facts = patch.important_facts
        after = self._contract_memory(contract)
        await self.audit.record(
            action="memory.contract.update",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type="contract",
            entity_id=contract_id,
            tool_name="update_contract_memory",
            diff_summary={"before": before, "after": after},
        )
        await self.session.flush()
        return after

    @staticmethod
    def _project_memory(project: Project) -> dict[str, str | None]:
        return {
            "summary": project.summary,
            "notes": project.notes,
            "current_issues": project.current_issues,
        }

    @staticmethod
    def _contract_memory(contract: Contract) -> dict[str, str | None]:
        return {
            "summary": contract.summary,
            "notes": contract.notes,
            "current_risks": contract.current_risks,
            "important_facts": contract.important_facts,
        }
