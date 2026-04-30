from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.entity_service import EntityService
from app.application.file_service import FileService
from app.application.memory_service import EntityMemoryService
from app.application.nl_task_parser import NaturalLanguageTaskParser
from app.application.schemas import EmployeeContext, MemoryPatch, TaskCreate, ToolResult
from app.application.task_service import TaskService
from app.domain.enums import DangerLevel
from app.tools.registry import ToolDefinition, ToolRegistry
from app.tools.schemas import (
    AppendNoteInput,
    CompleteTaskInput,
    CreateTaskInput,
    EmptyInput,
    EntityIdInput,
    GetLatestFileInput,
    ListEntityFilesInput,
    MemoryPatchInput,
    NaturalLanguageTaskInput,
    SearchInput,
)


def build_tool_registry(session: AsyncSession) -> ToolRegistry:
    registry = ToolRegistry()
    task_service = TaskService(session)
    memory_service = EntityMemoryService(session)
    entity_service = EntityService(session)
    file_service = FileService(session)
    nl_task_parser = NaturalLanguageTaskParser()

    async def create_task(
        actor: EmployeeContext, payload: CreateTaskInput, trace_id: str | None
    ) -> ToolResult:
        task = await task_service.create_task(
            actor,
            TaskCreate(
                creator_id=actor.id,
                assignee_id=payload.assignee_id,
                title=payload.title,
                description=payload.description,
                related_entity_type=payload.related_entity_type,
                related_entity_id=payload.related_entity_id,
                priority=payload.priority,
                due_at=payload.due_at,
                planned_at=payload.planned_at,
                reminder_at=payload.reminder_at,
                created_from="agent",
                original_text=payload.original_text,
                parsed_metadata=payload.parsed_metadata,
            ),
            trace_id=trace_id,
        )
        return ToolResult(ok=True, data=task.model_dump(mode="json"))

    async def list_my_tasks(
        actor: EmployeeContext, _payload: EmptyInput, _trace_id: str | None
    ) -> ToolResult:
        tasks = await task_service.list_my_tasks(actor)
        return ToolResult(ok=True, data={"tasks": [task.model_dump(mode="json") for task in tasks]})

    async def create_tasks_from_natural_language(
        actor: EmployeeContext, payload: NaturalLanguageTaskInput, trace_id: str | None
    ) -> ToolResult:
        drafts = nl_task_parser.parse(payload.text, timezone=actor.timezone)
        if not drafts:
            return ToolResult(ok=False, code="validation_error", message="No task draft found")
        if any(draft.ambiguous for draft in drafts):
            return ToolResult(
                ok=False,
                code="ambiguous",
                data={"drafts": [draft.__dict__ for draft in drafts]},
                message="Need clarification for date or task details",
            )
        created = []
        for draft in drafts:
            task = await task_service.create_task(
                actor,
                TaskCreate(
                    creator_id=actor.id,
                    assignee_id=payload.assignee_id or actor.id,
                    title=draft.title,
                    description=draft.description,
                    related_entity_type=payload.related_entity_type,
                    related_entity_id=payload.related_entity_id,
                    due_at=draft.due_at,
                    planned_at=draft.planned_at,
                    reminder_at=draft.reminder_at,
                    created_from="agent:nl",
                    original_text=payload.text,
                    parsed_metadata=draft.metadata,
                ),
                trace_id=trace_id,
            )
            created.append(task.model_dump(mode="json"))
        return ToolResult(ok=True, data={"tasks": created})

    async def complete_task(
        actor: EmployeeContext, payload: CompleteTaskInput, trace_id: str | None
    ) -> ToolResult:
        task = await task_service.complete_task(actor, payload.task_id, trace_id=trace_id)
        if task is None:
            return ToolResult(ok=False, code="not_found", message="Task was not found")
        return ToolResult(ok=True, data=task.model_dump(mode="json"))

    async def get_project_memory(
        actor: EmployeeContext, payload: EntityIdInput, _trace_id: str | None
    ) -> ToolResult:
        data = await memory_service.get_project_memory(actor, payload.id)
        return ToolResult(ok=bool(data), code="ok" if data else "not_found", data=data)

    async def update_project_memory(
        actor: EmployeeContext, payload: MemoryPatchInput, trace_id: str | None
    ) -> ToolResult:
        data = await memory_service.update_project_memory(
            actor,
            payload.entity_id,
            MemoryPatch(
                summary=payload.summary,
                notes=payload.notes,
                current_issues=payload.current_issues,
            ),
            trace_id=trace_id,
        )
        return ToolResult(ok=bool(data), code="ok" if data else "not_found", data=data)

    async def append_project_note(
        actor: EmployeeContext, payload: AppendNoteInput, trace_id: str | None
    ) -> ToolResult:
        note_id = await memory_service.append_project_note(
            actor, payload.entity_id, payload.note, trace_id=trace_id
        )
        return ToolResult(ok=True, data={"note_id": note_id})

    async def search_counterparties(
        actor: EmployeeContext, payload: SearchInput, _trace_id: str | None
    ) -> ToolResult:
        rows = await entity_service.search_counterparties(actor, payload.query)
        return ToolResult(ok=True, data={"counterparties": [row.model_dump() for row in rows]})

    async def get_counterparty(
        actor: EmployeeContext, payload: EntityIdInput, _trace_id: str | None
    ) -> ToolResult:
        row = await entity_service.get_counterparty(actor, payload.id)
        return ToolResult(
            ok=row is not None,
            code="ok" if row else "not_found",
            data=row.model_dump() if row else {},
        )

    async def search_projects(
        actor: EmployeeContext, payload: SearchInput, _trace_id: str | None
    ) -> ToolResult:
        rows = await entity_service.search_projects(actor, payload.query)
        return ToolResult(ok=True, data={"projects": [row.model_dump() for row in rows]})

    async def get_project(
        actor: EmployeeContext, payload: EntityIdInput, _trace_id: str | None
    ) -> ToolResult:
        row = await entity_service.get_project(actor, payload.id)
        return ToolResult(
            ok=row is not None,
            code="ok" if row else "not_found",
            data=row.model_dump() if row else {},
        )

    async def search_contracts(
        actor: EmployeeContext, payload: SearchInput, _trace_id: str | None
    ) -> ToolResult:
        rows = await entity_service.search_contracts(actor, payload.query)
        return ToolResult(ok=True, data={"contracts": [row.model_dump() for row in rows]})

    async def get_contract(
        actor: EmployeeContext, payload: EntityIdInput, _trace_id: str | None
    ) -> ToolResult:
        row = await entity_service.get_contract(actor, payload.id)
        return ToolResult(
            ok=row is not None,
            code="ok" if row else "not_found",
            data=row.model_dump() if row else {},
        )

    async def search_items(
        actor: EmployeeContext, payload: SearchInput, _trace_id: str | None
    ) -> ToolResult:
        rows = await entity_service.search_items(actor, payload.query)
        return ToolResult(ok=True, data={"items": [row.model_dump() for row in rows]})

    async def get_item(
        actor: EmployeeContext, payload: EntityIdInput, _trace_id: str | None
    ) -> ToolResult:
        row = await entity_service.get_item(actor, payload.id)
        return ToolResult(
            ok=row is not None,
            code="ok" if row else "not_found",
            data=row.model_dump() if row else {},
        )

    async def get_latest_file(
        actor: EmployeeContext, payload: GetLatestFileInput, _trace_id: str | None
    ) -> ToolResult:
        row = await file_service.get_latest_file(
            actor,
            payload.entity_type.value,
            payload.entity_id,
            payload.file_type,
        )
        return ToolResult(
            ok=row is not None,
            code="ok" if row else "not_found",
            data=row.model_dump() if row else {},
        )

    async def list_entity_files(
        actor: EmployeeContext, payload: ListEntityFilesInput, _trace_id: str | None
    ) -> ToolResult:
        rows = await file_service.list_entity_files(
            actor,
            payload.entity_type.value,
            payload.entity_id,
        )
        return ToolResult(ok=True, data={"files": [row.model_dump() for row in rows]})

    async def archive_file_version(
        actor: EmployeeContext, payload: EntityIdInput, trace_id: str | None
    ) -> ToolResult:
        archived = await file_service.archive_file_version(actor, payload.id, trace_id=trace_id)
        return ToolResult(ok=archived, code="ok" if archived else "not_found")

    definitions = [
        ToolDefinition(
            "create_task",
            "Create a task with optional related entity and reminder.",
            CreateTaskInput,
            "task.create",
            DangerLevel.safe,
            create_task,
        ),
        ToolDefinition(
            "list_my_tasks",
            "List current employee open tasks.",
            EmptyInput,
            "task.read",
            DangerLevel.safe,
            list_my_tasks,
        ),
        ToolDefinition(
            "create_tasks_from_natural_language",
            "Create one or more task drafts from natural language and persist unambiguous tasks.",
            NaturalLanguageTaskInput,
            "task.create",
            DangerLevel.safe,
            create_tasks_from_natural_language,
        ),
        ToolDefinition(
            "complete_task",
            "Complete a task assigned to the current employee.",
            CompleteTaskInput,
            "task.update.self",
            DangerLevel.safe,
            complete_task,
        ),
        ToolDefinition(
            "get_project_memory",
            "Read structured project memory.",
            EntityIdInput,
            "project.read",
            DangerLevel.safe,
            get_project_memory,
        ),
        ToolDefinition(
            "update_project_memory",
            "Update structured project memory fields.",
            MemoryPatchInput,
            "memory.update",
            DangerLevel.dangerous,
            update_project_memory,
        ),
        ToolDefinition(
            "append_project_note",
            "Append an operational note to a project.",
            AppendNoteInput,
            "memory.note.append",
            DangerLevel.safe,
            append_project_note,
        ),
        ToolDefinition(
            "search_counterparties",
            "Search counterparties by name.",
            SearchInput,
            "counterparty.read",
            DangerLevel.safe,
            search_counterparties,
        ),
        ToolDefinition(
            "get_counterparty",
            "Get counterparty details.",
            EntityIdInput,
            "counterparty.read",
            DangerLevel.safe,
            get_counterparty,
        ),
        ToolDefinition(
            "search_projects",
            "Search projects by title.",
            SearchInput,
            "project.read",
            DangerLevel.safe,
            search_projects,
        ),
        ToolDefinition(
            "get_project",
            "Get project details.",
            EntityIdInput,
            "project.read",
            DangerLevel.safe,
            get_project,
        ),
        ToolDefinition(
            "search_contracts",
            "Search contracts by title or number.",
            SearchInput,
            "contract.read",
            DangerLevel.safe,
            search_contracts,
        ),
        ToolDefinition(
            "get_contract",
            "Get contract details.",
            EntityIdInput,
            "contract.read",
            DangerLevel.safe,
            get_contract,
        ),
        ToolDefinition(
            "search_items",
            "Search items/products by name.",
            SearchInput,
            "item.read",
            DangerLevel.safe,
            search_items,
        ),
        ToolDefinition(
            "get_item",
            "Get item/product details.",
            EntityIdInput,
            "item.read",
            DangerLevel.safe,
            get_item,
        ),
        ToolDefinition(
            "get_latest_file",
            "Get the current active file version for an entity and file type.",
            GetLatestFileInput,
            "file.read",
            DangerLevel.safe,
            get_latest_file,
        ),
        ToolDefinition(
            "list_entity_files",
            "List logical files attached to an entity.",
            ListEntityFilesInput,
            "file.read",
            DangerLevel.safe,
            list_entity_files,
        ),
        ToolDefinition(
            "archive_file_version",
            "Archive a file version.",
            EntityIdInput,
            "file.archive",
            DangerLevel.dangerous,
            archive_file_version,
        ),
    ]
    stub_definitions = [
        ("search_knowledge", SearchInput, "knowledge.search", DangerLevel.safe),
    ]
    for definition in definitions:
        registry.register(definition)
    for name, schema, permission, danger in stub_definitions:
        registry.register(
            ToolDefinition(
                name=name,
                description=f"Planned tool: {name}",
                input_schema=schema,
                required_permission=permission,
                danger_level=danger,
            )
        )
    return registry
