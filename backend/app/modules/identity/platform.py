import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from sqlalchemy import text

from ...core.database import tenant_transaction
from .dependencies import identity, public_throttle, validate_origin
from .schemas import Input
from .security import digest
from .service import AccessError, revoke_user_sessions

router = APIRouter(prefix="/platform", tags=["Platform administration"])

PLATFORM_SESSION_COOKIE = "crm_platform_session"
PLATFORM_CSRF_COOKIE = "crm_platform_csrf"


class PlatformLogin(Input):
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)


class OrganizationControl(Input):
    status: Literal["active", "suspended", "closed"]
    subscription_plan: str = Field(min_length=1, max_length=80)
    subscription_status: Literal["trialing", "active", "past_due", "expired", "canceled"]
    subscription_started_at: datetime | None = None
    subscription_ends_at: datetime | None = None
    export_access_until: datetime | None = None
    max_users: int = Field(ge=1, le=100000)

    @model_validator(mode="after")
    def valid_subscription_dates(self):
        for value in (
            self.subscription_started_at,
            self.subscription_ends_at,
            self.export_access_until,
        ):
            if value is not None and value.utcoffset() is None:
                raise ValueError("Subscription dates must include a timezone")
        if (
            self.subscription_started_at is not None
            and self.subscription_ends_at is not None
            and self.subscription_ends_at < self.subscription_started_at
        ):
            raise ValueError("Subscription end must be after its start")
        return self


class MembershipControl(Input):
    status: Literal["active", "disabled"]
    confirm_email: EmailStr

    @field_validator("confirm_email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class PasswordResetConfirmation(Input):
    confirm_email: EmailStr

    @field_validator("confirm_email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


@dataclass(frozen=True)
class PlatformOperator:
    user_id: UUID
    access_level: str


async def require_operator(
    request: Request,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> PlatformOperator:
    token = request.cookies.get(PLATFORM_SESSION_COOKIE)
    if not token:
        raise AccessError(401, "authentication_required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        validate_origin(request)
        expected_csrf = request.cookies.get(PLATFORM_CSRF_COOKIE)
        if not csrf_token or not expected_csrf or not secrets.compare_digest(csrf_token, expected_csrf):
            raise AccessError(403, "invalid_csrf")
    service = identity(request)
    async with service.engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT s.user_id,s.csrf_token_hash,o.access_level,u.full_name,u.email "
                        "FROM crm.platform_sessions s JOIN crm.platform_operators o ON o.user_id=s.user_id "
                        "JOIN crm.app_users u ON u.id=s.user_id WHERE s.token_hash=:token "
                        "AND s.revoked_at IS NULL AND s.expires_at>now()"
                    ),
                    {"token": digest(token)},
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise AccessError(401, "invalid_session")
    if csrf_token is not None and not secrets.compare_digest(
        bytes(row["csrf_token_hash"]), digest(csrf_token)
    ):
        raise AccessError(403, "invalid_csrf")
    return PlatformOperator(row["user_id"], row["access_level"])


Operator = Annotated[PlatformOperator, Depends(require_operator)]


async def require_administrator(operator: Operator) -> PlatformOperator:
    if operator.access_level != "administrator":
        raise AccessError(403, "platform_administrator_required")
    return operator


Administrator = Annotated[PlatformOperator, Depends(require_administrator)]


def set_platform_session(request: Request, response: Response, token: str, csrf: str) -> None:
    secure = request.app.state.configuration.app_environment == "production"
    response.set_cookie(
        PLATFORM_SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=request.app.state.configuration.session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        PLATFORM_CSRF_COOKIE,
        csrf,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=request.app.state.configuration.session_hours * 3600,
        path="/",
    )


async def audit_platform(
    connection,
    actor: UUID,
    action: str,
    organization: UUID | None,
    entity_type: str,
    entity_id: UUID | None,
    details: dict | None = None,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO crm.platform_audit_logs(actor_user_id,organization_id,action,entity_type,entity_id,details) "
            "VALUES(:actor,:org,:action,:type,:entity,CAST(:details AS jsonb))"
        ),
        {
            "actor": actor,
            "org": organization,
            "action": action,
            "type": entity_type,
            "entity": entity_id,
            "details": json.dumps(details or {}),
        },
    )


@router.post("/login")
async def platform_login(body: PlatformLogin, request: Request, response: Response):
    service = await public_throttle(request, "platform-login", str(body.email))
    async with service.engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT u.id,u.password_hash,o.access_level FROM crm.app_users u "
                        "LEFT JOIN crm.platform_operators o ON o.user_id=u.id WHERE u.email=:email"
                    ),
                    {"email": str(body.email).lower()},
                )
            )
            .mappings()
            .first()
        )
    valid = await service.passwords.verify(
        body.password.get_secret_value(), row["password_hash"] if row else None
    )
    if not valid or row is None or row["access_level"] is None:
        raise AccessError(401, "invalid_credentials")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    async with service.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO crm.platform_sessions(id,user_id,token_hash,csrf_token_hash,expires_at) "
                "VALUES(:id,:user,:token,:csrf,:expires)"
            ),
            {
                "id": uuid4(),
                "user": row["id"],
                "token": digest(token),
                "csrf": digest(csrf),
                "expires": datetime.now(timezone.utc)
                + timedelta(hours=request.app.state.configuration.session_hours),
            },
        )
        await audit_platform(
            connection, row["id"], "operator.login", None, "operator", row["id"]
        )
    set_platform_session(request, response, token, csrf)
    return {"status": "authenticated", "csrf_token": csrf}


