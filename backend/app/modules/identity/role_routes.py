from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from ...core.database import tenant_transaction
from .access import save_role
from .dependencies import User
from .schemas import RoleInput
from .service import AccessError

router = APIRouter(tags=["Roles and permissions"])


@router.get("/permissions")
async def permissions(request: Request, user: User):
    if not ({"roles.view", "roles.manage", "users.manage"} & user.permissions):
        raise AccessError(403, "permission_denied")
    async with tenant_transaction(request.app.state.database_engine, user.org_id) as connection:
        return {"data": [dict(row) for row in (await connection.execute(
            text("SELECT code,module,page,action,is_delegable FROM crm.permissions ORDER BY module,code")
        )).mappings()]}


@router.get("/roles")
async def roles(request: Request, user: User, limit: int = Query(50, ge=1, le=100), after: UUID | None = None):
    if not ({"roles.view", "users.manage"} & user.permissions):
        raise AccessError(403, "permission_denied")
    async with tenant_transaction(request.app.state.database_engine, user.org_id) as connection:
        rows = (await connection.execute(
            text("WITH RECURSIVE hierarchy AS ("
                 "SELECT id,reports_to_role_id,1 AS level FROM crm.roles WHERE org_id=:org AND reports_to_role_id IS NULL "
                 "UNION ALL SELECT r.id,r.reports_to_role_id,h.level+1 FROM crm.roles r "
                 "JOIN hierarchy h ON r.reports_to_role_id=h.id WHERE r.org_id=:org) "
                 "SELECT r.id,r.name,r.description,r.data_scope,r.is_active,r.reports_to_role_id,h.level,"
                 "CASE WHEN r.reports_to_role_id IS NULL THEN 'Parent' ELSE 'Child' END AS role_type,"
                 "(SELECT name FROM crm.roles WHERE org_id=r.org_id AND id=r.reports_to_role_id) AS reports_to_name,"
                 "COALESCE(array_agg(p.permission_code ORDER BY p.permission_code) "
                 "FILTER(WHERE p.permission_code IS NOT NULL),ARRAY[]::text[]) AS permissions "
                 "FROM crm.roles r JOIN hierarchy h ON h.id=r.id LEFT JOIN crm.role_permissions p ON p.org_id=r.org_id AND p.role_id=r.id "
                 "WHERE r.org_id=:org AND (CAST(:after AS uuid) IS NULL OR r.id>:after) "
                 "GROUP BY r.org_id,r.id,h.level ORDER BY r.id LIMIT :limit"),
            {"org": user.org_id, "after": after, "limit": limit + 1},
        )).mappings().all()
        return {"data": [dict(row) for row in rows[:limit]], "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}


@router.post("/roles", status_code=201)
async def create_role(body: RoleInput, request: Request, user: User):
    return {"id": await save_role(request.app.state.database_engine, user, body, None)}


@router.put("/roles/{role_id}")
async def replace_role(role_id: UUID, body: RoleInput, request: Request, user: User):
    return {"id": await save_role(request.app.state.database_engine, user, body, role_id)}
