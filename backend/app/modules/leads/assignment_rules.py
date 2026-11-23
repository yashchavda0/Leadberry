from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.schemas import Input
from ..identity.service import AccessError, audit
from .queries import access

router = APIRouter(prefix="/api/v1/assignment-rules", tags=["Assignment rules"])
Source = Literal["website", "indiamart", "tradeindia"]


class AssignmentRuleInput(Input):
    team_id: UUID
    enabled: bool = True


def require_full_scope(current) -> None:
    if current.data_scope != "all":
        raise AccessError(403, "assignment_rules_require_full_scope")


@router.get("")
async def list_rules(request: Request, user: User):
    async with access(request, user, "assignment_rules.manage") as (
        connection,
        current,
    ):
        require_full_scope(current)
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT r.source,r.team_id,t.name AS team_name,t.is_active AS team_active,r.enabled,r.updated_at "
                        "FROM crm.source_assignment_rules r JOIN crm.teams t ON t.org_id=r.org_id AND t.id=r.team_id "
                        "WHERE r.org_id=:org ORDER BY r.source"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        return {"data": [dict(row) for row in rows]}


@router.get("/teams")
async def team_options(
    request: Request,
    user: User,
    limit: int = Query(25, ge=1, le=100),
    after: UUID | None = None,
    q: str = Query("", max_length=200),
):
    async with access(request, user, "assignment_rules.manage") as (
        connection,
        current,
    ):
        require_full_scope(current)
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT id,name,is_active FROM crm.teams WHERE org_id=:org AND is_active "
                        "AND (CAST(:after AS uuid) IS NULL OR id>:after) AND strpos(lower(name),lower(:q))>0 ORDER BY id LIMIT :limit"
                    ),
                    {
                        "org": current.org_id,
                        "after": after,
                        "q": q.strip(),
                        "limit": limit + 1,
                    },
                )
            )
            .mappings()
            .all()
        )
        return {
            "data": [dict(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }


@router.put("/{source}")
async def save_rule(
    source: Source, body: AssignmentRuleInput, request: Request, user: User
):
    async with access(request, user, "assignment_rules.manage") as (
        connection,
        current,
    ):
        require_full_scope(current)
        team = await connection.scalar(
            text(
                "SELECT id FROM crm.teams WHERE org_id=:org AND id=:team AND is_active"
            ),
            {"org": current.org_id, "team": body.team_id},
        )
        if not team:
            raise AccessError(422, "invalid_team")
        await connection.execute(
            text(
                "INSERT INTO crm.source_assignment_rules(org_id,source,team_id,enabled) VALUES(:org,:source,:team,:enabled) "
                "ON CONFLICT(org_id,source) DO UPDATE SET team_id=EXCLUDED.team_id,enabled=EXCLUDED.enabled,"
                "last_member_id=CASE WHEN crm.source_assignment_rules.team_id IS DISTINCT FROM EXCLUDED.team_id THEN NULL ELSE crm.source_assignment_rules.last_member_id END,updated_at=now()"
            ),
            {
                "org": current.org_id,
                "source": source,
                "team": body.team_id,
                "enabled": body.enabled,
            },
        )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "assignment_rule.updated",
            body.team_id,
        )
        return {"source": source, "team_id": body.team_id, "enabled": body.enabled}


async def next_assignment(connection, org_id: UUID, source: str, *, allocate: bool):
    lock = " FOR UPDATE OF r" if allocate else ""
    rule = (
        (
            await connection.execute(
                text(
                    "SELECT r.team_id,r.last_member_id,t.is_active FROM crm.source_assignment_rules r "
                    "JOIN crm.teams t ON t.org_id=r.org_id AND t.id=r.team_id "
                    "WHERE r.org_id=:org AND r.source=:source AND r.enabled" + lock
                ),
                {"org": org_id, "source": source},
            )
        )
        .mappings()
        .first()
    )
    if rule is None:
        return {"reason": "no_rule", "team_id": None, "membership_id": None}
    if not rule["is_active"]:
        return {"reason": "team_inactive", "team_id": None, "membership_id": None}
    candidate = (
        (
            await connection.execute(
                text(
                    "SELECT m.id,m.display_name FROM crm.team_memberships tm "
                    "JOIN crm.organization_memberships m ON m.org_id=tm.org_id AND m.id=tm.membership_id "
                    "WHERE tm.org_id=:org AND tm.team_id=:team AND m.status='active' AND (m.is_owner OR COALESCE("
                    "(SELECT x.allowed AND p.is_delegable FROM crm.membership_permission_overrides x "
                    "JOIN crm.permissions p ON p.code=x.permission_code WHERE x.org_id=m.org_id AND x.membership_id=m.id AND x.permission_code='leads.view'),"
                    "EXISTS(SELECT 1 FROM crm.membership_roles mr JOIN crm.roles r ON r.org_id=mr.org_id AND r.id=mr.role_id AND r.is_active "
                    "JOIN crm.role_permissions rp ON rp.org_id=r.org_id AND rp.role_id=r.id AND rp.permission_code='leads.view' "
                    "WHERE mr.org_id=m.org_id AND mr.membership_id=m.id))) "
                    "ORDER BY CASE WHEN CAST(:last AS uuid) IS NULL OR m.id>CAST(:last AS uuid) THEN 0 ELSE 1 END,m.id LIMIT 1"
                ),
                {
                    "org": org_id,
                    "team": rule["team_id"],
                    "last": rule["last_member_id"],
                },
            )
        )
        .mappings()
        .first()
    )
    if candidate is None:
        return {
            "reason": "no_eligible_member",
            "team_id": rule["team_id"],
            "membership_id": None,
        }
    if allocate:
        await connection.execute(
            text(
                "UPDATE crm.source_assignment_rules SET last_member_id=:member WHERE org_id=:org AND source=:source"
            ),
            {"org": org_id, "source": source, "member": candidate["id"]},
        )
    return {
        "reason": "assigned",
        "team_id": rule["team_id"],
        "membership_id": candidate["id"],
        "member_name": candidate["display_name"],
    }


@router.get("/{source}/preview")
async def preview_rule(source: Source, request: Request, user: User):
    async with access(request, user, "assignment_rules.manage") as (
        connection,
        current,
    ):
        require_full_scope(current)
        return await next_assignment(connection, current.org_id, source, allocate=False)


async def route_new_lead(connection, org_id: UUID, source: str, lead_id: UUID) -> None:
    result = await next_assignment(connection, org_id, source, allocate=True)
    if result["reason"] == "no_rule":
        return
    await connection.execute(
        text(
            "UPDATE crm.leads SET assigned_membership_id=:member,team_id=:team,row_version=row_version+1,updated_at=now() "
            "WHERE org_id=:org AND id=:lead"
        ),
        {
            "org": org_id,
            "lead": lead_id,
            "member": result["membership_id"],
            "team": result["team_id"],
        },
    )
    await audit(connection, org_id, None, f"assignment.{result['reason']}", lead_id)