@router.get("/me")
async def platform_me(request: Request, operator: Operator):
    token = request.cookies[PLATFORM_SESSION_COOKIE]
    async with identity(request).engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT u.email,u.full_name,o.access_level FROM crm.platform_sessions s "
                        "JOIN crm.app_users u ON u.id=s.user_id JOIN crm.platform_operators o ON o.user_id=u.id "
                        "WHERE s.token_hash=:token"
                    ),
                    {"token": digest(token)},
                )
            )
            .mappings()
            .one()
        )
    return {"user_id": operator.user_id, **dict(row)}


@router.post("/logout", status_code=204)
async def platform_logout(request: Request, response: Response, operator: Operator):
    token = request.cookies[PLATFORM_SESSION_COOKIE]
    async with identity(request).engine.begin() as connection:
        await connection.execute(
            text("UPDATE crm.platform_sessions SET revoked_at=now() WHERE token_hash=:token"),
            {"token": digest(token)},
        )
        await audit_platform(
            connection, operator.user_id, "operator.logout", None, "operator", operator.user_id
        )
    response.delete_cookie(PLATFORM_SESSION_COOKIE, path="/")
    response.delete_cookie(PLATFORM_CSRF_COOKIE, path="/")


async def organization_summary(engine, organization_id: UUID) -> dict:
    async with tenant_transaction(engine, organization_id) as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT o.id,o.slug,o.name,o.status,o.subscription_plan,o.subscription_status,"
                        "o.subscription_started_at,o.subscription_ends_at,o.export_access_until,o.max_users,o.created_at,"
                        "count(m.id) FILTER(WHERE m.status IN ('active','invited')) AS user_count "
                        "FROM crm.organizations o LEFT JOIN crm.organization_memberships m ON m.org_id=o.id "
                        "WHERE o.id=:org GROUP BY o.id"
                    ),
                    {"org": organization_id},
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise AccessError(404, "organization_not_found")
    return dict(row)


@router.get("/organizations")
async def organizations(
    request: Request,
    operator: Operator,
    limit: int = Query(50, ge=1, le=100),
    after: str | None = Query(None, max_length=63),
    search: str = Query("", max_length=100),
):
    engine = identity(request).engine
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT slug,organization_id FROM crm.organization_directory "
                    "WHERE (CAST(:after AS text) IS NULL OR slug>:after) AND (:search='' OR slug ILIKE :pattern) "
                    "ORDER BY slug LIMIT :limit"
                ),
                {"after": after, "search": search, "pattern": f"%{search}%", "limit": limit + 1},
            )
        ).mappings().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    data = [await organization_summary(engine, row["organization_id"]) for row in page_rows]
    return {"data": data, "next_cursor": page_rows[-1]["slug"] if has_more and page_rows else None}


@router.get("/organizations/{organization_id}")
async def get_organization(organization_id: UUID, request: Request, operator: Operator):
    return await organization_summary(identity(request).engine, organization_id)


