import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.service import AccessError, audit
from .queries import access

router = APIRouter(prefix="/api/v1", tags=["Lead configuration"])

STATUS_CATEGORIES = ("new", "pending", "working", "won", "lost")
BUILTIN_FIELDS = {
    "name",
    "company",
    "phone",
    "email",
    "product",
    "city",
    "state",
    "address",
    "enquiry",
    "tags",
    "next_follow_up_at",
}
DEFAULT_COLUMNS = [
    "name",
    "company",
    "email",
    "phone",
    "city",
    "state",
    "address",
    "product",
    "enquiry",
    "status_changed_at",
    "status",
    "source_name",
    "source_provider",
    "source_record_id",
    "received_at",
    "assignee",
    "team_name",
    "tags",
    "next_follow_up_at",
    "updated_at",
    "archived_at",
]
DEFAULT_VISIBLE_COLUMNS = [
    "company",
    "email",
    "phone",
    "name",
    "status_changed_at",
    "status",
    "source_name",
    "received_at",
]


class StatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    category: Literal["new", "pending", "working", "won", "lost"]
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    position: int = Field(ge=0, le=10000)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Status name is required")
        return value


class StatusCreateInput(StatusInput):
    next_follow_up_required: bool = False


class StatusRulesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag_on_entry: str | None = Field(None, max_length=50)
    auto_assign: bool = False
    member_ids: list[UUID] = Field(default_factory=list, max_length=200)
    role_ids: list[UUID] = Field(default_factory=list, max_length=100)
    required_fields: list[str] = Field(default_factory=list, max_length=50)


class CustomFieldInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=100)
    field_type: Literal["text", "number", "boolean", "select"]
    options: list[str] = Field(default_factory=list, max_length=100)
    position: int = Field(ge=0, le=10000)
    is_active: bool = True

    @field_validator("label")
    @classmethod
    def valid_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field label is required")
        return value

    @field_validator("options")
    @classmethod
    def normalized_options(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values]


class CustomFieldCreate(CustomFieldInput):
    field_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")


class ColumnPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[str] = Field(min_length=1, max_length=500)


async def validate_status_rules(
    connection, org_id: UUID, rules: StatusRulesInput
) -> None:
    if rules.auto_assign and not rules.member_ids:
        raise AccessError(422, "status_assignment_pool_required")
    if len(set(rules.member_ids)) != len(rules.member_ids) or len(
        set(rules.role_ids)
    ) != len(rules.role_ids):
        raise AccessError(422, "duplicate_status_rule_member")
    if len(set(rules.required_fields)) != len(rules.required_fields):
        raise AccessError(422, "duplicate_required_field")
    if rules.tag_on_entry is not None and not rules.tag_on_entry.strip():
        raise AccessError(422, "invalid_status_tag")
    valid_fields = set(BUILTIN_FIELDS)
    custom_rows = await connection.execute(
        text(
            "SELECT field_key FROM crm.lead_custom_fields WHERE org_id=:org AND is_active"
        ),
        {"org": org_id},
    )
    valid_fields.update(row[0] for row in custom_rows)
    if any(field not in valid_fields for field in rules.required_fields):
        raise AccessError(422, "invalid_required_field")
    if rules.member_ids:
        members = await connection.execute(
            text(
                "SELECT id FROM crm.organization_memberships WHERE org_id=:org AND status='active' AND id=ANY(:ids)"
            ),
            {"org": org_id, "ids": rules.member_ids},
        )
        if {row[0] for row in members} != set(rules.member_ids):
            raise AccessError(422, "invalid_status_assignment_member")
    if rules.role_ids:
        roles = await connection.execute(
            text(
                "SELECT id FROM crm.roles WHERE org_id=:org AND is_active AND id=ANY(:ids)"
            ),
            {"org": org_id, "ids": rules.role_ids},
        )
        if {row[0] for row in roles} != set(rules.role_ids):
            raise AccessError(422, "invalid_status_assignment_role")


