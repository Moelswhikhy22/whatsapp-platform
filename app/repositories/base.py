from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.tenants.context import TenantContext

ModelT = TypeVar("ModelT")


class TenantScopedRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant: TenantContext,
    ) -> None:
        self._session = session
        self._tenant = tenant

    @property
    def tenant(self) -> TenantContext:
        return self._tenant

    @property
    def tenant_id(self) -> UUID:
        return self._tenant.tenant_id

    def _scope(
        self,
        statement: Select[ModelT],
        tenant_id_column: InstrumentedAttribute[UUID],
    ) -> Select[ModelT]:
        return statement.where(tenant_id_column == self.tenant_id)
