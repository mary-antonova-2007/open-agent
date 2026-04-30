from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_service import AuditService
from app.application.permissions import PermissionGuard
from app.application.schemas import EmployeeContext, ReminderCreate, TaskCreate, TaskRead
from app.domain.enums import TaskStatus
from app.infrastructure.db.models import Reminder, Task


class TaskService:
    def __init__(self, session: AsyncSession, guard: PermissionGuard | None = None) -> None:
        self.session = session
        self.guard = guard or PermissionGuard()
        self.audit = AuditService(session)

    async def create_task(
        self, actor: EmployeeContext, payload: TaskCreate, *, trace_id: str | None = None
    ) -> TaskRead:
        self.guard.require(actor, "task.create")
        task = Task(
            creator_id=payload.creator_id,
            assignee_id=payload.assignee_id,
            related_entity_type=payload.related_entity_type,
            related_entity_id=payload.related_entity_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority.value,
            due_at=payload.due_at,
            planned_at=payload.planned_at,
            reminder_at=payload.reminder_at,
            created_from=payload.created_from,
            original_text=payload.original_text,
            parsed_metadata=payload.parsed_metadata,
        )
        self.session.add(task)
        await self.session.flush()
        if payload.reminder_at is not None:
            self.session.add(
                Reminder(
                    task_id=task.id,
                    recipient_id=payload.assignee_id,
                    remind_at=payload.reminder_at,
                    message=payload.title,
                    delivery_channel="telegram",
                    status="scheduled",
                    metadata_={"source": "task.reminder_at"},
                )
            )
        await self.audit.record(
            action="task.create",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type="task",
            entity_id=task.id,
            tool_name="create_task",
            diff_summary={"title": task.title, "assignee_id": task.assignee_id},
        )
        await self.session.flush()
        return TaskRead.model_validate(task)

    async def list_my_tasks(self, actor: EmployeeContext) -> list[TaskRead]:
        self.guard.require(actor, "task.read")
        stmt = (
            select(Task)
            .where(
                Task.assignee_id == actor.id,
                Task.status.notin_(["done", "cancelled", "archived"]),
            )
            .order_by(Task.due_at.is_(None), Task.due_at, Task.created_at.desc())
        )
        tasks = await self.session.scalars(stmt)
        return [TaskRead.model_validate(task) for task in tasks]

    async def list_overdue_tasks(self, actor: EmployeeContext) -> list[TaskRead]:
        self.guard.require(actor, "task.read")
        stmt = select(Task).where(
            Task.assignee_id == actor.id,
            Task.status.notin_(["done", "cancelled", "archived"]),
            Task.due_at < datetime.now(UTC),
        )
        tasks = await self.session.scalars(stmt)
        return [TaskRead.model_validate(task) for task in tasks]

    async def complete_task(
        self, actor: EmployeeContext, task_id: int, *, trace_id: str | None = None
    ) -> TaskRead | None:
        task = await self.session.get(Task, task_id)
        if task is None:
            return None
        if task.assignee_id != actor.id:
            self.guard.require(actor, "task.update.any")
        else:
            self.guard.require(actor, "task.update.self")
        task.status = TaskStatus.done.value
        await self.audit.record(
            action="task.complete",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type="task",
            entity_id=task.id,
            tool_name="complete_task",
            diff_summary={"status": "done"},
        )
        await self.session.flush()
        return TaskRead.model_validate(task)


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def schedule(self, payload: ReminderCreate) -> Reminder:
        reminder = Reminder(
            task_id=payload.task_id,
            recipient_id=payload.recipient_id,
            remind_at=payload.remind_at,
            message=payload.message,
            delivery_channel=payload.delivery_channel,
            status="scheduled",
            metadata_=payload.metadata,
        )
        self.session.add(reminder)
        await self.session.flush()
        return reminder
