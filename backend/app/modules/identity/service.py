import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ...core.database import tenant_transaction
from .permissions import SCOPE_RANK
from .security import PasswordService, digest, opaque_token, parse_token
from .schemas import Login, Onboard

logger = logging.getLogger(__name__)


class AccessError(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Principal:
    org_id: UUID
    member_id: UUID
    session_id: UUID
    user_id: UUID
    is_owner: bool
    permissions: frozenset[str]
    data_scope: str
    access_mode: str = "full"
    password_change_required: bool = False


async def audit(
    connection: AsyncConnection,
    org: UUID,
    actor: UUID | None,
    action: str,
    entity: UUID | None,
) -> None:
    logger.info(
        "audit action=%s org_id=%s actor=%s entity_id=%s", action, org, actor, entity
    )
    await connection.execute(
        text(
            "INSERT INTO crm.audit_logs(org_id,actor_membership_id,request_id,action,entity_type,entity_id) "
            "VALUES(:org,:actor,:request,:action,'access',:entity)"
        ),
        {
            "org": org,
            "actor": actor,
            "request": uuid4(),
            "action": action,
            "entity": entity,
        },
    )


async def effective_access(
    connection: AsyncConnection, org: UUID, member: UUID
) -> tuple[bool, frozenset[str], str, UUID]:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT m.is_owner,m.visibility_override,m.user_id FROM crm.organization_memberships m "
                    "JOIN crm.organizations o ON o.id=m.org_id "
                    "WHERE m.org_id=:org AND m.id=:member AND m.status='active' AND o.status='active'"
                ),
                {"org": org, "member": member},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise AccessError(401, "membership_inactive")
    if row["is_owner"]:
        codes = frozenset(
            (
                await connection.execute(text("SELECT code FROM crm.permissions"))
            ).scalars()
        )
        return True, codes, "all", row["user_id"]
    rows = (
        (
            await connection.execute(
                text(
                    "SELECT r.data_scope,p.permission_code FROM crm.membership_roles mr "
                    "JOIN crm.roles r ON r.org_id=mr.org_id AND r.id=mr.role_id AND r.is_active "
                    "LEFT JOIN crm.role_permissions p ON p.org_id=r.org_id AND p.role_id=r.id "
                    "WHERE mr.org_id=:org AND mr.membership_id=:member"
                ),
                {"org": org, "member": member},
            )
        )
        .mappings()
        .all()
    )
    codes = {item["permission_code"] for item in rows if item["permission_code"]}
    scope = max(
        (item["data_scope"] for item in rows),
        key=lambda value: SCOPE_RANK[value],
        default="own",
    )
    overrides = (
        (
            await connection.execute(
                text(
                    "SELECT x.permission_code,x.allowed,p.is_delegable "
                    "FROM crm.membership_permission_overrides x JOIN crm.permissions p ON p.code=x.permission_code "
                    "WHERE x.org_id=:org AND x.membership_id=:member"
                ),
                {"org": org, "member": member},
            )
        )
        .mappings()
        .all()
    )
    for override in overrides:
        if override["allowed"] and override["is_delegable"]:
            codes.add(override["permission_code"])
        else:
            codes.discard(override["permission_code"])
    return False, frozenset(codes), row["visibility_override"] or scope, row["user_id"]


async def organization_access_mode(connection: AsyncConnection, org: UUID) -> str:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT status,subscription_status,subscription_ends_at,export_access_until "
                    "FROM crm.organizations WHERE id=:org"
                ),
                {"org": org},
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["status"] != "active":
        raise AccessError(401, "membership_inactive")
    now = datetime.now(timezone.utc)
    subscription_ended = row["subscription_status"] == "expired" or (
        row["subscription_ends_at"] is not None
        and row["subscription_ends_at"] <= now
    ) or (row["subscription_status"] == "canceled" and row["subscription_ends_at"] is None)
    if not subscription_ended:
        return "full"
    if (
        row["export_access_until"] is not None
        and row["export_access_until"] > now
    ):
        return "export_only"
    raise AccessError(403, "subscription_access_ended")


