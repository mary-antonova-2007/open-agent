from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_service import AuditService
from app.application.permissions import PermissionGuard
from app.application.schemas import (
    EmployeeContext,
    FileObjectRead,
    FileVersionCreate,
    FileVersionRead,
)
from app.infrastructure.db.models import FileObject, FileVersion


class FileService:
    def __init__(self, session: AsyncSession, guard: PermissionGuard | None = None) -> None:
        self.session = session
        self.guard = guard or PermissionGuard()
        self.audit = AuditService(session)

    async def add_file_version(
        self,
        actor: EmployeeContext,
        payload: FileVersionCreate,
        *,
        trace_id: str | None = None,
        replace_current: bool = False,
    ) -> FileVersionRead:
        self.guard.require(actor, "file.write")
        file_object = await self._find_file_object(
            payload.entity_type.value,
            payload.entity_id,
            payload.file_type,
            payload.display_name,
        )
        if file_object is None:
            file_object = FileObject(
                entity_type=payload.entity_type.value,
                entity_id=payload.entity_id,
                file_type=payload.file_type,
                display_name=payload.display_name,
                metadata_=payload.metadata,
            )
            self.session.add(file_object)
            await self.session.flush()
        if file_object.current_version_id and replace_current:
            current = await self.session.get(FileVersion, file_object.current_version_id)
            if current is not None:
                current.is_archived = True
        version_number = await self._next_version_number(file_object.id)
        version = FileVersion(
            file_object_id=file_object.id,
            version_number=version_number,
            minio_bucket=payload.minio_bucket,
            object_key=payload.object_key,
            checksum=payload.checksum,
            size_bytes=payload.size_bytes,
            mime_type=payload.mime_type,
            is_archived=False,
            uploaded_by=payload.uploaded_by,
        )
        self.session.add(version)
        await self.session.flush()
        file_object.current_version_id = version.id
        await self.audit.record(
            action="file.version.add",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type=payload.entity_type.value,
            entity_id=payload.entity_id,
            tool_name="add_file_to_entity",
            diff_summary={
                "file_object_id": file_object.id,
                "file_version_id": version.id,
                "replace_current": replace_current,
            },
        )
        await self.session.flush()
        return FileVersionRead.model_validate(version)

    async def get_latest_file(
        self, actor: EmployeeContext, entity_type: str, entity_id: int, file_type: str
    ) -> FileVersionRead | None:
        self.guard.require(actor, "file.read")
        stmt = (
            select(FileVersion)
            .join(FileObject, FileObject.id == FileVersion.file_object_id)
            .where(
                FileObject.entity_type == entity_type,
                FileObject.entity_id == entity_id,
                FileObject.file_type == file_type,
                FileObject.current_version_id == FileVersion.id,
                FileVersion.is_archived.is_(False),
            )
        )
        row = await self.session.scalar(stmt)
        return FileVersionRead.model_validate(row) if row else None

    async def list_entity_files(
        self, actor: EmployeeContext, entity_type: str, entity_id: int
    ) -> list[FileObjectRead]:
        self.guard.require(actor, "file.read")
        stmt = (
            select(FileObject)
            .where(FileObject.entity_type == entity_type, FileObject.entity_id == entity_id)
            .order_by(FileObject.file_type, FileObject.display_name)
        )
        rows = await self._scalars(stmt)
        return [FileObjectRead.model_validate(row) for row in rows]

    async def archive_file_version(
        self, actor: EmployeeContext, file_version_id: int, *, trace_id: str | None = None
    ) -> bool:
        self.guard.require(actor, "file.archive")
        version = await self.session.get(FileVersion, file_version_id)
        if version is None:
            return False
        version.is_archived = True
        await self.audit.record(
            action="file.version.archive",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type="file",
            entity_id=file_version_id,
            tool_name="archive_file_version",
            diff_summary={"is_archived": True},
        )
        await self.session.flush()
        return True

    async def _find_file_object(
        self, entity_type: str, entity_id: int, file_type: str, display_name: str
    ) -> FileObject | None:
        stmt = select(FileObject).where(
            FileObject.entity_type == entity_type,
            FileObject.entity_id == entity_id,
            FileObject.file_type == file_type,
            FileObject.display_name == display_name,
        )
        return await self.session.scalar(stmt)

    async def _next_version_number(self, file_object_id: int) -> int:
        stmt = (
            select(FileVersion.version_number)
            .where(FileVersion.file_object_id == file_object_id)
            .order_by(FileVersion.version_number.desc())
            .limit(1)
        )
        current = await self.session.scalar(stmt)
        return int(current or 0) + 1

    async def _scalars(self, stmt: Select[tuple[FileObject]]) -> list[FileObject]:
        rows = await self.session.scalars(stmt)
        return list(rows)
