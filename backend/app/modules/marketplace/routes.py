import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.service import AccessError, audit, effective_access
from ..leads.queries import access
from .catalog import PROVIDERS, provider, validate_configuration
from .crypto import encrypt_credentials, load_public_key

router = APIRouter(prefix="/api/v1/marketplace", tags=["Marketplace"])
SAFE_FIELDS = "id,provider_code,name,status,config,credential_version,verified_version,row_version,last_success_at,last_received_at,safe_error_code,default_assignee_membership_id,created_at,updated_at"


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider_code: str = Field(max_length=40)
    name: str = Field(min_length=1, max_length=100)
    config: dict[str, str] = Field(default_factory=dict, max_length=10)
    credentials: dict[str, SecretStr] = Field(default_factory=dict, max_length=10)
    row_version: int | None = Field(None, ge=1)
    default_assignee_membership_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Account name is required")
        return value.strip()

    @field_validator("config", "credentials")
    @classmethod
    def bounded_fields(cls, value: dict) -> dict:
        if any(len(key) > 40 or len(item.get_secret_value() if isinstance(item, SecretStr) else item) > 4096
               for key, item in value.items()):
            raise ValueError("Configuration field exceeds maximum length")
        return value


class AccountAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_version: int = Field(ge=1)


async def account(connection, org: UUID, identity: UUID) -> dict:
    row = (await connection.execute(text(f"SELECT {SAFE_FIELDS} FROM crm.marketplace_accounts WHERE org_id=:org AND id=:id"),
                                    {"org": org, "id": identity})).mappings().first()
    if row is None:
        raise AccessError(404, "marketplace_account_not_found")
    return dict(row)


async def validate_default_assignee(connection, current, member: UUID | None) -> None:
    if member is None:
        return
    if "leads.assign" not in current.permissions:
        raise AccessError(403, "permission_denied")
    try:
        _, permissions, _, _ = await effective_access(connection, current.org_id, member)
    except AccessError:
        raise AccessError(422, "invalid_assignee")
    if "leads.assign" not in permissions:
        raise AccessError(422, "invalid_assignee")


@router.get("/providers")
async def providers(request: Request, user: User):
    async with access(request, user, "marketplace.view"):
        configuration = request.app.state.configuration
        try:
            load_public_key(configuration)
            ready = True
        except AccessError:
            ready = False
        return {"data": PROVIDERS, "credential_storage_ready": ready}


@router.get("/assignees")
async def assignees(request: Request, user: User):
    async with access(request, user, "marketplace.manage") as (connection, current):
        members = (await connection.execute(text(
            "SELECT id,display_name FROM crm.organization_memberships WHERE org_id=:org AND status='active' ORDER BY display_name,id"
        ), {"org": current.org_id})).mappings().all()
        eligible = []
        for member in members:
            try:
                _, permissions, _, _ = await effective_access(connection, current.org_id, member["id"])
            except AccessError:
                continue
            if "leads.assign" in permissions:
                eligible.append(dict(member))
        return {"data": eligible}


@router.get("/accounts")
async def list_accounts(request: Request, user: User, after: UUID | None = None, limit: int = Query(25, ge=1, le=100)):
    async with access(request, user, "marketplace.view") as (connection, current):
        rows = (await connection.execute(text(
            f"SELECT {SAFE_FIELDS} FROM crm.marketplace_accounts WHERE org_id=:org AND status<>'retired' "
            "AND (CAST(:after AS uuid) IS NULL OR id>:after) ORDER BY id LIMIT :limit"
        ), {"org": current.org_id, "after": after, "limit": limit + 1})).mappings().all()
        return {"data": [dict(row) for row in rows[:limit]], "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}


@router.post("/accounts", status_code=201)
async def create_account(body: AccountInput, request: Request, user: User):
    values = {key: value.get_secret_value().strip() for key, value in body.credentials.items()}
    validate_configuration(body.provider_code, body.config, values)
    identity = uuid4()
    async with access(request, user, "marketplace.manage") as (connection, current):
        await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:org),hashtext(:provider))"),
                                 {"org": str(current.org_id), "provider": body.provider_code})
        await validate_default_assignee(connection, current, body.default_assignee_membership_id)
        if provider(body.provider_code)["multiple_accounts"] is not True and await connection.scalar(text(
            "SELECT 1 FROM crm.marketplace_accounts WHERE org_id=:org AND provider_code=:provider AND status<>'retired' LIMIT 1"
        ), {"org": current.org_id, "provider": body.provider_code}):
            raise AccessError(409, "provider_account_limit_unverified")
        envelope = encrypt_credentials(request.app.state.configuration, values, str(current.org_id), str(identity), 1)
        await connection.execute(text(
            "INSERT INTO crm.marketplace_accounts(org_id,id,provider_code,name,config,credential_envelope,credential_fingerprint,created_by,default_assignee_membership_id) "
            "VALUES(:org,:id,:provider,:name,CAST(:config AS jsonb),CAST(:envelope AS jsonb),:fingerprint,:member,:assignee)"
        ), {"org": current.org_id, "id": identity, "provider": body.provider_code, "name": body.name,
            "config": json.dumps(body.config), "envelope": json.dumps(envelope), "member": current.member_id,
            "assignee": body.default_assignee_membership_id,
            "fingerprint": hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()})
        await audit(connection, current.org_id, current.member_id, "marketplace.account_created", identity)
        return await account(connection, current.org_id, identity)