@router.put("/organizations/{organization_id}")
async def update_organization(
    organization_id: UUID,
    body: OrganizationControl,
    request: Request,
    operator: Administrator,
):
    engine = identity(request).engine
    async with tenant_transaction(engine, organization_id) as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT status,subscription_plan,subscription_status,subscription_started_at,"
                        "subscription_ends_at,export_access_until,max_users FROM crm.organizations "
                        "WHERE id=:org FOR UPDATE"
                    ),
                    {"org": organization_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise AccessError(404, "organization_not_found")
        values = body.model_dump()
        await connection.execute(
            text(
                "UPDATE crm.organizations SET status=:status,subscription_plan=:plan,subscription_status=:subscription_status,"
                "subscription_started_at=:started,subscription_ends_at=:ends,export_access_until=:export_until,"
                "max_users=:max_users,updated_at=now() WHERE id=:org"
            ),
            {
                "org": organization_id,
                "status": values["status"],
                "plan": values["subscription_plan"],
                "subscription_status": values["subscription_status"],
                "started": values["subscription_started_at"],
                "ends": values["subscription_ends_at"],
                "export_until": values["export_access_until"],
                "max_users": values["max_users"],
            },
        )
        if values["status"] != "active":
            await connection.execute(
                text("UPDATE crm.auth_sessions SET revoked_at=COALESCE(revoked_at,now()) WHERE org_id=:org"),
                {"org": organization_id},
            )
        await audit_platform(
            connection,
            operator.user_id,
            "organization.updated",
            organization_id,
            "organization",
            organization_id,
            {
                "previous": {
                    "status": row["status"],
                    "subscription_plan": row["subscription_plan"],
                    "subscription_status": row["subscription_status"],
                    "subscription_started_at": row["subscription_started_at"].isoformat()
                    if row["subscription_started_at"]
                    else None,
                    "subscription_ends_at": row["subscription_ends_at"].isoformat()
                    if row["subscription_ends_at"]
                    else None,
                    "export_access_until": row["export_access_until"].isoformat()
                    if row["export_access_until"]
                    else None,
                    "max_users": row["max_users"],
                },
                "updated": {
                    "status": values["status"],
                    "subscription_plan": values["subscription_plan"],
                    "subscription_status": values["subscription_status"],
                    "subscription_started_at": values["subscription_started_at"].isoformat()
                    if values["subscription_started_at"]
                    else None,
                    "subscription_ends_at": values["subscription_ends_at"].isoformat()
                    if values["subscription_ends_at"]
                    else None,
                    "export_access_until": values["export_access_until"].isoformat()
                    if values["export_access_until"]
                    else None,
                    "max_users": values["max_users"],
                },
            },
        )
    return await organization_summary(engine, organization_id)


@router.get("/organizations/{organization_id}/users")
async def organization_users(
    organization_id: UUID,
    request: Request,
    operator: Operator,
    limit: int = Query(50, ge=1, le=100),
    after: UUID | None = None,
    search: str = Query("", max_length=100),
):
    async with tenant_transaction(identity(request).engine, organization_id) as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT m.id,m.user_id,m.display_name,m.status,m.is_owner,m.created_at,u.email "
                    "FROM crm.organization_memberships m JOIN crm.app_users u ON u.id=m.user_id "
                    "WHERE m.org_id=:org AND (CAST(:after AS uuid) IS NULL OR m.id>:after) "
                    "AND (:search='' OR m.display_name ILIKE :pattern OR u.email ILIKE :pattern) "
                    "ORDER BY m.id LIMIT :limit"
                ),
                {"org": organization_id, "after": after, "search": search, "pattern": f"%{search}%", "limit": limit + 1},
            )
        ).mappings().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return {
        "data": [dict(row) for row in page_rows],
        "next_cursor": page_rows[-1]["id"] if has_more and page_rows else None,
    }


