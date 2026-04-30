from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ConfirmationStatus
from app.infrastructure.db.models import PendingConfirmation


class ConfirmationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        employee_id: int,
        tool_name: str,
        payload: dict[str, Any],
        ttl_minutes: int = 15,
    ) -> PendingConfirmation:
        row = PendingConfirmation(
            employee_id=employee_id,
            tool_name=tool_name,
            payload=payload,
            payload_hash=self.hash_payload(payload),
            status=ConfirmationStatus.pending.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    @staticmethod
    def hash_payload(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
