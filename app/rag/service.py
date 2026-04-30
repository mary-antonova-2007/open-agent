from __future__ import annotations

from dataclasses import dataclass

from app.application.schemas import EmployeeContext


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    score: float
    metadata: dict[str, object]


class RagService:
    async def search(
        self, *, query: str, employee: EmployeeContext, filters: dict[str, object] | None = None
    ) -> list[RetrievedChunk]:
        # Qdrant-backed ACL-aware retrieval is wired in Phase 5.
        _ = (query, employee, filters)
        return []
