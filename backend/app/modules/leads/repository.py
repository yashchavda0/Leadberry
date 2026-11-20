from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..identity.service import Principal
from .queries import JOINS, fields, lead_payload, visibility


class LeadRepository:
    """Tenant-scoped lead persistence without transaction ownership."""

    def __init__(self, connection: AsyncConnection, principal: Principal) -> None:
        self.connection = connection
        self.principal = principal
        self.org_id = principal.org_id

    @property
    def parameters(self) -> dict[str, Any]:
        return {"org": self.org_id, "member": self.principal.member_id}

    async def get_by_id(self, lead_id: UUID):
        row = (
            (
                await self.connection.execute(
                    text(
                        f"SELECT {fields(self.principal)} {JOINS} "
                        "WHERE l.org_id=:org AND l.id=:id "
                        f"AND {visibility(self.principal)}"
                    ),
                    {**self.parameters, "id": lead_id},
                )
            )
            .mappings()
            .first()
        )
        return lead_payload(row) if row is not None else None

    async def count(self, conditions: list[str], parameters: dict[str, Any]) -> int:
        return int(
            await self.connection.scalar(
                text(f"SELECT count(*) {JOINS} WHERE {' AND '.join(conditions)}"),
                parameters,
            )
            or 0
        )

    async def list_page(
        self,
        conditions: list[str],
        parameters: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = (
            (
                await self.connection.execute(
                    text(
                        f"SELECT {fields(self.principal)} {JOINS} "
                        f"WHERE {' AND '.join(conditions)} "
                        "ORDER BY l.received_at DESC,l.id DESC LIMIT :limit"
                    ),
                    {**parameters, "limit": limit + 1},
                )
            )
            .mappings()
            .all()
        )
        return [lead_payload(row) for row in rows]