async def revoke_user_sessions(
    engine: AsyncEngine, user_id: UUID, except_session_id: UUID | None = None
) -> None:
    async with engine.connect() as connection:
        organizations = list(
            (
                await connection.execute(
                    text("SELECT organization_id FROM crm.organization_directory")
                )
            ).scalars()
        )
    for org in organizations:
        async with tenant_transaction(engine, org) as connection:
            await connection.execute(
                text(
                    "UPDATE crm.auth_sessions s SET revoked_at=COALESCE(s.revoked_at,now()) "
                    "FROM crm.organization_memberships m WHERE s.org_id=:org AND m.org_id=s.org_id "
                    "AND m.id=s.membership_id AND m.user_id=:user "
                    "AND (CAST(:except_session AS uuid) IS NULL OR s.id<>:except_session)"
                ),
                {"org": org, "user": user_id, "except_session": except_session_id},
            )


async def authorize_mutation(
    connection: AsyncConnection, principal: Principal, permission: str
) -> Principal:
    # Access writers share this lock; revocation cannot race another privileged mutation.
    await connection.execute(
        text("SELECT id FROM crm.organizations WHERE id=:org FOR UPDATE"),
        {"org": principal.org_id},
    )
    access_mode = await organization_access_mode(connection, principal.org_id)
    if access_mode != "full":
        raise AccessError(403, "export_only_access")
    owner, codes, scope, user = await effective_access(
        connection, principal.org_id, principal.member_id
    )
    if permission not in codes:
        raise AccessError(403, "permission_denied")
    return Principal(
        principal.org_id,
        principal.member_id,
        principal.session_id,
        user,
        owner,
        codes,
        scope,
        access_mode,
        principal.password_change_required,
    )


async def validate_permissions(
    connection: AsyncConnection, principal: Principal, codes: list[str], scope: str
) -> None:
    catalog = set(
        (
            await connection.execute(
                text("SELECT code FROM crm.permissions WHERE is_delegable")
            )
        ).scalars()
    )
    if not set(codes) <= catalog:
        raise AccessError(422, "unknown_or_non_delegable_permission")
    if not principal.is_owner and (
        not set(codes) <= principal.permissions
        or SCOPE_RANK[scope] > SCOPE_RANK[principal.data_scope]
    ):
        raise AccessError(403, "grant_exceeds_access")


async def validate_roles(
    connection: AsyncConnection,
    principal: Principal,
    role_ids: list[UUID],
    scope: str | None,
) -> None:
    for role_id in set(role_ids):
        role = (
            (
                await connection.execute(
                    text(
                        "SELECT data_scope FROM crm.roles WHERE org_id=:org AND id=:id AND is_active"
                    ),
                    {"org": principal.org_id, "id": role_id},
                )
            )
            .mappings()
            .first()
        )
        if role is None:
            raise AccessError(422, "invalid_role")
        permissions = list(
            (
                await connection.execute(
                    text(
                        "SELECT permission_code FROM crm.role_permissions WHERE org_id=:org AND role_id=:id"
                    ),
                    {"org": principal.org_id, "id": role_id},
                )
            ).scalars()
        )
        await validate_permissions(
            connection, principal, permissions, role["data_scope"]
        )
    if scope is not None:
        await validate_permissions(connection, principal, [], scope)


