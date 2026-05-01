from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
from app.core.config import get_settings
from app.domain.enums import EntityType
from app.infrastructure.db.models import FileObject, FileVersion

SINGLETON_FILE_TYPES = {"kdz", "kdp"}
FILE_TYPE_DIRS = {
    "measurement": "Замеры",
    "kdz": "КДЗ",
    "kdp": "КДП",
    "info": "Info",
    "model": "Models",
    "contract": "Info",
}


@dataclass(frozen=True)
class StoredInboxFile:
    file_object_id: int
    file_version_id: int
    display_name: str
    object_key: str


class FileService:
    def __init__(self, session: AsyncSession, guard: PermissionGuard | None = None) -> None:
        self.session = session
        self.guard = guard or PermissionGuard()
        self.audit = AuditService(session)
        self.storage_root = Path(get_settings().local_file_storage_root)

    async def save_inbox_file(
        self,
        actor: EmployeeContext,
        *,
        source_path: Path,
        original_filename: str,
        mime_type: str | None = None,
        trace_id: str | None = None,
    ) -> StoredInboxFile:
        self.guard.require(actor, "file.write")
        safe_name = self._safe_filename(original_filename)
        destination_dir = self.storage_root / "users" / str(actor.id) / "Inbox"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = self._unique_path(destination_dir / safe_name)
        shutil.copyfile(source_path, destination)
        checksum = self._sha256(destination)
        size_bytes = destination.stat().st_size
        detected_mime = mime_type or mimetypes.guess_type(destination.name)[0] or "application/octet-stream"
        object_key = self._relative_key(destination)
        file_object = FileObject(
            entity_type=EntityType.personal.value,
            entity_id=actor.id,
            file_type="inbox",
            display_name=destination.name,
            metadata_={"original_filename": original_filename},
        )
        self.session.add(file_object)
        await self.session.flush()
        version = FileVersion(
            file_object_id=file_object.id,
            version_number=1,
            minio_bucket="local",
            object_key=object_key,
            checksum=checksum,
            size_bytes=size_bytes,
            mime_type=detected_mime,
            is_archived=False,
            uploaded_by=actor.id,
        )
        self.session.add(version)
        await self.session.flush()
        file_object.current_version_id = version.id
        await self.audit.record(
            action="file.inbox.save",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type=EntityType.personal.value,
            entity_id=actor.id,
            tool_name="save_inbox_file",
            diff_summary={
                "file_object_id": file_object.id,
                "file_version_id": version.id,
                "object_key": object_key,
            },
        )
        return StoredInboxFile(
            file_object_id=file_object.id,
            file_version_id=version.id,
            display_name=file_object.display_name,
            object_key=object_key,
        )

    async def move_inbox_file_to_entity(
        self,
        actor: EmployeeContext,
        *,
        file_object_id: int,
        entity_type: EntityType,
        entity_id: int,
        file_type: str,
        display_name: str,
        project_title: str | None = None,
        contract_title: str | None = None,
        item_title: str | None = None,
        trace_id: str | None = None,
    ) -> FileVersionRead | None:
        self.guard.require(actor, "file.write")
        inbox_object = await self.session.get(FileObject, file_object_id)
        if inbox_object is None or inbox_object.current_version_id is None:
            return None
        current = await self.session.get(FileVersion, inbox_object.current_version_id)
        if current is None:
            return None

        source = self.storage_root / current.object_key
        if not source.exists():
            return None

        folder = self._entity_folder(
            project_title=project_title,
            contract_title=contract_title,
            item_title=item_title,
            entity_type=entity_type,
            entity_id=entity_id,
            file_type=file_type,
        )
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / self._safe_filename(display_name)

        if file_type in SINGLETON_FILE_TYPES and destination.exists():
            archive_dir = folder / "Архив"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_name = f"{datetime.now(ZoneInfo(actor.timezone)).strftime('%Y%m%d_%H%M%S')}_{destination.name}"
            shutil.move(str(destination), str(archive_dir / archive_name))

        destination = self._unique_path(destination)
        shutil.move(str(source), str(destination))

        inbox_object.entity_type = entity_type.value
        inbox_object.entity_id = entity_id
        inbox_object.file_type = file_type
        inbox_object.display_name = destination.name
        inbox_object.metadata_ = {
            **(inbox_object.metadata_ or {}),
            "project_title": project_title,
            "contract_title": contract_title,
            "item_title": item_title,
        }
        current.object_key = self._relative_key(destination)
        current.checksum = self._sha256(destination)
        current.size_bytes = destination.stat().st_size
        current.mime_type = mimetypes.guess_type(destination.name)[0] or current.mime_type
        await self.audit.record(
            action="file.inbox.move",
            result="succeeded",
            actor_employee_id=actor.id,
            trace_id=trace_id,
            entity_type=entity_type.value,
            entity_id=entity_id,
            tool_name="move_inbox_file_to_entity",
            diff_summary={
                "file_object_id": inbox_object.id,
                "file_version_id": current.id,
                "object_key": current.object_key,
            },
        )
        await self.session.flush()
        return FileVersionRead.model_validate(current)

    def get_local_path(self, version: FileVersionRead) -> Path:
        return self.storage_root / version.object_key

    def list_storage_tree(self, *, max_entries: int = 200) -> list[str]:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        entries: list[str] = []
        for path in sorted(self.storage_root.rglob("*")):
            if len(entries) >= max_entries:
                break
            entries.append(str(path.relative_to(self.storage_root)))
        return entries

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

    def _entity_folder(
        self,
        *,
        project_title: str | None,
        contract_title: str | None,
        item_title: str | None,
        entity_type: EntityType,
        entity_id: int,
        file_type: str,
    ) -> Path:
        parts = [self.storage_root, "projects"]
        parts.append(self._safe_path_part(project_title or f"{entity_type.value}_{entity_id}"))
        if contract_title:
            parts.append(self._safe_path_part(contract_title))
        if item_title:
            parts.append(self._safe_path_part(item_title))
        parts.append(FILE_TYPE_DIRS.get(file_type, "Info"))
        return Path(*parts)

    def _relative_key(self, path: Path) -> str:
        return path.relative_to(self.storage_root).as_posix()

    @staticmethod
    def _safe_path_part(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
        return re.sub(r"\s+", " ", cleaned).strip(" .")[:120] or "Без названия"

    @classmethod
    def _safe_filename(cls, value: str) -> str:
        name = cls._safe_path_part(value)
        return name[:180]

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 2
        while True:
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