async def replace_status_rules(
    connection, org_id: UUID, status_id: UUID, rules: StatusRulesInput
) -> None:
    await validate_status_rules(connection, org_id, rules)
    await connection.execute(
        text(
            "INSERT INTO crm.lead_status_rules(org_id,status_id,tag_on_entry,auto_assign) "
            "VALUES(:org,:status,:tag,:auto) ON CONFLICT(org_id,status_id) DO UPDATE "
            "SET tag_on_entry=excluded.tag_on_entry,auto_assign=excluded.auto_assign,updated_at=now()"
        ),
        {
            "org": org_id,
            "status": status_id,
            "tag": rules.tag_on_entry.strip() if rules.tag_on_entry else None,
            "auto": rules.auto_assign,
        },
    )
    for table in (
        "lead_status_rule_members",
        "lead_status_rule_roles",
        "lead_status_required_fields",
    ):
        await connection.execute(
            text(f"DELETE FROM crm.{table} WHERE org_id=:org AND status_id=:status"),
            {"org": org_id, "status": status_id},
        )
    if rules.member_ids:
        await connection.execute(
            text(
                "INSERT INTO crm.lead_status_rule_members(org_id,status_id,membership_id,position) "
                "SELECT :org,:status,item,ordinality::integer FROM unnest(CAST(:ids AS uuid[])) "
                "WITH ORDINALITY AS selected(item,ordinality)"
            ),
            {"org": org_id, "status": status_id, "ids": rules.member_ids},
        )
    for table, field, values in (
        ("lead_status_rule_roles", "role_id", rules.role_ids),
        ("lead_status_required_fields", "field_key", rules.required_fields),
    ):
        if values:
            await connection.execute(
                text(
                    f"INSERT INTO crm.{table}(org_id,status_id,{field}) "
                    f"SELECT :org,:status,value FROM unnest(CAST(:values AS {'uuid[]' if field == 'role_id' else 'text[]'})) AS value"
                ),
                {"org": org_id, "status": status_id, "values": values},
            )


async def status_payload(connection, org_id: UUID, status: dict) -> dict:
    rules = (
        (
            await connection.execute(
                text(
                    "SELECT tag_on_entry,auto_assign,round_robin_cursor FROM crm.lead_status_rules "
                    "WHERE org_id=:org AND status_id=:status"
                ),
                {"org": org_id, "status": status["id"]},
            )
        )
        .mappings()
        .first()
    )
    members = (
        (
            await connection.execute(
                text(
                    "SELECT membership_id FROM crm.lead_status_rule_members WHERE org_id=:org AND status_id=:status ORDER BY position,membership_id"
                ),
                {"org": org_id, "status": status["id"]},
            )
        )
        .scalars()
        .all()
    )
    roles = (
        (
            await connection.execute(
                text(
                    "SELECT role_id FROM crm.lead_status_rule_roles WHERE org_id=:org AND status_id=:status ORDER BY role_id"
                ),
                {"org": org_id, "status": status["id"]},
            )
        )
        .scalars()
        .all()
    )
    required = (
        (
            await connection.execute(
                text(
                    "SELECT field_key FROM crm.lead_status_required_fields WHERE org_id=:org AND status_id=:status ORDER BY field_key"
                ),
                {"org": org_id, "status": status["id"]},
            )
        )
        .scalars()
        .all()
    )
    return {
        **status,
        "tag_on_entry": rules["tag_on_entry"] if rules else None,
        "auto_assign": rules["auto_assign"] if rules else False,
        "member_ids": members,
        "role_ids": roles,
        "required_fields": required,
    }