class IdentityService:
    def __init__(self, engine: AsyncEngine, session_hours: int) -> None:
        self.engine = engine
        self.session_hours = session_hours
        self.passwords = PasswordService()

    async def throttle(self, key: str, limit: int) -> None:
        async with self.engine.begin() as connection:
            attempts = await connection.scalar(
                text(
                    "INSERT INTO crm.auth_rate_limits(bucket_key,attempts,window_end) "
                    "VALUES(:key,1,now()+interval '15 minutes') "
                    "ON CONFLICT(bucket_key) DO UPDATE SET "
                    "attempts=CASE WHEN crm.auth_rate_limits.window_end<=now() THEN 1 ELSE crm.auth_rate_limits.attempts+1 END, "
                    "window_end=CASE WHEN crm.auth_rate_limits.window_end<=now() THEN now()+interval '15 minutes' ELSE crm.auth_rate_limits.window_end END "
                    "RETURNING attempts"
                ),
                {"key": digest(key)},
            )
        if attempts is None or attempts > limit:
            raise AccessError(429, "too_many_attempts")

    async def issue_session(
        self, connection: AsyncConnection, org: UUID, member: UUID
    ) -> tuple[str, str]:
        session_id = uuid4()
        token, csrf = opaque_token(org, session_id), secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=self.session_hours)
        await connection.execute(
            text(
                "INSERT INTO crm.auth_sessions(org_id,id,membership_id,csrf_token_hash,expires_at) "
                "VALUES(:org,:id,:member,:csrf,:expires)"
            ),
            {
                "org": org,
                "id": session_id,
                "member": member,
                "csrf": digest(csrf),
                "expires": expires,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO crm.session_refresh_tokens(org_id,session_id,token_hash,expires_at) "
                "VALUES(:org,:session,:hash,:expires)"
            ),
            {
                "org": org,
                "session": session_id,
                "hash": digest(token),
                "expires": expires,
            },
        )
        return token, csrf

    async def onboard(self, body: Onboard) -> tuple[UUID, tuple[str, str]]:
        new_hash = await self.passwords.hash(body.password.get_secret_value())
        org, member = uuid4(), uuid4()
        async with tenant_transaction(self.engine, org) as connection:
            # Authenticate existing identities; never overwrite their passwords during signup.
            user = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,password_hash FROM crm.app_users WHERE email=:email FOR UPDATE"
                        ),
                        {"email": str(body.email)},
                    )
                )
                .mappings()
                .first()
            )
            if user is not None:
                is_platform_operator = await connection.scalar(
                    text("SELECT 1 FROM crm.platform_operators WHERE user_id=:user"),
                    {"user": user["id"]},
                )
                if is_platform_operator:
                    raise AccessError(409, "identity_unavailable")
                if not await self.passwords.verify(
                    body.password.get_secret_value(), user["password_hash"]
                ):
                    raise AccessError(409, "identity_unavailable")
                user_id = user["id"]
            else:
                user_id = uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO crm.app_users(id,email,full_name,password_hash) VALUES(:id,:email,:name,:hash)"
                    ),
                    {
                        "id": user_id,
                        "email": str(body.email),
                        "name": body.full_name,
                        "hash": new_hash,
                    },
                )
            await connection.execute(
                text(
                    "INSERT INTO crm.organizations(id,slug,name,timezone) VALUES(:id,:slug,:name,:timezone)"
                ),
                {
                    "id": org,
                    "slug": body.organization_slug,
                    "name": body.organization_name,
                    "timezone": body.timezone,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO crm.organization_memberships(org_id,id,user_id,display_name,status,is_owner) "
                    "VALUES(:org,:id,:user,:name,'active',true)"
                ),
                {"org": org, "id": member, "user": user_id, "name": body.full_name},
            )
            for position, (name, category, color) in enumerate(
                (
                    ("New", "new", "#2563eb"),
                    ("Pending", "pending", "#d97706"),
                    ("Contacted", "working", "#0891b2"),
                    ("Qualified", "working", "#7c3aed"),
                    ("Interested", "working", "#db2777"),
                    ("Not Interested", "lost", "#c2410c"),
                    ("Converted", "won", "#16a34a"),
                    ("Lost", "lost", "#dc2626"),
                )
            ):
                await connection.execute(
                    text(
                        "INSERT INTO crm.lead_statuses(org_id,name,category,color,position,is_default,is_system) "
                        "VALUES(:org,:name,:category,:color,:position,:default,true)"
                    ),
                    {
                        "org": org,
                        "name": name,
                        "category": category,
                        "color": color,
                        "position": position,
                        "default": position == 0,
                    },
                )
            await connection.execute(
                text("INSERT INTO crm.organization_settings(org_id) VALUES(:org)"),
                {"org": org},
            )
            await connection.execute(
                text("UPDATE crm.organizations SET status='active' WHERE id=:org"),
                {"org": org},
            )
            await audit(connection, org, member, "organization.created", org)
            tokens = await self.issue_session(connection, org, member)
        return org, tokens

    async def login(self, body: Login) -> tuple[str, str]:
        async with self.engine.connect() as connection:
            user = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,password_hash FROM crm.app_users WHERE email=:email"
                        ),
                        {"email": str(body.email)},
                    )
                )
                .mappings()
                .first()
            )
            org = await connection.scalar(
                text(
                    "SELECT organization_id FROM crm.organization_directory WHERE slug=:slug"
                ),
                {"slug": body.organization_slug},
            )
        valid = await self.passwords.verify(
            body.password.get_secret_value(), user["password_hash"] if user else None
        )
        if not valid or user is None or org is None:
            raise AccessError(401, "invalid_credentials")
        async with tenant_transaction(self.engine, org) as connection:
            await connection.execute(
                text("SELECT id FROM crm.organizations WHERE id=:org FOR UPDATE"),
                {"org": org},
            )
            latest_password_hash = await connection.scalar(
                text("SELECT password_hash FROM crm.app_users WHERE id=:user FOR UPDATE"),
                {"user": user["id"]},
            )
            if latest_password_hash != user["password_hash"] or not await self.passwords.verify(
                body.password.get_secret_value(), latest_password_hash
            ):
                raise AccessError(401, "invalid_credentials")
            member = await connection.scalar(
                text(
                    "SELECT id FROM crm.organization_memberships WHERE org_id=:org AND user_id=:user AND status='active'"
                ),
                {"org": org, "user": user["id"]},
            )
            if member is None:
                raise AccessError(401, "invalid_credentials")
            await effective_access(connection, org, member)
            await organization_access_mode(connection, org)
            if await connection.scalar(
                text(
                    "SELECT require_mfa FROM crm.organization_settings WHERE org_id=:org"
                ),
                {"org": org},
            ):
                raise AccessError(403, "mfa_required_not_available")
            await audit(connection, org, member, "session.created", member)
            return await self.issue_session(connection, org, member)

    async def authenticate(self, token: str, csrf: str | None = None) -> Principal:
        try:
            org, session = parse_token(token)
        except ValueError:
            raise AccessError(401, "invalid_session") from None
        async with tenant_transaction(self.engine, org) as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT s.membership_id,s.csrf_token_hash FROM crm.auth_sessions s "
                            "JOIN crm.session_refresh_tokens t ON t.org_id=s.org_id AND t.session_id=s.id "
                            "WHERE s.org_id=:org AND s.id=:session AND t.token_hash=:hash "
                            "AND t.consumed_at IS NULL AND t.revoked_at IS NULL AND t.expires_at>now() "
                            "AND s.revoked_at IS NULL AND s.expires_at>now()"
                        ),
                        {"org": org, "session": session, "hash": digest(token)},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise AccessError(401, "invalid_session")
            if csrf is not None and not secrets.compare_digest(
                bytes(row["csrf_token_hash"]), digest(csrf)
            ):
                raise AccessError(403, "invalid_csrf")
            owner, codes, scope, user = await effective_access(
                connection, org, row["membership_id"]
            )
            access_mode = await organization_access_mode(connection, org)
            if await connection.scalar(
                text(
                    "SELECT require_mfa FROM crm.organization_settings WHERE org_id=:org"
                ),
                {"org": org},
            ):
                raise AccessError(403, "mfa_required_not_available")
            password_change_required = await connection.scalar(
                text("SELECT password_change_required FROM crm.app_users WHERE id=:user"),
                {"user": user},
            )
            return Principal(
                org,
                row["membership_id"],
                session,
                user,
                owner,
                codes,
                scope,
                access_mode,
                bool(password_change_required),
            )

    async def refresh(self, token: str, csrf: str) -> tuple[str, str]:
        try:
            org, session = parse_token(token)
        except ValueError:
            raise AccessError(401, "invalid_session") from None
        replay = False
        tokens = None
        async with tenant_transaction(self.engine, org) as connection:
            await connection.execute(
                text("SELECT id FROM crm.organizations WHERE id=:org FOR UPDATE"),
                {"org": org},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT s.membership_id,s.csrf_token_hash,s.revoked_at,s.expires_at,t.consumed_at "
                            "FROM crm.auth_sessions s JOIN crm.session_refresh_tokens t ON t.org_id=s.org_id AND t.session_id=s.id "
                            "WHERE s.org_id=:org AND s.id=:session AND t.token_hash=:hash FOR UPDATE OF s,t"
                        ),
                        {"org": org, "session": session, "hash": digest(token)},
                    )
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["revoked_at"]
                or row["expires_at"] <= datetime.now(timezone.utc)
            ):
                raise AccessError(401, "invalid_session")
            if not secrets.compare_digest(bytes(row["csrf_token_hash"]), digest(csrf)):
                raise AccessError(403, "invalid_csrf")
            await effective_access(connection, org, row["membership_id"])
            await organization_access_mode(connection, org)
            if await connection.scalar(
                text(
                    "SELECT require_mfa FROM crm.organization_settings WHERE org_id=:org"
                ),
                {"org": org},
            ):
                raise AccessError(403, "mfa_required_not_available")
            if row["consumed_at"] is not None:
                replay = True
                await connection.execute(
                    text(
                        "UPDATE crm.auth_sessions SET revoked_at=now() WHERE org_id=:org AND id=:session"
                    ),
                    {"org": org, "session": session},
                )
                await audit(
                    connection,
                    org,
                    row["membership_id"],
                    "session.reuse_detected",
                    session,
                )
            else:
                await connection.execute(
                    text(
                        "UPDATE crm.session_refresh_tokens SET consumed_at=now() WHERE org_id=:org AND token_hash=:hash"
                    ),
                    {"org": org, "hash": digest(token)},
                )
                # Keep a stable session CSRF token; retain consumed hashes to detect replay.
                new_token = opaque_token(org, session)
                await connection.execute(
                    text(
                        "INSERT INTO crm.session_refresh_tokens(org_id,session_id,token_hash,expires_at) "
                        "VALUES(:org,:session,:hash,:expires)"
                    ),
                    {
                        "org": org,
                        "session": session,
                        "hash": digest(new_token),
                        "expires": row["expires_at"],
                    },
                )
                tokens = new_token, csrf
        if replay or tokens is None:
            raise AccessError(401, "session_reuse_detected")
        return tokens

    async def logout(self, principal: Principal) -> None:
        async with tenant_transaction(self.engine, principal.org_id) as connection:
            await connection.execute(
                text(
                    "UPDATE crm.auth_sessions SET revoked_at=now() WHERE org_id=:org AND id=:id"
                ),
                {"org": principal.org_id, "id": principal.session_id},
            )
            await audit(
                connection,
                principal.org_id,
                principal.member_id,
                "session.revoked",
                principal.session_id,
            )

    async def change_password(
        self, principal: Principal, current_password: str, new_password: str
    ) -> None:
        new_hash = await self.passwords.hash(new_password)
        async with self.engine.begin() as connection:
            password_hash = await connection.scalar(
                text("SELECT password_hash FROM crm.app_users WHERE id=:user FOR UPDATE"),
                {"user": principal.user_id},
            )
            if not await self.passwords.verify(current_password, password_hash):
                raise AccessError(403, "invalid_current_password")
            await connection.execute(
                text(
                    "UPDATE crm.app_users SET password_hash=:hash,password_change_required=false,updated_at=now() "
                    "WHERE id=:user"
                ),
                {"hash": new_hash, "user": principal.user_id},
            )
        await revoke_user_sessions(self.engine, principal.user_id, principal.session_id)
