from __future__ import annotations

from enum import StrEnum


class AccessLevel(StrEnum):
    public = "public"
    department = "department"
    restricted = "restricted"
    confidential = "confidential"


class EntityType(StrEnum):
    counterparty = "counterparty"
    project = "project"
    contract = "contract"
    item = "item"
    document = "document"
    file = "file"
    task = "task"


class TaskStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    waiting = "waiting"
    done = "done"
    cancelled = "cancelled"
    archived = "archived"


class TaskPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class ReminderStatus(StrEnum):
    scheduled = "scheduled"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class DangerLevel(StrEnum):
    safe = "safe"
    sensitive = "sensitive"
    dangerous = "dangerous"


class ConfirmationStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    expired = "expired"
    executed = "executed"


class ToolCallStatus(StrEnum):
    planned = "planned"
    succeeded = "succeeded"
    failed = "failed"
    forbidden = "forbidden"
    needs_confirmation = "needs_confirmation"
