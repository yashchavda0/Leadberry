import base64
import binascii
import json
import math
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.service import AccessError, Principal, audit
from .queries import JOINS, access, fields, visibility
from .schemas import LeadInput, LeadUpdate, VersionInput
from .configuration import BUILTIN_FIELDS

router = APIRouter(prefix="/api/v1", tags=["Leads"])


def encode_cursor(row) -> str:
    return base64.urlsafe_b64encode(
        f"{row['received_at'].isoformat()}|{row['id']}".encode()
    ).decode()


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        moment, identity = (
            base64.b64decode(value, altchars=b"-_", validate=True).decode().split("|")
        )
        parsed = datetime.fromisoformat(moment)
        if parsed.tzinfo is None:
            raise ValueError("Timezone required")
        return parsed, UUID(identity)
    except (ValueError, UnicodeError, binascii.Error):
        raise AccessError(422, "invalid_cursor") from None


async def get_lead(connection, user: Principal, lead_id: UUID):
    row = (
        (
            await connection.execute(
                text(
                    f"SELECT {fields(user)} {JOINS} WHERE l.org_id=:org AND l.id=:id AND {visibility(user)}"
                ),
                {"org": user.org_id, "id": lead_id, "member": user.member_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise AccessError(404, "lead_not_found")
    return dict(row)


async def validate_references(connection, user: Principal, body: LeadInput) -> UUID:
    status = body.status_id or await connection.scalar(
        text(
            "SELECT id FROM crm.lead_statuses WHERE org_id=:org AND is_active AND is_default"
        ),
        {"org": user.org_id},
    )
    if not await connection.scalar(
        text(
            "SELECT 1 FROM crm.lead_statuses WHERE org_id=:org AND id=:id AND is_active"
        ),
        {"org": user.org_id, "id": status},
    ):
        raise AccessError(422, "invalid_status")
    if body.assigned_membership_id is not None:
        if not await connection.scalar(
            text(
                "SELECT 1 FROM crm.organization_memberships WHERE org_id=:org AND id=:id AND status='active'"
            ),
            {"org": user.org_id, "id": body.assigned_membership_id},
        ):
            raise AccessError(422, "invalid_assignee")
    if body.team_id is not None:
        if not await connection.scalar(
            text("SELECT 1 FROM crm.teams WHERE org_id=:org AND id=:id AND is_active"),
            {"org": user.org_id, "id": body.team_id},
        ):
            raise AccessError(422, "invalid_team")
    return status


def has_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


async def validate_custom_field_values(
    connection, org_id: UUID, values: dict, previous: dict | None = None
) -> None:
    definitions = (
        (
            await connection.execute(
                text(
                    "SELECT field_key,field_type,options FROM crm.lead_custom_fields WHERE org_id=:org AND is_active"
                ),
                {"org": org_id},
            )
        )
        .mappings()
        .all()
    )
    by_key = {row["field_key"]: row for row in definitions}
    for key, value in values.items():
        definition = by_key.get(key)
        if definition is None:
            if previous is not None and previous.get(key) == value:
                continue
            raise AccessError(422, "unknown_custom_field")
        if value is None:
            continue
        field_type = definition["field_type"]
        options = definition["options"]
        valid = (
            isinstance(value, str)
            if field_type == "text"
            else (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                if field_type == "number"
                else (
                    isinstance(value, bool)
                    if field_type == "boolean"
                    else (
                        isinstance(value, str) and value in options
                        if field_type == "select"
                        else False
                    )
                )
            )
        )
        if not valid:
            raise AccessError(422, "invalid_custom_field_value")


async def apply_status_rules(
    connection,
    org_id: UUID,
    status_id: UUID,
    values: dict,
    previous_status_id: UUID | None,
) -> None:
    entering = previous_status_id != status_id
    rule = None
    if entering:
        rule = (
            (
                await connection.execute(
                    text(
                        "SELECT tag_on_entry,auto_assign,round_robin_cursor FROM crm.lead_status_rules "
                        "WHERE org_id=:org AND status_id=:status FOR UPDATE"
                    ),
                    {"org": org_id, "status": status_id},
                )
            )
            .mappings()
            .first()
        )
        if rule and rule["tag_on_entry"]:
            tags = values.setdefault("tags", [])
            if rule["tag_on_entry"] not in tags:
                if len(tags) >= 20:
                    raise AccessError(422, "status_tag_limit_reached")
                tags.append(rule["tag_on_entry"])
    required = (
        (
            await connection.execute(
                text(
                    "SELECT field_key FROM crm.lead_status_required_fields WHERE org_id=:org AND status_id=:status"
                ),
                {"org": org_id, "status": status_id},
            )
        )
        .scalars()
        .all()
    )
    custom = values.get("custom_fields") or {}
    missing = [
        key
        for key in required
        if not has_value(values.get(key) if key in BUILTIN_FIELDS else custom.get(key))
    ]
    if missing:
        raise AccessError(422, "lead_required_fields_missing")
    if not entering or rule is None:
        return
    if not rule["auto_assign"]:
        return
    eligible = (
        (
            await connection.execute(
                text(
                    "SELECT rm.membership_id FROM crm.lead_status_rule_members rm "
                    "JOIN crm.organization_memberships m ON m.org_id=rm.org_id AND m.id=rm.membership_id "
                    "WHERE rm.org_id=:org AND rm.status_id=:status AND m.status='active' "
                    "AND (NOT EXISTS(SELECT 1 FROM crm.lead_status_rule_roles rr WHERE rr.org_id=rm.org_id AND rr.status_id=rm.status_id) "
                    "OR EXISTS(SELECT 1 FROM crm.membership_roles mr "
                    "JOIN crm.roles r ON r.org_id=mr.org_id AND r.id=mr.role_id AND r.is_active "
                    "JOIN crm.lead_status_rule_roles rr ON rr.org_id=mr.org_id AND rr.role_id=mr.role_id "
                    "WHERE mr.org_id=rm.org_id AND mr.membership_id=rm.membership_id AND rr.status_id=rm.status_id)) "
                    "ORDER BY rm.position,rm.membership_id"
                ),
                {"org": org_id, "status": status_id},
            )
        )
        .scalars()
        .all()
    )
    if not eligible:
        raise AccessError(409, "status_assignment_pool_empty")
    cursor = rule["round_robin_cursor"] % len(eligible)
    values["assigned_membership_id"] = eligible[cursor]
    await connection.execute(
        text(
            "UPDATE crm.lead_status_rules SET round_robin_cursor=round_robin_cursor+1,updated_at=now() "
            "WHERE org_id=:org AND status_id=:status"
        ),
        {"org": org_id, "status": status_id},
    )


@router.get("/leads")
async def list_leads(
    request: Request,
    user: User,
    limit: int = Query(25, ge=1, le=100),
    after: str | None = Query(None, max_length=200),
    q: str = Query("", max_length=200),
    status_id: UUID | None = None,
    source: str = Query("", max_length=100),
    integration_id: UUID | None = None,
    source_record_id: str = Query("", max_length=200),
    tag: str = Query("", max_length=50),
    assignee: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    archived: bool = False,
    status_start: date | None = None,
    status_end: date | None = None,
):
    if (start and end and start > end) or (
        status_start and status_end and status_start > status_end
    ):
        raise AccessError(422, "invalid_date_range")
    cursor = decode_cursor(after) if after else None
    async with access(request, user, "leads.view") as (connection, current):
        if (
            archived
            and "leads.archive" not in current.permissions
            and "leads.restore" not in current.permissions
        ):
            raise AccessError(403, "permission_denied")
        conditions = [
            "l.org_id=:org",
            visibility(current),
            "l.archived_at IS NOT NULL" if archived else "l.archived_at IS NULL",
        ]
        parameters = {
            "org": current.org_id,
            "member": current.member_id,
            "limit": limit + 1,
        }
        for enabled, condition, key, value in (
            (
                bool(q.strip()),
                "l.search_document @@ plainto_tsquery('simple',:q)",
                "q",
                q.strip(),
            ),
            (status_id is not None, "l.status_id=:status", "status", status_id),
            (bool(source), "l.source_provider=:source", "source", source),
            (
                integration_id is not None,
                "l.integration_id=:integration",
                "integration",
                integration_id,
            ),
            (
                bool(source_record_id),
                "l.source_record_id=:source_record_id",
                "source_record_id",
                source_record_id,
            ),
            (bool(tag), "l.tags @> ARRAY[CAST(:tag AS text)]", "tag", tag),
            (
                assignee is not None,
                "l.assigned_membership_id=:assignee",
                "assignee",
                assignee,
            ),
            (start is not None, "l.received_at>=CAST(:start AS date)", "start", start),
            (
                end is not None,
                "l.received_at<CAST(:end AS date)+interval '1 day'",
                "end",
                end,
            ),
            (
                status_start is not None,
                "l.status_changed_at>=CAST(:status_start AS date)",
                "status_start",
                status_start,
            ),
            (
                status_end is not None,
                "l.status_changed_at<CAST(:status_end AS date)+interval '1 day'",
                "status_end",
                status_end,
            ),
        ):
            if enabled:
                conditions.append(condition)
                parameters[key] = value
        if cursor:
            conditions.append("(l.received_at,l.id)<(:moment,:id)")
            parameters.update(moment=cursor[0], id=cursor[1])
        rows = (
            (
                await connection.execute(
                    text(
                        f"SELECT {fields(current)} {JOINS} WHERE {' AND '.join(conditions)} "
                        "ORDER BY l.received_at DESC,l.id DESC LIMIT :limit"
                    ),
                    parameters,
                )
            )
            .mappings()
            .all()
        )
        return {
            "data": [dict(row) for row in rows[:limit]],
            "next_cursor": (
                encode_cursor(rows[limit - 1]) if len(rows) > limit else None
            ),
        }


@router.get("/leads/options")
async def lead_options(request: Request, user: User):
    async with access(request, user, "leads.view") as (connection, current):
        statuses = (
            (
                await connection.execute(
                    text(
                        "SELECT s.id,s.name,s.color,s.category AS type,s.is_default, "
                        "COALESCE((SELECT array_agg(r.field_key ORDER BY r.field_key) FROM crm.lead_status_required_fields r "
                        "WHERE r.org_id=s.org_id AND r.status_id=s.id),ARRAY[]::text[]) AS required_fields "
                        "FROM crm.lead_statuses s WHERE s.org_id=:org AND s.is_active ORDER BY s.position,s.name"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        custom_fields = (
            (
                await connection.execute(
                    text(
                        "SELECT field_key,label,field_type,options,position FROM crm.lead_custom_fields "
                        "WHERE org_id=:org AND is_active ORDER BY position,label"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        sources = (
            (
                await connection.execute(
                    text(
                        "SELECT DISTINCT source_provider FROM crm.leads WHERE org_id=:org ORDER BY source_provider"
                    ),
                    {"org": current.org_id},
                )
            )
            .scalars()
            .all()
        )
        accounts = (
            (
                await connection.execute(
                    text(
                        "SELECT id,name FROM crm.marketplace_accounts WHERE org_id=:org AND status<>'retired' ORDER BY name,id"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        return {
            "statuses": [dict(row) for row in statuses],
            "custom_fields": [dict(row) for row in custom_fields],
            "sources": list(sources),
            "accounts": [dict(row) for row in accounts],
        }


@router.get("/leads/assignees")
async def assignees(
    request: Request,
    user: User,
    limit: int = Query(25, ge=1, le=100),
    after: UUID | None = None,
):
    async with access(request, user, "leads.assign") as (connection, current):
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT id,display_name,status FROM crm.organization_memberships WHERE org_id=:org AND status='active' "
                        "AND (CAST(:after AS uuid) IS NULL OR id>:after) ORDER BY id LIMIT :limit"
                    ),
                    {"org": current.org_id, "after": after, "limit": limit + 1},
                )
            )
            .mappings()
            .all()
        )
        return {
            "data": [dict(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }


@router.get("/leads/{lead_id}")
async def detail(lead_id: UUID, request: Request, user: User):
    async with access(request, user, "leads.view") as (connection, current):
        return await get_lead(connection, current, lead_id)


@router.post("/leads", status_code=201)
async def create(body: LeadInput, request: Request, user: User):
    async with access(request, user, "leads.create") as (connection, current):
        if "leads.view" not in current.permissions:
            raise AccessError(403, "permission_denied")
        if "leads.pii.view" not in current.permissions and any(
            (body.phone, body.email, body.address, body.enquiry, body.custom_fields)
        ):
            raise AccessError(403, "pii_permission_required")
        if (
            body.assigned_membership_id not in (None, current.member_id) or body.team_id
        ) and "leads.assign" not in current.permissions:
            raise AccessError(403, "assignment_permission_required")
        status = await validate_references(connection, current, body)
        if current.data_scope != "all" and body.assigned_membership_id not in (
            None,
            current.member_id,
        ):
            raise AccessError(403, "assignment_exceeds_scope")
        if (
            current.data_scope != "all"
            and body.team_id
            and not await connection.scalar(
                text(
                    "SELECT 1 FROM crm.team_memberships WHERE org_id=:org AND team_id=:team AND membership_id=:member"
                ),
                {
                    "org": current.org_id,
                    "team": body.team_id,
                    "member": current.member_id,
                },
            )
        ):
            raise AccessError(403, "assignment_exceeds_scope")
        values = body.model_dump()
        await validate_custom_field_values(
            connection, current.org_id, values["custom_fields"]
        )
        assigned_member = body.assigned_membership_id
        if (
            "leads.assign" not in current.permissions
            or "assigned_membership_id" not in body.model_fields_set
        ):
            assigned_member = current.member_id
        values.update(
            org=current.org_id,
            member=current.member_id,
            status_id=status,
            assigned_membership_id=assigned_member,
            email=str(body.email or ""),
        )
        await apply_status_rules(connection, current.org_id, status, values, None)
        values["custom_fields"] = json.dumps(values["custom_fields"])
        lead_id = await connection.scalar(
            text(
                "INSERT INTO crm.leads(org_id,created_by,name,company,phone,email,city,state,address,product,enquiry,"
                "source_provider,status_id,assigned_membership_id,team_id,tags,custom_fields,next_follow_up_at,status_changed_at) "
                "VALUES(:org,:member,:name,:company,:phone,:email,:city,:state,:address,:product,:enquiry,"
                ":source_provider,:status_id,:assigned_membership_id,:team_id,:tags,CAST(:custom_fields AS jsonb),:next_follow_up_at,now()) RETURNING id"
            ),
            values,
        )
        await audit(
            connection, current.org_id, current.member_id, "lead.created", lead_id
        )
        return await get_lead(connection, current, lead_id)


@router.put("/leads/{lead_id}")
async def replace(lead_id: UUID, body: LeadUpdate, request: Request, user: User):
    async with access(request, user, "leads.edit") as (connection, current):
        if "leads.view" not in current.permissions:
            raise AccessError(403, "permission_denied")
        existing = await get_lead(connection, current, lead_id)
        if existing["archived_at"]:
            raise AccessError(409, "lead_archived")
        if (
            body.assigned_membership_id != existing["assigned_membership_id"]
            or body.team_id != existing["team_id"]
        ) and "leads.assign" not in current.permissions:
            raise AccessError(403, "assignment_permission_required")
        status = await validate_references(connection, current, body)
        values = body.model_dump()
        if "leads.pii.view" not in current.permissions:
            if any(
                (body.phone, body.email, body.address, body.enquiry, body.custom_fields)
            ):
                raise AccessError(403, "pii_permission_required")
            hidden = {"phone", "email", "address", "enquiry", "custom_fields"}
        else:
            hidden = set()
        previous_custom = existing["custom_fields"]
        if "leads.pii.view" not in current.permissions:
            stored = (
                (
                    await connection.execute(
                        text(
                            "SELECT phone,email,address,enquiry,custom_fields FROM crm.leads WHERE org_id=:org AND id=:id"
                        ),
                        {"org": current.org_id, "id": lead_id},
                    )
                )
                .mappings()
                .one()
            )
            values.update(
                phone=stored["phone"],
                email=stored["email"],
                address=stored["address"],
                enquiry=stored["enquiry"],
                custom_fields=stored["custom_fields"],
            )
            previous_custom = stored["custom_fields"]
        await validate_custom_field_values(
            connection, current.org_id, values["custom_fields"], previous_custom
        )
        await apply_status_rules(
            connection, current.org_id, status, values, existing["status_id"]
        )
        values.update(
            org=current.org_id,
            member=current.member_id,
            id=lead_id,
            status_id=status,
            email=str(body.email or ""),
        )
        values["custom_fields"] = json.dumps(values["custom_fields"])
        if "leads.pii.view" not in current.permissions:
            values.update(
                phone=None, email=None, address=None, enquiry=None, custom_fields=None
            )
        columns = set(LeadInput.model_fields) - hidden
        columns.add("status_changed_at")
        if status != existing["status_id"]:
            values["status_changed_at"] = datetime.now(timezone.utc)
        else:
            columns.remove("status_changed_at")
        if "leads.pii.view" not in current.permissions:
            columns.discard("custom_fields")
        assignments = ",".join(
            f"{column}="
            + (
                f"CAST(:{column} AS jsonb)"
                if column == "custom_fields"
                else f":{column}"
            )
            for column in sorted(columns)
        )
        updated = await connection.scalar(
            text(
                f"UPDATE crm.leads l SET {assignments},row_version=row_version+1,updated_at=now() "
                f"WHERE org_id=:org AND id=:id AND row_version=:row_version AND {visibility(current)} RETURNING id"
            ),
            values,
        )
        if not updated:
            raise AccessError(409, "lead_version_conflict")
        await audit(
            connection, current.org_id, current.member_id, "lead.updated", lead_id
        )
        # A valid reassignment can remove this lead from the caller's scope.
        return {"id": lead_id, "row_version": body.row_version + 1}


@router.post("/leads/{lead_id}/archive")
async def archive(lead_id: UUID, body: VersionInput, request: Request, user: User):
    return await set_archive(lead_id, body, request, user, True)


@router.post("/leads/{lead_id}/restore")
async def restore(lead_id: UUID, body: VersionInput, request: Request, user: User):
    return await set_archive(lead_id, body, request, user, False)


async def set_archive(
    lead_id: UUID, body: VersionInput, request: Request, user: Principal, archived: bool
):
    async with access(
        request, user, "leads.archive" if archived else "leads.restore"
    ) as (connection, current):
        await get_lead(connection, current, lead_id)
        updated = await connection.scalar(
            text(
                f"UPDATE crm.leads l SET archived_at={'now()' if archived else 'NULL'},row_version=row_version+1,updated_at=now() "
                f"WHERE org_id=:org AND id=:id AND row_version=:version AND {visibility(current)} RETURNING id"
            ),
            {
                "org": current.org_id,
                "id": lead_id,
                "member": current.member_id,
                "version": body.row_version,
            },
        )
        if not updated:
            raise AccessError(409, "lead_version_conflict")
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "lead.archived" if archived else "lead.restored",
            lead_id,
        )
        return {"id": lead_id, "row_version": body.row_version + 1}
