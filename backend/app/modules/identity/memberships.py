from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.engine import make_url

from ...core.database import tenant_transaction
from .access import invite_member, recover_invitation, update_membership
from .dependencies import User, identity
from .schemas import InviteInput, MembershipUpdate
from .service import AccessError

router = APIRouter(tags=["Members and invitations"])


@router.get("/memberships")
async def memberships(
    request: Request,
    user: User,
    limit: int = Query(50, ge=1, le=100),
    after: UUID | None = None,
):
    if "users.view" not in user.permissions:
        raise AccessError(403, "permission_denied")
    async with tenant_transaction(identity(request).engine, user.org_id) as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT m.id,m.display_name,u.email,m.status,m.is_owner,m.visibility_override,m.landing_page,"
                        "COALESCE((SELECT jsonb_object_agg(x.permission_code,x.allowed) "
                        "FROM crm.membership_permission_overrides x WHERE x.org_id=m.org_id AND x.membership_id=m.id),'{}'::jsonb) AS permission_overrides,"
                        "COALESCE(array_agg(r.role_id ORDER BY r.role_id) FILTER(WHERE r.role_id IS NOT NULL),"
                        "ARRAY[]::uuid[]) AS role_ids "
                        "FROM crm.organization_memberships m JOIN crm.app_users u ON u.id=m.user_id LEFT JOIN crm.membership_roles r "
                        "ON r.org_id=m.org_id AND r.membership_id=m.id "
                        "WHERE m.org_id=:org AND (CAST(:after AS uuid) IS NULL OR m.id>:after) "
                        "GROUP BY m.org_id,m.id,u.email ORDER BY m.id LIMIT :limit"
                    ),
                    {"org": user.org_id, "after": after, "limit": limit + 1},
                )
            )
            .mappings()
            .all()
        )
        total = (
            await connection.scalar(
                text(
                    "SELECT count(*) FROM crm.organization_memberships WHERE org_id=:org"
                ),
                {"org": user.org_id},
            )
            if after is None
            else None
        )
        return {
            "data": [dict(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
            "total": total,
        }


@router.put("/memberships/{membership_id}")
async def replace_membership(
    membership_id: UUID, body: MembershipUpdate, request: Request, user: User
):
    await update_membership(
        request.app.state.database_engine, user, membership_id, body
    )
    return {"id": membership_id, "status": "updated"}


def invitation_key(request: Request) -> bytes:
    settings = request.app.state.configuration
    if settings.invitation_token_key is not None:
        return settings.invitation_token_key.get_secret_value().encode("utf-8")
    database = settings.auth_database_url or settings.database_url
    password = make_url(database.get_secret_value()).password if database else None
    if not password:
        raise AccessError(503, "invitation_key_not_configured")
    return password.encode("utf-8")


@router.post("/invitations", status_code=201)
async def invite(body: InviteInput, request: Request, response: Response, user: User):
    response.headers["Cache-Control"] = "no-store"
    return await invite_member(identity(request), user, body, invitation_key(request))


@router.get("/memberships/{membership_id}/invitation")
async def read_invitation(
    membership_id: UUID, request: Request, response: Response, user: User
):
    if not user.is_owner:
        raise AccessError(403, "permission_denied")
    response.headers["Cache-Control"] = "no-store"
    return await recover_invitation(
        identity(request), user, membership_id, invitation_key(request)
    )


@router.delete("/memberships/{membership_id}")
async def deactivate_membership(membership_id: UUID, request: Request, user: User):
    await update_membership(
        request.app.state.database_engine,
        user,
        membership_id,
        MembershipUpdate(status="disabled"),
        deactivate_only=True,
    )
    return {"id": membership_id, "status": "disabled"}
