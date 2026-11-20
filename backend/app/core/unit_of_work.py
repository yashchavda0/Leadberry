from __future__ import annotations

from types import TracebackType
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .database import tenant_transaction


class UnitOfWork:
    """Request- or job-scoped transactional boundary for one organization."""

    def __init__(
        self,
        engine: AsyncEngine,
        org_id: UUID,
        membership_id: UUID | None = None,
    ) -> None:
        self.engine = engine
        self.org_id = org_id
        self.membership_id = membership_id
        self._transaction = tenant_transaction(engine, org_id, membership_id)
        self._connection: AsyncConnection | None = None

    @property
    def connection(self) -> AsyncConnection:
        if self._connection is None:
            raise RuntimeError("UnitOfWork has not been entered")
        return self._connection

    async def __aenter__(self) -> "UnitOfWork":
        self._connection = await self._transaction.__aenter__()
        return self

    async def commit(self) -> None:
        await self.connection.commit()

    async def rollback(self) -> None:
        await self.connection.rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            return await self._transaction.__aexit__(exc_type, exc_value, traceback)
        finally:
            self._connection = None