@router.get("/lead-statuses")
async def list_statuses(request: Request, user: User):
    async with access(request, user, "settings.view") as (connection, current):
        statuses = (
            (
                await connection.execute(
                    text(
                        "SELECT id,name,category AS type,color,position,is_active,is_default,is_system "
                        "FROM crm.lead_statuses WHERE org_id=:org ORDER BY position,name"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        return {
            "data": [
                await status_payload(connection, current.org_id, dict(row))
                for row in statuses
            ]
        }


@router.get("/lead-status-options")
async def lead_status_options(request: Request, user: User):
    async with access(request, user, "assignment_rules.manage") as (
        connection,
        current,
    ):
        members = (
            (
                await connection.execute(
                    text(
                        "SELECT id,display_name FROM crm.organization_memberships "
                        "WHERE org_id=:org AND status='active' ORDER BY display_name,id"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        roles = (
            (
                await connection.execute(
                    text(
                        "SELECT id,name FROM crm.roles WHERE org_id=:org AND is_active ORDER BY name,id"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        fields = (
            (
                await connection.execute(
                    text(
                        "SELECT field_key,label,field_type FROM crm.lead_custom_fields "
                        "WHERE org_id=:org AND is_active ORDER BY position,label"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        return {
            "members": [dict(row) for row in members],
            "roles": [dict(row) for row in roles],
            "custom_fields": [dict(row) for row in fields],
        }


@router.post("/lead-statuses", status_code=201)
async def create_status(body: StatusCreateInput, request: Request, user: User):
    async with access(request, user, "settings.manage") as (connection, current):
        if (
            body.next_follow_up_required
            and "assignment_rules.manage" not in current.permissions
        ):
            raise AccessError(403, "permission_denied")
        status_id = uuid4()
        await connection.execute(
            text(
                "INSERT INTO crm.lead_statuses(org_id,id,name,category,color,position) "
                "VALUES(:org,:id,:name,:category,:color,:position)"
            ),
            {
                "org": current.org_id,
                "id": status_id,
                "name": body.name.strip(),
                "category": body.category,
                "color": body.color,
                "position": body.position,
            },
        )
        if body.next_follow_up_required:
            await connection.execute(
                text(
                    "INSERT INTO crm.lead_status_required_fields(org_id,status_id,field_key) "
                    "VALUES(:org,:status,'next_follow_up_at')"
                ),
                {"org": current.org_id, "status": status_id},
            )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "lead_status.created",
            status_id,
        )
        return {"id": status_id, "status": "created"}


@router.put("/lead-statuses/{status_id}")
async def update_status(
    status_id: UUID, body: StatusInput, request: Request, user: User
):
    async with access(request, user, "settings.manage") as (connection, current):
        existing = (
            (
                await connection.execute(
                    text(
                        "SELECT is_system,is_default,name,category FROM crm.lead_statuses WHERE org_id=:org AND id=:id FOR UPDATE"
                    ),
                    {"org": current.org_id, "id": status_id},
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            raise AccessError(404, "lead_status_not_found")
        if existing["is_system"] and (
            body.name.strip() != existing["name"]
            or body.category != existing["category"]
            or not body.is_active
        ):
            raise AccessError(409, "system_status_protected")
        if existing["is_default"] and not body.is_active:
            raise AccessError(409, "default_status_required")
        if not body.is_active and await connection.scalar(
            text("SELECT 1 FROM crm.leads WHERE org_id=:org AND status_id=:id LIMIT 1"),
            {"org": current.org_id, "id": status_id},
        ):
            raise AccessError(409, "lead_status_in_use")
        await connection.execute(
            text(
                "UPDATE crm.lead_statuses SET name=:name,category=:category,color=:color,position=:position,is_active=:active "
                "WHERE org_id=:org AND id=:id"
            ),
            {
                "org": current.org_id,
                "id": status_id,
                "name": body.name.strip(),
                "category": body.category,
                "color": body.color,
                "position": body.position,
                "active": body.is_active,
            },
        )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "lead_status.updated",
            status_id,
        )
        return {"id": status_id, "status": "updated"}


@router.put("/lead-statuses/{status_id}/rules")
async def update_status_rules(
    status_id: UUID, body: StatusRulesInput, request: Request, user: User
):
    async with access(request, user, "assignment_rules.manage") as (
        connection,
        current,
    ):
        if not await connection.scalar(
            text(
                "SELECT 1 FROM crm.lead_statuses WHERE org_id=:org AND id=:id AND is_active"
            ),
            {"org": current.org_id, "id": status_id},
        ):
            raise AccessError(404, "lead_status_not_found")
        await replace_status_rules(connection, current.org_id, status_id, body)
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "lead_status.rules_updated",
            status_id,
        )
        return {"id": status_id, "status": "updated"}


@router.get("/lead-custom-fields")
async def list_custom_fields(request: Request, user: User):
    async with access(request, user, "settings.view") as (connection, current):
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT field_key,label,field_type,options,position,is_active FROM crm.lead_custom_fields "
                        "WHERE org_id=:org ORDER BY position,label"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
        )
        return {"data": [dict(row) for row in rows]}


def validate_custom_field_input(body: CustomFieldInput) -> None:
    if body.field_type == "select":
        if not body.options or any(
            not item.strip() or len(item) > 100 for item in body.options
        ):
            raise AccessError(422, "invalid_custom_field_options")
        if len(set(body.options)) != len(body.options):
            raise AccessError(422, "duplicate_custom_field_option")
    elif body.options:
        raise AccessError(422, "options_only_for_select_fields")


@router.post("/lead-custom-fields", status_code=201)
async def create_custom_field(body: CustomFieldCreate, request: Request, user: User):
    validate_custom_field_input(body)
    if body.field_key in BUILTIN_FIELDS:
        raise AccessError(422, "reserved_custom_field_key")
    async with access(request, user, "settings.manage") as (connection, current):
        await connection.execute(
            text(
                "INSERT INTO crm.lead_custom_fields(org_id,field_key,label,field_type,options,position,is_active) "
                "VALUES(:org,:key,:label,:type,CAST(:options AS jsonb),:position,:active)"
            ),
            {
                "org": current.org_id,
                "key": body.field_key,
                "label": body.label.strip(),
                "type": body.field_type,
                "options": json.dumps(body.options),
                "position": body.position,
                "active": body.is_active,
            },
        )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "lead_custom_field.created",
            None,
        )
        return {"field_key": body.field_key, "status": "created"}


@router.put("/lead-custom-fields/{field_key}")
async def update_custom_field(
    field_key: str, body: CustomFieldInput, request: Request, user: User
):
    validate_custom_field_input(body)
    async with access(request, user, "settings.manage") as (connection, current):
        existing = (
            (
                await connection.execute(
                    text(
                        "SELECT field_type,options FROM crm.lead_custom_fields WHERE org_id=:org AND field_key=:key"
                    ),
                    {"org": current.org_id, "key": field_key},
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            raise AccessError(404, "custom_field_not_found")
        has_values = await connection.scalar(
            text(
                "SELECT 1 FROM crm.leads WHERE org_id=:org AND custom_fields ? :key LIMIT 1"
            ),
            {"org": current.org_id, "key": field_key},
        )
        if has_values and (
            existing["field_type"] != body.field_type
            or existing["options"] != body.options
        ):
            raise AccessError(409, "custom_field_values_in_use")
        if not body.is_active and await connection.scalar(
            text(
                "SELECT 1 FROM crm.lead_status_required_fields WHERE org_id=:org AND field_key=:key LIMIT 1"
            ),
            {"org": current.org_id, "key": field_key},
        ):
            raise AccessError(409, "custom_field_required_by_status")
        await connection.execute(
            text(
                "UPDATE crm.lead_custom_fields SET label=:label,field_type=:type,options=CAST(:options AS jsonb),"
                "position=:position,is_active=:active,updated_at=now() WHERE org_id=:org AND field_key=:key"
            ),
            {
                "org": current.org_id,
                "key": field_key,
                "label": body.label.strip(),
                "type": body.field_type,
                "options": json.dumps(body.options),
                "position": body.position,
                "active": body.is_active,
            },
        )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "lead_custom_field.updated",
            None,
        )
        return {"field_key": field_key, "status": "updated"}


def is_pii_table_column(column: str) -> bool:
    return column in ("email", "phone", "address", "enquiry") or column.startswith(
        "custom:"
    )


async def available_table_columns(connection, org_id: UUID) -> list[str]:
    custom_keys = await connection.scalars(
        text(
            "SELECT field_key FROM crm.lead_custom_fields WHERE org_id=:org AND is_active "
            "ORDER BY position,label"
        ),
        {"org": org_id},
    )
    return DEFAULT_COLUMNS + [f"custom:{key}" for key in custom_keys]


@router.get("/lead-table-preferences")
async def get_table_preferences(request: Request, user: User):
    async with access(request, user, "leads.view") as (connection, current):
        available = await available_table_columns(connection, current.org_id)
        columns = await connection.scalar(
            text(
                "SELECT columns FROM crm.lead_table_preferences WHERE org_id=:org AND membership_id=:member"
            ),
            {"org": current.org_id, "member": current.member_id},
        )
        if columns is None:
            columns = [
                column for column in DEFAULT_VISIBLE_COLUMNS if column in available
            ]
        else:
            columns = [column for column in columns if column in available]
        if "leads.pii.view" not in current.permissions:
            columns = [column for column in columns if not is_pii_table_column(column)]
        return {"columns": columns or ["name"]}


@router.put("/lead-table-preferences")
async def save_table_preferences(body: ColumnPreferences, request: Request, user: User):
    if len(set(body.columns)) != len(body.columns):
        raise AccessError(422, "invalid_lead_table_columns")
    async with access(request, user, "leads.view") as (connection, current):
        available = await available_table_columns(connection, current.org_id)
        if any(column not in available for column in body.columns):
            raise AccessError(422, "invalid_lead_table_columns")
        columns = body.columns
        if "leads.pii.view" not in current.permissions:
            columns = [column for column in columns if not is_pii_table_column(column)]
        if not columns:
            raise AccessError(422, "invalid_lead_table_columns")
        await connection.execute(
            text(
                "INSERT INTO crm.lead_table_preferences(org_id,membership_id,columns) "
                "VALUES(:org,:member,CAST(:columns AS jsonb)) ON CONFLICT(org_id,membership_id) "
                "DO UPDATE SET columns=excluded.columns,updated_at=now()"
            ),
            {
                "org": current.org_id,
                "member": current.member_id,
                "columns": json.dumps(columns),
            },
        )
        return {"columns": columns}
