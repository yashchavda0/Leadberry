from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, Field
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.schemas import Input
from ..identity.service import AccessError, audit
from .queries import access, visibility
from .routes import decode_cursor, encode_cursor, get_lead

router = APIRouter(prefix="/api/v1", tags=["Follow-ups"])


class CompleteFollowUp(Input):
    row_version: int = Field(ge=1)
    note: str = Field(default="", max_length=2000)


class RescheduleFollowUp(Input):
    row_version: int = Field(ge=1)
    due_at: AwareDatetime


class CancelFollowUp(Input):
    row_version: int = Field(ge=1)


def task_columns(can_view_pii: bool) -> str:
    note = "t.note" if can_view_pii else "NULL::text"
    return (
        "t.id,t.lead_id,t.assigned_membership_id,t.due_at,t.state,"
        f"{note} AS note,t.completed_by,t.completed_at,t.created_at,t.updated_at,t.row_version,"
        "l.name AS lead_name,l.status_id,s.name AS lead_status,m.display_name AS assignee"
    )


@router.get("/follow-ups")
async def list_follow_ups(
    request: Request,
    user: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: str | None = None,
    assignee: UUID | None = None,
    due_before: AwareDatetime | None = None,
    due_after: AwareDatetime | None = None,
    period: Literal["all", "overdue", "today", "upcoming"] = "all",
):
    async with access(request, user, "leads.view") as (connection, current):
        params = {
            "org": current.org_id,
            "member": current.member_id,
            "limit": limit + 1,
        }
        conditions = [
            "t.org_id=:org",
            "t.state='open'",
            "l.archived_at IS NULL",
            visibility(current),
        ]
        if after:
            moment, identity = decode_cursor(after)
            conditions.append("(t.due_at,t.id)>(:cursor_time,:cursor_id)")
            params.update(cursor_time=moment, cursor_id=identity)
        if assignee:
            conditions.append("t.assigned_membership_id=:assignee")
            params["assignee"] = assignee
        if due_before:
            conditions.append("t.due_at<:due_before")
            params["due_before"] = due_before
        if due_after:
            conditions.append("t.due_at>=:due_after")
            params["due_after"] = due_after
        if period == "overdue":
            conditions.append("t.due_at<now()")
        elif period in ("today", "upcoming"):
            zone = await connection.scalar(
                text("SELECT timezone FROM crm.organizations WHERE id=:org"),
                {"org": current.org_id},
            )
            params["zone"] = zone or "UTC"
            start = "(date_trunc('day',now() AT TIME ZONE :zone) AT TIME ZONE :zone)"
            end = "((date_trunc('day',now() AT TIME ZONE :zone) + interval '1 day') AT TIME ZONE :zone)"
            conditions.append(
                f"t.due_at>={start} AND t.due_at<{end}"
                if period == "today"
                else f"t.due_at>={end}"
            )
        rows = (
            (
                await connection.execute(
                    text(
                        f"SELECT {task_columns('leads.pii.view' in current.permissions)} "
                        "FROM crm.follow_up_tasks t JOIN crm.leads l ON l.org_id=t.org_id AND l.id=t.lead_id "
                        "JOIN crm.lead_statuses s ON s.org_id=l.org_id AND s.id=l.status_id "
                        "LEFT JOIN crm.organization_memberships m ON m.org_id=t.org_id AND m.id=t.assigned_membership_id "
                        f"WHERE {' AND '.join(conditions)} ORDER BY t.due_at,t.id LIMIT :limit"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        page = [dict(row) for row in rows[:limit]]
        cursor = (
            encode_cursor({"received_at": page[-1]["due_at"], "id": page[-1]["id"]})
            if len(rows) > limit
            else None
        )
        return {"data": page, "next_cursor": cursor}


@router.get("/leads/{lead_id}/follow-ups")
async def follow_up_history(
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
            cursor_condition = " AND (t.created_at,t.id)<(:cursor_time,:cursor_id)"
        rows = (
            (
                await connection.execute(
                    text(
                        f"SELECT {task_columns('leads.pii.view' in current.permissions)} "
                        "FROM crm.follow_up_tasks t JOIN crm.leads l ON l.org_id=t.org_id AND l.id=t.lead_id "
                        "JOIN crm.lead_statuses s ON s.org_id=l.org_id AND s.id=l.status_id "
                        "LEFT JOIN crm.organization_memberships m ON m.org_id=t.org_id AND m.id=t.assigned_membership_id "
                        "WHERE t.org_id=:org AND t.lead_id=:lead"
                        + cursor_condition
                        + " ORDER BY t.created_at DESC,t.id DESC LIMIT :limit"
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


async def change_follow_up(
    task_id: UUID, body, request: Request, user: User, action: str
):
    async with access(request, user, "leads.edit") as (connection, current):
        if "leads.view" not in current.permissions:
            raise AccessError(403, "permission_denied")
        lead = (
            (
                await connection.execute(
                    text(
                        "SELECT l.id,l.archived_at FROM crm.follow_up_tasks t "
                        "JOIN crm.leads l ON l.org_id=t.org_id AND l.id=t.lead_id "
                        f"WHERE t.org_id=:org AND t.id=:task AND {visibility(current)} FOR UPDATE OF l"
                    ),
                    {
                        "org": current.org_id,
                        "member": current.member_id,
                        "task": task_id,
                    },
                )
            )
            .mappings()
            .first()
        )
        if lead is None:
            raise AccessError(404, "follow_up_not_found")
        if lead["archived_at"]:
            raise AccessError(409, "lead_archived")
        task = (
            (
                await connection.execute(
                    text(
                        "SELECT state,row_version FROM crm.follow_up_tasks WHERE org_id=:org AND id=:task FOR UPDATE"
                    ),
                    {"org": current.org_id, "task": task_id},
                )
            )
            .mappings()
            .one()
        )
        if task["state"] != "open" or task["row_version"] != body.row_version:
            raise AccessError(409, "follow_up_version_conflict")
        if action == "complete":
            if body.note and "leads.pii.view" not in current.permissions:
                raise AccessError(403, "pii_permission_required")
            await connection.execute(
                text(
                    "UPDATE crm.follow_up_tasks SET state='completed',note=:note,completed_by=:member,"
                    "completed_at=now(),updated_at=now(),row_version=row_version+1 WHERE org_id=:org AND id=:task"
                ),
                {
                    "org": current.org_id,
                    "task": task_id,
                    "member": current.member_id,
                    "note": body.note.strip(),
                },
            )
        due_at: datetime | None = body.due_at if action == "reschedule" else None
        await connection.execute(
            text(
                "UPDATE crm.leads SET next_follow_up_at=:due_at,row_version=row_version+1,updated_at=now() "
                "WHERE org_id=:org AND id=:lead"
            ),
            {"org": current.org_id, "lead": lead["id"], "due_at": due_at},
        )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            f"follow_up.{action}",
            lead["id"],
        )
        return {
            "id": task_id,
            "state": (
                "completed"
                if action == "complete"
                else "cancelled" if action == "cancel" else "open"
            ),
        }


@router.post("/follow-ups/{task_id}/complete")
async def complete_follow_up(
    task_id: UUID, body: CompleteFollowUp, request: Request, user: User
):
    return await change_follow_up(task_id, body, request, user, "complete")


@router.post("/follow-ups/{task_id}/reschedule")
async def reschedule_follow_up(
    task_id: UUID, body: RescheduleFollowUp, request: Request, user: User
):
    return await change_follow_up(task_id, body, request, user, "reschedule")


@router.post("/follow-ups/{task_id}/cancel")
async def cancel_follow_up(
    task_id: UUID, body: CancelFollowUp, request: Request, user: User
):
    return await change_follow_up(task_id, body, request, user, "cancel")
