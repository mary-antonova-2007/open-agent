from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import EntityType, TaskPriority


class EmptyInput(BaseModel):
    pass


class SearchInput(BaseModel):
    query: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)


class EntityIdInput(BaseModel):
    id: int


class CreateTaskInput(BaseModel):
    assignee_id: int
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    related_entity_type: EntityType | None = None
    related_entity_id: int | None = None
    priority: TaskPriority = TaskPriority.normal
    due_at: datetime | None = None
    planned_at: datetime | None = None
    reminder_at: datetime | None = None
    original_text: str | None = None
    parsed_metadata: dict[str, Any] = Field(default_factory=dict)


class NaturalLanguageTaskInput(BaseModel):
    text: str = Field(min_length=1)
    assignee_id: int | None = None
    related_entity_type: EntityType | None = None
    related_entity_id: int | None = None


class CompleteTaskInput(BaseModel):
    task_id: int


class MemoryPatchInput(BaseModel):
    entity_id: int
    summary: str | None = None
    notes: str | None = None
    current_issues: str | None = None
    current_risks: str | None = None
    important_facts: str | None = None


class AppendNoteInput(BaseModel):
    entity_id: int
    note: str = Field(min_length=1)


class GetLatestFileInput(BaseModel):
    entity_type: EntityType
    entity_id: int
    file_type: str


class ListEntityFilesInput(BaseModel):
    entity_type: EntityType
    entity_id: int