@router.put("/accounts/{account_id}")
async def update_account(account_id: UUID, body: AccountInput, request: Request, user: User):
    if body.row_version is None:
        raise AccessError(422, "marketplace_version_required")
    async with access(request, user, "marketplace.manage") as (connection, current):
        existing = await account(connection, current.org_id, account_id)
        if existing["status"] == "retired" or body.provider_code != existing["provider_code"]:
            raise AccessError(409, "marketplace_account_unavailable")
        values = {key: value.get_secret_value().strip() for key, value in body.credentials.items()}
        validate_configuration(body.provider_code, body.config, values, replacing=True)
        await validate_default_assignee(connection, current, body.default_assignee_membership_id)
        parameters = {"org": current.org_id, "id": account_id, "name": body.name, "config": json.dumps(body.config), "version": body.row_version,
                      "assignee": body.default_assignee_membership_id}
        secret_assignment = ""
        if values:
            version = existing["credential_version"] + 1
            envelope = encrypt_credentials(request.app.state.configuration, values, str(current.org_id), str(account_id), version)
            parameters.update(envelope=json.dumps(envelope), fingerprint=hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest())
            secret_assignment = ",credential_envelope=CAST(:envelope AS jsonb),credential_fingerprint=:fingerprint,credential_version=credential_version+1"
        changed = await connection.scalar(text(
            "UPDATE crm.marketplace_accounts SET name=:name,config=CAST(:config AS jsonb),status='draft',verified_version=NULL,"
            "default_assignee_membership_id=:assignee,"
            f"safe_error_code=NULL,row_version=row_version+1,updated_at=now(){secret_assignment} "
            "WHERE org_id=:org AND id=:id AND row_version=:version RETURNING id"
        ), parameters)
        if not changed:
            raise AccessError(409, "marketplace_version_conflict")
        await connection.execute(text("UPDATE crm.marketplace_sync_runs SET state='cancelled',finished_at=now() WHERE org_id=:org AND account_id=:id AND state IN ('queued','running')"), parameters)
        await audit(connection, current.org_id, current.member_id, "marketplace.account_updated", account_id)
        return await account(connection, current.org_id, account_id)


@router.post("/accounts/{account_id}/{action}")
async def action_account(account_id: UUID, action: Literal["test", "sync", "activate", "pause", "retire"], body: AccountAction, request: Request, user: User):
    async with access(request, user, "marketplace.manage") as (connection, current):
        await connection.execute(text("SELECT id FROM crm.marketplace_accounts WHERE org_id=:org AND id=:id FOR UPDATE"), {"org": current.org_id, "id": account_id})
        existing = await account(connection, current.org_id, account_id)
        if existing["row_version"] != body.row_version:
            raise AccessError(409, "marketplace_version_conflict")
        if existing["status"] == "retired":
            raise AccessError(409, "marketplace_account_unavailable")
        if action in ("test", "sync", "activate") and not provider(existing["provider_code"])["adapter"]:
            raise AccessError(409, "provider_adapter_unavailable")
        if action in ("sync", "activate") and existing["verified_version"] != existing["credential_version"]:
            raise AccessError(409, "marketplace_test_required")
        if action == "sync" and existing["status"] != "active":
            raise AccessError(409, "marketplace_account_not_active")
        parameters = {"org": current.org_id, "id": account_id, "version": existing["credential_version"], "action": action}
        if action in ("test", "sync"):
            await connection.execute(text("INSERT INTO crm.marketplace_sync_runs(org_id,account_id,kind,credential_version) VALUES(:org,:id,:action,:version)"), parameters)
        else:
            parameters["status"] = {"activate": "active", "pause": "paused", "retire": "retired"}[action]
            await connection.execute(text("UPDATE crm.marketplace_accounts SET status=:status,row_version=row_version+1,updated_at=now() WHERE org_id=:org AND id=:id"), parameters)
            if action != "activate":
                await connection.execute(text("UPDATE crm.marketplace_sync_runs SET state='cancelled',finished_at=now() WHERE org_id=:org AND account_id=:id AND state IN ('queued','running')"), parameters)
        await audit(connection, current.org_id, current.member_id, f"marketplace.{action}", account_id)
        return await account(connection, current.org_id, account_id)


@router.get("/accounts/{account_id}/runs")
async def runs(account_id: UUID, request: Request, user: User):
    async with access(request, user, "marketplace.view") as (connection, current):
        await account(connection, current.org_id, account_id)
        rows = (await connection.execute(text("SELECT id,kind,state,fetched_count,accepted_count,safe_error_code,created_at,finished_at FROM crm.marketplace_sync_runs WHERE org_id=:org AND account_id=:id ORDER BY created_at DESC LIMIT 25"), {"org": current.org_id, "id": account_id})).mappings().all()
        return {"data": [dict(row) for row in rows]}