@router.put("/organizations/{organization_id}/users/{membership_id}")
async def update_user_access(
    organization_id: UUID,
    membership_id: UUID,
    body: MembershipControl,
    request: Request,
    operator: Administrator,
):
    engine = identity(request).engine
    async with tenant_transaction(engine, organization_id) as connection:
        await connection.execute(
            text("SELECT id FROM crm.organizations WHERE id=:org FOR UPDATE"),
            {"org": organization_id},
        )
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT m.user_id,m.status,m.is_owner,u.email FROM crm.organization_memberships m "
                        "JOIN crm.app_users u ON u.id=m.user_id WHERE m.org_id=:org AND m.id=:member FOR UPDATE OF m"
                    ),
                    {"org": organization_id, "member": membership_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise AccessError(404, "membership_not_found")
        if str(row["email"]).lower() != str(body.confirm_email).lower():
            raise AccessError(422, "confirmation_email_mismatch")
        if row["status"] == "invited" and body.status == "active":
            raise AccessError(409, "invitation_acceptance_required")
        if body.status == "active" and row["status"] != "active":
            user_limit, active_and_invited = (
                await connection.execute(
                    text(
                        "SELECT o.max_users,(SELECT count(*) FROM crm.organization_memberships m "
                        "WHERE m.org_id=o.id AND m.status IN ('active','invited')) "
                        "FROM crm.organizations o WHERE o.id=:org"
                    ),
                    {"org": organization_id},
                )
            ).one()
            if active_and_invited >= user_limit:
                raise AccessError(409, "user_limit_reached")
        if row["is_owner"] and body.status == "disabled" and row["status"] == "active":
            active_owners = await connection.scalar(
                text("SELECT count(*) FROM crm.organization_memberships WHERE org_id=:org AND is_owner AND status='active'"),
                {"org": organization_id},
            )
            if active_owners <= 1:
                raise AccessError(409, "last_active_owner")
        await connection.execute(
            text(
                "UPDATE crm.organization_memberships SET status=:status,authz_version=authz_version+1,updated_at=now() "
                "WHERE org_id=:org AND id=:member"
            ),
            {"org": organization_id, "member": membership_id, "status": body.status},
        )
        if body.status == "disabled":
            await connection.execute(
                text("UPDATE crm.auth_sessions SET revoked_at=COALESCE(revoked_at,now()) WHERE org_id=:org AND membership_id=:member"),
                {"org": organization_id, "member": membership_id},
            )
        await audit_platform(
            connection,
            operator.user_id,
            "membership.access_updated",
            organization_id,
            "membership",
            membership_id,
            {"previous_status": row["status"], "status": body.status},
        )
    return {"membership_id": membership_id, "status": body.status}


@router.post("/organizations/{organization_id}/users/{membership_id}/generate-password")
async def generate_user_password(
    organization_id: UUID,
    membership_id: UUID,
    body: PasswordResetConfirmation,
    request: Request,
    operator: Administrator,
):
    service = identity(request)
    async with tenant_transaction(service.engine, organization_id) as connection:
        member = (
            (
                await connection.execute(
                    text(
                        "SELECT m.user_id,u.email FROM crm.organization_memberships m "
                        "JOIN crm.app_users u ON u.id=m.user_id WHERE m.org_id=:org AND m.id=:member"
                    ),
                    {"org": organization_id, "member": membership_id},
                )
            )
            .mappings()
            .first()
        )
        if member is None:
            raise AccessError(404, "membership_not_found")
        if str(member["email"]).lower() != str(body.confirm_email).lower():
            raise AccessError(422, "confirmation_email_mismatch")
        temporary_password = secrets.token_urlsafe(24)
        password_hash = await service.passwords.hash(temporary_password)
        await connection.execute(
            text(
                "UPDATE crm.app_users SET password_hash=:hash,password_change_required=true,updated_at=now() "
                "WHERE id=:user"
            ),
            {"hash": password_hash, "user": member["user_id"]},
        )
        await audit_platform(
            connection,
            operator.user_id,
            "user.password_generated",
            organization_id,
            "user",
            member["user_id"],
            {"membership_id": str(membership_id)},
        )
    await revoke_user_sessions(service.engine, member["user_id"])
    return {"temporary_password": temporary_password, "password_change_required": True}


@router.get("/audit")
async def platform_audit_history(
    request: Request,
    operator: Operator,
    limit: int = Query(50, ge=1, le=100),
    after: UUID | None = None,
    organization_id: UUID | None = None,
):
    async with identity(request).engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT a.id,a.actor_user_id,u.email AS actor_email,a.organization_id,a.action,"
                    "a.entity_type,a.entity_id,a.details,a.occurred_at FROM crm.platform_audit_logs a "
                    "JOIN crm.app_users u ON u.id=a.actor_user_id "
                    "WHERE (CAST(:after AS uuid) IS NULL OR (a.occurred_at,a.id)<(SELECT occurred_at,id FROM crm.platform_audit_logs WHERE id=:after)) "
                    "AND (CAST(:org AS uuid) IS NULL OR a.organization_id=:org) ORDER BY a.occurred_at DESC,a.id DESC LIMIT :limit"
                ),
                {"after": after, "org": organization_id, "limit": limit + 1},
            )
        ).mappings().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return {
        "data": [dict(row) for row in page_rows],
        "next_cursor": page_rows[-1]["id"] if has_more and page_rows else None,
    }