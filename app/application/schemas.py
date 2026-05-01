from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import EntityType, TaskPriority, TaskStatus


class EmployeeContext(BaseModel):
    id: int
    full_name: str
    telegram_user_id: int | None
    role: str | None = None
    department: str | None = None
    permissions: set[str] = Field(default_factory=set)
    timezone: str = "Europe/Moscow"


class TaskCreate(BaseModel):
    creator_id: int
    assignee_id: int
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    related_entity_type: EntityType | None = None
    related_entity_id: int | None = None
    priority: TaskPriority = TaskPriority.normal
    due_at: datetime | None = None
    planned_at: datetime | None = None
    reminder_at: datetime | None = None
    created_from: str = "api"
    original_text: str | None = None
    parsed_metadata: dict[str, Any] = Field(default_factory=dict)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    assignee_id: int
    related_entity_type: str | None
    related_entity_id: int | None
    title: str
    description: str | None
    status: str
    priority: str
    due_at: datetime | None
    planned_at: datetime | None
    reminder_at: datetime | None
    created_from: str
    original_text: str | None
    parsed_metadata: dict[str, Any]


class CounterpartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    contacts: dict[str, Any]
    legal_details: dict[str, Any]
    notes: str | None
    metadata_: dict[str, Any]


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    primary_counterparty_id: int | None
    title: str
    status: str
    responsible_id: int | None
    summary: str | None
    notes: str | None
    current_issues: str | None
    metadata_: dict[str, Any]


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    counterparty_id: int | None
    number: str | None
    title: str
    status: str
    responsible_id: int | None
    summary: str | None
    notes: str | None
    current_risks: str | None
    important_facts: str | None
    metadata_: dict[str, Any]


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int | None
    name: str
    type: str
    status: str
    parameters: dict[str, Any]
    notes: str | None
    metadata_: dict[str, Any]


class FileObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    file_type: str
    display_name: str
    current_version_id: int | None
    metadata_: dict[str, Any]


class FileVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_object_id: int
    version_number: int
    minio_bucket: str
    object_key: str
    checksum: str
    size_bytes: int
    mime_type: str
    is_archived: bool
    uploaded_by: int


class FileVersionCreate(BaseModel):
    entity_type: EntityType
    entity_id: int
    file_type: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=300)
    minio_bucket: str
    object_key: str
    checksum: str
    size_bytes: int = Field(ge=0)
    mime_type: str
    uploaded_by: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskStatusUpdate(BaseModel):
    task_id: int
    actor_id: int
    status: TaskStatus


class ReminderCreate(BaseModel):
    task_id: int | None = None
    recipient_id: int
    remind_at: datetime
    message: str
    delivery_channel: str = "telegram"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryPatch(BaseModel):
    summary: str | None = None
    notes: str | None = None
    current_issues: str | None = None
    current_risks: str | None = None
    important_facts: str | None = None


class ToolResult(BaseModel):
    ok: bool
    code: str = "ok"
    data: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
