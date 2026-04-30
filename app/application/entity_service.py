from __future__ import annotations

from typing import TypeVar

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.permissions import PermissionGuard
from app.application.schemas import (
    ContractRead,
    CounterpartyRead,
    EmployeeContext,
    ItemRead,
    ProjectRead,
)
from app.infrastructure.db.models import Contract, Counterparty, Item, Project

T = TypeVar("T")


class EntityService:
    """Read/search service for CRM entities.

    ACL is intentionally centralized here instead of Telegram handlers or agent nodes. The MVP uses
    RBAC permissions first; explicit project/contract ACL filtering can be tightened behind these
    methods without changing tools.
    """

    def __init__(self, session: AsyncSession, guard: PermissionGuard | None = None) -> None:
        self.session = session
        self.guard = guard or PermissionGuard()

    async def search_counterparties(
        self, actor: EmployeeContext, query: str, *, limit: int = 10
    ) -> list[CounterpartyRead]:
        self.guard.require(actor, "counterparty.read")
        stmt = (
            select(Counterparty)
            .where(Counterparty.name.ilike(self._contains(query)))
            .order_by(Counterparty.name)
            .limit(limit)
        )
        return [CounterpartyRead.model_validate(row) for row in await self._scalars(stmt)]

    async def get_counterparty(
        self, actor: EmployeeContext, counterparty_id: int
    ) -> CounterpartyRead | None:
        self.guard.require(actor, "counterparty.read")
        row = await self.session.get(Counterparty, counterparty_id)
        return CounterpartyRead.model_validate(row) if row else None

    async def search_projects(
        self, actor: EmployeeContext, query: str, *, limit: int = 10
    ) -> list[ProjectRead]:
        self.guard.require(actor, "project.read")
        stmt = (
            select(Project)
            .where(Project.title.ilike(self._contains(query)))
            .order_by(Project.title)
            .limit(limit)
        )
        return [ProjectRead.model_validate(row) for row in await self._scalars(stmt)]

    async def get_project(self, actor: EmployeeContext, project_id: int) -> ProjectRead | None:
        self.guard.require(actor, "project.read")
        row = await self.session.get(Project, project_id)
        return ProjectRead.model_validate(row) if row else None

    async def search_contracts(
        self, actor: EmployeeContext, query: str, *, limit: int = 10
    ) -> list[ContractRead]:
        self.guard.require(actor, "contract.read")
        pattern = self._contains(query)
        stmt = (
            select(Contract)
            .where(or_(Contract.title.ilike(pattern), Contract.number.ilike(pattern)))
            .order_by(Contract.title)
            .limit(limit)
        )
        return [ContractRead.model_validate(row) for row in await self._scalars(stmt)]

    async def get_contract(self, actor: EmployeeContext, contract_id: int) -> ContractRead | None:
        self.guard.require(actor, "contract.read")
        row = await self.session.get(Contract, contract_id)
        return ContractRead.model_validate(row) if row else None

    async def search_items(
        self, actor: EmployeeContext, query: str, *, limit: int = 10
    ) -> list[ItemRead]:
        self.guard.require(actor, "item.read")
        stmt = (
            select(Item)
            .where(Item.name.ilike(self._contains(query)))
            .order_by(Item.name)
            .limit(limit)
        )
        return [ItemRead.model_validate(row) for row in await self._scalars(stmt)]

    async def get_item(self, actor: EmployeeContext, item_id: int) -> ItemRead | None:
        self.guard.require(actor, "item.read")
        row = await self.session.get(Item, item_id)
        return ItemRead.model_validate(row) if row else None

    @staticmethod
    def _contains(query: str) -> str:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    async def _scalars(self, stmt: Select[tuple[T]]) -> list[T]:
        rows = await self.session.scalars(stmt)
        return list(rows)
