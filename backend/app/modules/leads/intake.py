import hashlib
import hmac
import json
import re
import secrets
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import EmailStr, Field, field_validator
from sqlalchemy import text

from ...core.unit_of_work import UnitOfWork
from ..identity.dependencies import User
from ..identity.schemas import Input
from ..identity.service import AccessError, audit, effective_access
from .queries import access
from .assignment_rules import route_new_lead
from .routes import apply_status_rules
from ...core.phone import normalize_phone

router = APIRouter(prefix="/api/v1/intake", tags=["Website intake"])
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class KeyInput(Input):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class WebsiteLead(Input):
    name: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    email: EmailStr | None = None
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    product: str = Field(default="", max_length=200)
    enquiry: str = Field(default="", max_length=10000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        return normalize_phone(value)


def require_key_manager(current) -> None:
    if current.data_scope != "all" or not {"leads.create", "leads.pii.view"}.issubset(
        current.permissions
    ):
        raise AccessError(403, "intake_management_requires_full_lead_access")


@router.post("/keys", status_code=201)
async def create_key(body: KeyInput, request: Request, user: User):
    async with access(request, user, "api_keys.manage") as (connection, current):
        require_key_manager(current)
        key_id = uuid4()
        secret = secrets.token_urlsafe(32)
        await connection.execute(
            text(
                "INSERT INTO crm.intake_keys(org_id,id,name,secret_hash,created_by) "
                "VALUES(:org,:id,:name,:hash,:member)"
            ),
            {
                "org": current.org_id,
                "id": key_id,
                "name": body.name,
                "hash": hashlib.sha256(secret.encode()).digest(),
                "member": current.member_id,
            },
        )
        await audit(
            connection, current.org_id, current.member_id, "intake.key_created", key_id
        )
        return {
            "id": key_id,
            "name": body.name,
            "token": f"lbk_{current.org_id.hex}_{key_id.hex}_{secret}",
        }


@router.get("/keys")
async def list_keys(
    request: Request,
    user: User,
    limit: int = Query(25, ge=1, le=100),
    after: UUID | None = None,
):
    async with access(request, user, "api_keys.manage") as (connection, current):
        require_key_manager(current)
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT id,name,created_at,revoked_at FROM crm.intake_keys WHERE org_id=:org "
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


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(key_id: UUID, request: Request, user: User):
    async with access(request, user, "api_keys.manage") as (connection, current):
        require_key_manager(current)
        key = await connection.scalar(
            text(
                "UPDATE crm.intake_keys SET revoked_at=COALESCE(revoked_at,now()) "
                "WHERE org_id=:org AND id=:id RETURNING id"
            ),
            {"org": current.org_id, "id": key_id},
        )
        if key is None:
            raise AccessError(404, "intake_key_not_found")
        await audit(
            connection, current.org_id, current.member_id, "intake.key_revoked", key_id
        )
        return Response(status_code=204)


def parse_token(authorization: str | None) -> tuple[UUID, UUID, str]:
    try:
        scheme, token = (authorization or "").split(" ", 1)
        prefix, organization, key, secret = token.split("_", 3)
        if (
            scheme.lower() != "bearer"
            or prefix != "lbk"
            or not SECRET_PATTERN.fullmatch(secret)
        ):
            raise ValueError()
        return UUID(hex=organization), UUID(hex=key), secret
    except ValueError:
        raise AccessError(401, "invalid_intake_key") from None


@router.post("/leads", status_code=201)
async def submit_lead(
    body: WebsiteLead,
    request: Request,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if request.headers.get("origin"):
        raise AccessError(403, "server_to_server_only")
    if not idempotency_key or not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise AccessError(422, "invalid_idempotency_key")
    org_id, key_id, secret = parse_token(authorization)
    payload_hash = hashlib.sha256(
        json.dumps(
            body.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).digest()
    async with UnitOfWork(request.app.state.database_engine, org_id) as unit:
        connection = unit.connection
        organization = await connection.scalar(
            text(
                "SELECT id FROM crm.organizations WHERE id=:org AND status='active' FOR SHARE"
            ),
            {"org": org_id},
        )
        if not organization:
            raise AccessError(401, "invalid_intake_key")
        key = (
            (
                await connection.execute(
                    text(
                        "SELECT secret_hash,created_by,revoked_at,window_started_at,window_count "
                        "FROM crm.intake_keys WHERE org_id=:org AND id=:id FOR UPDATE"
                    ),
                    {"org": org_id, "id": key_id},
                )
            )
            .mappings()
            .first()
        )
        if (
            key is None
            or key["revoked_at"]
            or not hmac.compare_digest(
                bytes(key["secret_hash"]), hashlib.sha256(secret.encode()).digest()
            )
        ):
            raise AccessError(401, "invalid_intake_key")
        try:
            _, permissions, scope, _ = await effective_access(
                connection, org_id, key["created_by"]
            )
        except AccessError:
            raise AccessError(401, "invalid_intake_key") from None
        if scope != "all" or not {
            "api_keys.manage",
            "leads.create",
            "leads.pii.view",
        }.issubset(permissions):
            raise AccessError(401, "invalid_intake_key")
        allowed = await connection.scalar(
            text(
                "UPDATE crm.intake_keys SET window_count=CASE WHEN window_started_at<now()-interval '1 minute' THEN 1 ELSE window_count+1 END, "
                "window_started_at=CASE WHEN window_started_at<now()-interval '1 minute' THEN now() ELSE window_started_at END "
                "WHERE org_id=:org AND id=:id AND (window_started_at<now()-interval '1 minute' OR window_count<60) RETURNING id"
            ),
            {"org": org_id, "id": key_id},
        )
        if not allowed:
            raise AccessError(429, "intake_rate_limited")
        receipt = (
            (
                await connection.execute(
                    text(
                        "SELECT lead_id,payload_hash FROM crm.intake_receipts WHERE org_id=:org AND key_id=:key AND idempotency_key=:idempotency"
                    ),
                    {"org": org_id, "key": key_id, "idempotency": idempotency_key},
                )
            )
            .mappings()
            .first()
        )
        if receipt:
            if not hmac.compare_digest(bytes(receipt["payload_hash"]), payload_hash):
                raise AccessError(409, "idempotency_conflict")
            response.status_code = 200
            return {"id": receipt["lead_id"], "created": False}
        status_id = await connection.scalar(
            text(
                "SELECT id FROM crm.lead_statuses WHERE org_id=:org AND is_default AND is_active"
            ),
            {"org": org_id},
        )
        if not status_id:
            raise AccessError(409, "default_status_unavailable")
        values = body.model_dump(mode="json")
        values.update(
            org=org_id,
            member=key["created_by"],
            status_id=status_id,
            assigned_membership_id=None,
            tags=[],
            custom_fields={},
            next_follow_up_at=None,
        )
        await apply_status_rules(
            connection, org_id, status_id, values, None, skip_auto_assignment=True
        )
        lead_id = await connection.scalar(
            text(
                "INSERT INTO crm.leads(org_id,created_by,name,company,phone,email,city,state,product,enquiry,"
                "source_provider,status_id,assigned_membership_id,tags,custom_fields,status_changed_at) "
                "VALUES(:org,:member,:name,:company,:phone,:email,:city,:state,:product,:enquiry,"
                "'website',:status_id,:assigned_membership_id,:tags,CAST(:custom_fields AS jsonb),now()) RETURNING id"
            ),
            {**values, "email": values["email"] or "", "custom_fields": "{}"},
        )
        await route_new_lead(connection, org_id, "website", lead_id)
        await connection.execute(
            text(
                "INSERT INTO crm.intake_receipts(org_id,key_id,idempotency_key,payload_hash,lead_id) "
                "VALUES(:org,:key,:idempotency,:hash,:lead)"
            ),
            {
                "org": org_id,
                "key": key_id,
                "idempotency": idempotency_key,
                "hash": payload_hash,
                "lead": lead_id,
            },
        )
        await audit(
            connection, org_id, key["created_by"], "intake.lead_created", lead_id
        )
        return {"id": lead_id, "created": True}
