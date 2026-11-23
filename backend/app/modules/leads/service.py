from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from ..identity.service import AccessError, Principal
from .repository import LeadRepository


class LeadQueryService:
    """Application boundary for tenant-scoped lead reads."""

    def __init__(self, connection: AsyncConnection, principal: Principal) -> None:
        self.repository = LeadRepository(connection, principal)

    async def get(self, lead_id: UUID) -> dict[str, Any]:
        lead = await self.repository.get_by_id(lead_id)
        if lead is None:
            raise AccessError(404, "lead_not_found")
        return lead

    async def list_page(
        self,
        conditions: list[str],
        parameters: dict[str, Any],
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> dict[str, Any]:
        total = (
            await self.repository.count(conditions, parameters)
            if cursor is None
            else None
        )
        page_conditions = list(conditions)
        page_parameters = dict(parameters)
        if cursor is not None:
            page_conditions.append("(l.received_at,l.id)<(:moment,:id)")
            page_parameters.update(moment=cursor[0], id=cursor[1])
        rows = await self.repository.list_page(page_conditions, page_parameters, limit)
        return {
            "data": rows[:limit],
            "next_cursor": rows[limit - 1] if len(rows) > limit else None,
            "total": total,
        }
