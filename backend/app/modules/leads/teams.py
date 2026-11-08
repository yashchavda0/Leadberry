from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from ...core.database import tenant_transaction
from ..identity.dependencies import User
from ..identity.service import AccessError, Principal, audit, authorize_mutation
from .queries import access
from .schemas import TeamInput

router = APIRouter(prefix="/api/v1", tags=["Teams"])


@router.get("/teams")
async def teams(request: Request, user: User, limit: int = Query(100, ge=1, le=100), after: UUID | None = None):
    async with access(request, user, "leads.view") as (connection, current):
        rows = (await connection.execute(text(
            "SELECT t.id,t.name,t.is_active,COALESCE(array_agg(tm.membership_id) "
            "FILTER(WHERE tm.membership_id IS NOT NULL),ARRAY[]::uuid[]) AS membership_ids "
            "FROM crm.teams t LEFT JOIN crm.team_memberships tm ON tm.org_id=t.org_id AND tm.team_id=t.id "
            "WHERE t.org_id=:org AND (CAST(:after AS uuid) IS NULL OR t.id>:after) "
            "AND (:all_scope OR EXISTS(SELECT 1 FROM crm.team_memberships x WHERE x.org_id=t.org_id AND x.team_id=t.id AND x.membership_id=:member)) "
            "GROUP BY t.org_id,t.id ORDER BY t.id LIMIT :limit"
        ), {"org": current.org_id, "member": current.member_id, "all_scope": current.data_scope == "all", "after": after, "limit": limit + 1})).mappings().all()
        return {"data": [{**dict(row), "membership_ids": list(row["membership_ids"]) if current.is_owner else []} for row in rows[:limit]],
                "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}


@router.post("/teams", status_code=201)
async def create_team(body: TeamInput, request: Request, user: User):
    return await save_team(body, request, user, None)


@router.put("/teams/{team_id}")
async def replace_team(team_id: UUID, body: TeamInput, request: Request, user: User):
    return await save_team(body, request, user, team_id)


async def save_team(body: TeamInput, request: Request, user: Principal, team_id: UUID | None):
    async with tenant_transaction(request.app.state.database_engine, user.org_id) as connection:
        current = await authorize_mutation(connection, user, "users.manage")
        if not current.is_owner:
            raise AccessError(403, "owner_required")
        for member in set(body.membership_ids):
            if not await connection.scalar(text("SELECT 1 FROM crm.organization_memberships WHERE org_id=:org AND id=:id AND status='active'"),
                                           {"org": user.org_id, "id": member}):
                raise AccessError(422, "invalid_team_member")
        values = {"org": user.org_id, "id": team_id, "name": body.name, "active": body.is_active}
        if team_id is None:
            team_id = await connection.scalar(text("INSERT INTO crm.teams(org_id,name,is_active) VALUES(:org,:name,:active) RETURNING id"), values)
        elif not await connection.scalar(text("UPDATE crm.teams SET name=:name,is_active=:active WHERE org_id=:org AND id=:id RETURNING id"), values):
            raise AccessError(404, "team_not_found")
        await connection.execute(text("DELETE FROM crm.team_memberships WHERE org_id=:org AND team_id=:id"), {"org": user.org_id, "id": team_id})
        for member in set(body.membership_ids):
            await connection.execute(text("INSERT INTO crm.team_memberships(org_id,team_id,membership_id) VALUES(:org,:team,:member)"),
                                     {"org": user.org_id, "team": team_id, "member": member})
        await audit(connection, user.org_id, user.member_id, "team.updated", team_id)
        return {"id": team_id}
