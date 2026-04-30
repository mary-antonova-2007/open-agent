from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonDict = dict[str, Any]


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[list[Role]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(240), nullable=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role: Mapped[Role | None] = relationship()
    department: Mapped[Department | None] = relationship()


class Counterparty(Base, TimestampMixin):
    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(80), default="client", nullable=False)
    contacts: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)
    legal_details: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    primary_counterparty_id: Mapped[int | None] = mapped_column(ForeignKey("counterparties.id"))
    title: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    current_issues: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class ProjectCounterparty(Base):
    __tablename__ = "project_counterparties"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    counterparty_id: Mapped[int] = mapped_column(
        ForeignKey("counterparties.id", ondelete="CASCADE"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(80), default="related", nullable=False)


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    counterparty_id: Mapped[int | None] = mapped_column(ForeignKey("counterparties.id"))
    number: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    current_risks: Mapped[str | None] = mapped_column(Text)
    important_facts: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))
    name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(80), default="product", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    parameters: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class EmployeeProjectAccess(Base):
    __tablename__ = "employee_project_access"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    access_level: Mapped[str] = mapped_column(String(50), default="read", nullable=False)


class EmployeeContractAccess(Base):
    __tablename__ = "employee_contract_access"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    )
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), primary_key=True
    )
    access_level: Mapped[str] = mapped_column(String(50), default="read", nullable=False)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_assignee_status_due", "assignee_id", "status", "due_at"),
        Index("ix_tasks_related_entity", "related_entity_type", "related_entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(50))
    related_entity_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    priority: Mapped[str] = mapped_column(String(50), default="normal", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_from: Mapped[str] = mapped_column(String(80), default="api", nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text)
    parsed_metadata: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"
    __table_args__ = (Index("ix_reminders_status_remind_at", "status", "remind_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_channel: Mapped[str] = mapped_column(String(50), default="telegram", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="scheduled", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class EntityNote(Base, TimestampMixin):
    __tablename__ = "entity_notes"
    __table_args__ = (Index("ix_entity_notes_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(50), default="default", nullable=False)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class FileObject(Base, TimestampMixin):
    __tablename__ = "file_objects"
    __table_args__ = (Index("ix_file_objects_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class FileVersion(Base, TimestampMixin):
    __tablename__ = "file_versions"
    __table_args__ = (UniqueConstraint("file_object_id", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_object_id: Mapped[int] = mapped_column(ForeignKey("file_objects.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    minio_bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_acl", "department_id", "access_level", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    access_level: Mapped[str] = mapped_column(String(50), default="department", nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_version_id: Mapped[int | None] = mapped_column(ForeignKey("file_versions.id"))
    checksum: Mapped[str | None] = mapped_column(String(128))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    change_summary: Mapped[str | None] = mapped_column(Text)


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    qdrant_point_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[JsonDict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    state: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    message_text: Mapped[str | None] = mapped_column(Text)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_sessions.id"))
    status: Mapped[str] = mapped_column(String(50), default="started", nullable=False)
    route: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PendingConfirmation(Base, TimestampMixin):
    __tablename__ = "pending_confirmations"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[JsonDict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ToolCall(Base, TimestampMixin):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    input_summary: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)
    output_summary: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmation_id: Mapped[int | None] = mapped_column(ForeignKey("pending_confirmations.id"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_trace_id", "trace_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    actor_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    tool_name: Mapped[str | None] = mapped_column(String(160))
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    diff_summary: Mapped[JsonDict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
