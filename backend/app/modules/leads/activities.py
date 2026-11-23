from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.schemas import Input
from ..identity.service import AccessError, audit
from .queries import access, visibility
from .routes import decode_cursor, encode_cursor, get_lead

router = APIRouter(prefix="/api/v1", tags=["Lead activities"])


class ActivityInput(Input):
    activity_type: Literal["call", "email", "meeting", "other"]
    outcome: Literal[
        "connected", "no_answer", "left_message", "scheduled", "not_applicable"
    ]
    note: str = Field(default="", max_length=2000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str) -> str:
        return value.strip()


def activity_note(can_view_pii: bool) -> str:
    return "a.note" if can_view_pii else "NULL::text"


@router.get("/leads/{lead_id}/activities")
async def list_activities(
    lead_id: UUID,
    request: Request,
    user: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: str | None = None,
):
    async with access(request, user, "leads.view") as (connection, current):
        await get_lead(connection, current, lead_id)
        params = {"org": current.org_id, "lead": lead_id, "limit": limit + 1}
        cursor_condition = ""
        if after:
            moment, identity = decode_cursor(after)
            params.update(cursor_time=moment, cursor_id=identity)
            cursor_condition = " AND (a.created_at,a.id)<(:cursor_time,:cursor_id)"
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT a.id,a.lead_id,a.actor_membership_id,m.display_name AS actor_name,"
                        "a.activity_type,a.outcome,"
                        + activity_note("leads.pii.view" in current.permissions)
                        + " AS note,"
                        "a.created_at FROM crm.lead_activities a "
                        "JOIN crm.organization_memberships m ON m.org_id=a.org_id AND m.id=a.actor_membership_id "
                        "WHERE a.org_id=:org AND a.lead_id=:lead"
                        + cursor_condition
                        + " ORDER BY a.created_at DESC,a.id DESC LIMIT :limit"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        page = [dict(row) for row in rows[:limit]]
        cursor = (
            encode_cursor({"received_at": page[-1]["created_at"], "id": page[-1]["id"]})
            if len(rows) > limit
            else None
        )
        return {"data": page, "next_cursor": cursor}


@router.post("/leads/{lead_id}/activities", status_code=201)
async def create_activity(
    lead_id: UUID, body: ActivityInput, request: Request, user: User
):
    async with access(request, user, "leads.edit") as (connection, current):
        if "leads.view" not in current.permissions:
            raise AccessError(403, "permission_denied")
        lead = await get_lead(connection, current, lead_id)
        locked = (
            (
                await connection.execute(
                    text(
                        "SELECT archived_at FROM crm.leads l WHERE l.org_id=:org AND l.id=:lead AND "
                        f"{visibility(current)} FOR UPDATE"
                    ),
                    {
                        "org": current.org_id,
                        "lead": lead_id,
                        "member": current.member_id,
                    },
                )
            )
            .mappings()
            .first()
        )
        if locked is None:
            raise AccessError(404, "lead_not_found")
        if locked["archived_at"]:
            raise AccessError(409, "lead_archived")
        if body.note and "leads.pii.view" not in current.permissions:
            raise AccessError(403, "pii_permission_required")
        activity_id = uuid4()
        created_at = await connection.scalar(
            text(
                "INSERT INTO crm.lead_activities(org_id,id,lead_id,actor_membership_id,activity_type,outcome,note) "
                "VALUES(:org,:id,:lead,:actor,:type,:outcome,:note) RETURNING created_at"
            ),
            {
                "org": current.org_id,
                "id": activity_id,
                "lead": lead_id,
                "actor": current.member_id,
                "type": body.activity_type,
                "outcome": body.outcome,
                "note": body.note,
            },
        )
        actor_name = await connection.scalar(
            text(
                "SELECT display_name FROM crm.organization_memberships WHERE org_id=:org AND id=:actor"
            ),
            {"org": current.org_id, "actor": current.member_id},
        )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "lead.activity_logged",
            lead_id,
        )
        return {
            "id": activity_id,
            "lead_id": lead_id,
            "actor_membership_id": current.member_id,
            "actor_name": actor_name,
            "activity_type": body.activity_type,
            "outcome": body.outcome,
            "note": body.note if "leads.pii.view" in current.permissions else None,
            "created_at": created_at,
        }
