from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ...core.database import tenant_transaction
from .schemas import AcceptInvite, InviteInput, MembershipUpdate, RoleInput
from .security import digest, invitation_token, parse_token
from .service import (
    AccessError,
    IdentityService,
    Principal,
    audit,
    authorize_mutation,
    organization_access_mode,
    validate_permissions,
    validate_roles,
)


async def bump_access(connection: AsyncConnection, org: UUID) -> None:
    await connection.execute(
        text(
            "UPDATE crm.organizations SET authz_version=authz_version+1 WHERE id=:org"
        ),
        {"org": org},
    )


async def validate_landing_page(
    connection: AsyncConnection,
    org: UUID,
    body: InviteInput | MembershipUpdate,
    owner: bool = False,
) -> None:
    if body.landing_page in (None, "/account") or owner:
        return
    codes = set(
        (
            await connection.execute(
                text(
                    "SELECT p.permission_code FROM crm.roles r JOIN crm.role_permissions p "
                    "ON p.org_id=r.org_id AND p.role_id=r.id WHERE r.org_id=:org AND r.is_active "
                    "AND r.id=ANY(:roles)"
                ),
                {"org": org, "roles": body.role_ids},
            )
        ).scalars()
    )
    if isinstance(body, MembershipUpdate):
        for code, allowed in body.permission_overrides.items():
            if allowed:
                codes.add(code)
            else:
                codes.discard(code)
    required = {
        "/": {"dashboard.view"},
        "/leads": {"leads.view"},
        "/users": {"users.view", "roles.view"},
        "/settings": {"settings.view"},
        "/marketplace": {"marketplace.view"},
    }
    if not codes & required[body.landing_page]:
        raise AccessError(422, "landing_page_not_allowed")


async def save_role(
    engine: AsyncEngine, principal: Principal, body: RoleInput, role_id: UUID | None
) -> UUID:
    async with tenant_transaction(engine, principal.org_id) as connection:
        principal = await authorize_mutation(connection, principal, "roles.manage")
        await validate_permissions(
            connection, principal, body.permissions, body.data_scope
        )
        if body.reports_to_role_id is not None:
            ancestors = list(
                (
                    await connection.execute(
                        text(
                            "WITH RECURSIVE parents AS ("
                            "SELECT id,reports_to_role_id FROM crm.roles WHERE org_id=:org AND id=:parent "
                            "UNION SELECT r.id,r.reports_to_role_id FROM crm.roles r JOIN parents p "
                            "ON r.id=p.reports_to_role_id WHERE r.org_id=:org) SELECT id FROM parents"
                        ),
                        {"org": principal.org_id, "parent": body.reports_to_role_id},
                    )
                ).scalars()
            )
            if not ancestors:
                raise AccessError(422, "invalid_reporting_role")
            if role_id in ancestors:
                raise AccessError(422, "role_hierarchy_cycle")
        if role_id is not None:
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT data_scope FROM crm.roles WHERE org_id=:org AND id=:id"
                        ),
                        {"org": principal.org_id, "id": role_id},
                    )
                )
                .mappings()
                .first()
            )
            if existing is None:
                raise AccessError(404, "role_not_found")
            old_codes = list(
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
                connection, principal, old_codes, existing["data_scope"]
            )
            await connection.execute(
                text(
                    "UPDATE crm.roles SET name=:name,description=:description,data_scope=:scope,is_active=:active,reports_to_role_id=:parent,updated_at=now() "
                    "WHERE org_id=:org AND id=:id"
                ),
                {
                    "org": principal.org_id,
                    "id": role_id,
                    "name": body.name,
                    "description": body.description,
                    "scope": body.data_scope,
                    "active": body.is_active,
                    "parent": body.reports_to_role_id,
                },
            )
            await connection.execute(
                text(
                    "DELETE FROM crm.role_permissions WHERE org_id=:org AND role_id=:id"
                ),
                {"org": principal.org_id, "id": role_id},
            )
        else:
            role_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO crm.roles(org_id,id,name,description,data_scope,is_active,reports_to_role_id) "
                    "VALUES(:org,:id,:name,:description,:scope,:active,:parent)"
                ),
                {
                    "org": principal.org_id,
                    "id": role_id,
                    "name": body.name,
                    "description": body.description,
                    "scope": body.data_scope,
                    "active": body.is_active,
                    "parent": body.reports_to_role_id,
                },
            )
        for code in sorted(set(body.permissions)):
            await connection.execute(
                text(
                    "INSERT INTO crm.role_permissions(org_id,role_id,permission_code) VALUES(:org,:id,:code)"
                ),
                {"org": principal.org_id, "id": role_id, "code": code},
            )
        await bump_access(connection, principal.org_id)
        await audit(
            connection, principal.org_id, principal.member_id, "role.saved", role_id
        )
    return role_id


async def update_membership(
    engine: AsyncEngine,
    principal: Principal,
    member: UUID,
    body: MembershipUpdate,
    *,
    deactivate_only: bool = False,
) -> None:
    async with tenant_transaction(engine, principal.org_id) as connection:
        principal = await authorize_mutation(connection, principal, "users.manage")
        existing = (
            (
                await connection.execute(
                    text(
                        "SELECT is_owner,status,EXISTS(SELECT 1 FROM crm.auth_sessions s "
                        "WHERE s.org_id=m.org_id AND s.membership_id=m.id) AS has_session "
                        "FROM crm.organization_memberships m WHERE org_id=:org AND id=:id"
                    ),
                    {"org": principal.org_id, "id": member},
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            raise AccessError(404, "membership_not_found")
        if body.status == "active" and (
            existing["status"] == "invited"
            or existing["status"] == "disabled"
            and not existing["has_session"]
        ):
            raise AccessError(409, "invitation_acceptance_required")
        if body.status == "active" and existing["status"] != "active":
            user_limit, active_and_invited = (
                await connection.execute(
                    text(
                        "SELECT o.max_users,(SELECT count(*) FROM crm.organization_memberships m "
                        "WHERE m.org_id=o.id AND m.status IN ('active','invited')) "
                        "FROM crm.organizations o WHERE o.id=:org"
                    ),
                    {"org": principal.org_id},
                )
            ).one()
            if active_and_invited >= user_limit:
                raise AccessError(409, "user_limit_reached")
        if not principal.is_owner and (
            existing["is_owner"]
            or body.is_owner is not None
            or member == principal.member_id
        ):
            raise AccessError(403, "owner_required")
        # Non-Owners cannot edit a target currently above their grant ceiling.
        if not principal.is_owner:
            current_roles = list(
                (
                    await connection.execute(
                        text(
                            "SELECT role_id FROM crm.membership_roles WHERE org_id=:org AND membership_id=:id"
                        ),
                        {"org": principal.org_id, "id": member},
                    )
                ).scalars()
            )
            await validate_roles(connection, principal, current_roles, None)
            existing_grants = list(
                (
                    await connection.execute(
                        text(
                            "SELECT permission_code FROM crm.membership_permission_overrides "
                            "WHERE org_id=:org AND membership_id=:id AND allowed"
                        ),
                        {"org": principal.org_id, "id": member},
                    )
                ).scalars()
            )
            await validate_permissions(connection, principal, existing_grants, "own")
            current_scope = await connection.scalar(
                text(
                    "SELECT visibility_override FROM crm.organization_memberships WHERE org_id=:org AND id=:id"
                ),
                {"org": principal.org_id, "id": member},
            )
            await validate_permissions(
                connection, principal, [], current_scope or "own"
            )
        if deactivate_only:
            await connection.execute(
                text(
                    "UPDATE crm.organization_memberships SET status='disabled',"
                    "authz_version=authz_version+1,updated_at=now() WHERE org_id=:org AND id=:id"
                ),
                {"org": principal.org_id, "id": member},
            )
            await connection.execute(
                text(
                    "UPDATE crm.auth_sessions SET revoked_at=now() WHERE org_id=:org AND membership_id=:id"
                ),
                {"org": principal.org_id, "id": member},
            )
            await bump_access(connection, principal.org_id)
            await audit(
                connection,
                principal.org_id,
                principal.member_id,
                "membership.deactivated",
                member,
            )
            return
        await validate_roles(
            connection, principal, body.role_ids, body.visibility_override
        )
        await validate_permissions(
            connection,
            principal,
            list(body.permission_overrides),
            body.visibility_override or "own",
        )
        await validate_landing_page(
            connection,
            principal.org_id,
            body,
            body.is_owner if body.is_owner is not None else existing["is_owner"],
        )
        await connection.execute(
            text(
                "UPDATE crm.organization_memberships SET status=:status,visibility_override=:scope,"
                "is_owner=COALESCE(:owner,is_owner),display_name=COALESCE(:name,display_name),landing_page=:landing,authz_version=authz_version+1,updated_at=now() "
                "WHERE org_id=:org AND id=:id"
            ),
            {
                "org": principal.org_id,
                "id": member,
                "status": body.status,
                "scope": body.visibility_override,
                "owner": body.is_owner,
                "landing": body.landing_page,
                "name": body.display_name,
            },
        )
        await connection.execute(
            text(
                "DELETE FROM crm.membership_roles WHERE org_id=:org AND membership_id=:id"
            ),
            {"org": principal.org_id, "id": member},
        )
        for role in set(body.role_ids):
            await connection.execute(
                text(
                    "INSERT INTO crm.membership_roles(org_id,membership_id,role_id) VALUES(:org,:id,:role)"
                ),
                {"org": principal.org_id, "id": member, "role": role},
            )
        await connection.execute(
            text(
                "DELETE FROM crm.membership_permission_overrides WHERE org_id=:org AND membership_id=:id"
            ),
            {"org": principal.org_id, "id": member},
        )
        for code, allowed in body.permission_overrides.items():
            await connection.execute(
                text(
                    "INSERT INTO crm.membership_permission_overrides(org_id,membership_id,permission_code,allowed,changed_by) "
                    "VALUES(:org,:id,:code,:allowed,:actor)"
                ),
                {
                    "org": principal.org_id,
                    "id": member,
                    "code": code,
                    "allowed": allowed,
                    "actor": principal.member_id,
                },
            )
        if body.status == "disabled":
            await connection.execute(
                text(
                    "UPDATE crm.auth_sessions SET revoked_at=now() WHERE org_id=:org AND membership_id=:id"
                ),
                {"org": principal.org_id, "id": member},
            )
        await bump_access(connection, principal.org_id)
        await audit(
            connection,
            principal.org_id,
            principal.member_id,
            "membership.updated",
            member,
        )


async def invite_member(
    service: IdentityService, principal: Principal, body: InviteInput, key: bytes
) -> dict:
    # Global identity writes stay in the restricted identity pool, never the business pool.
    async with tenant_transaction(service.engine, principal.org_id) as connection:
        principal = await authorize_mutation(connection, principal, "users.manage")
        await validate_roles(
            connection, principal, body.role_ids, body.visibility_override
        )
        await validate_landing_page(connection, principal.org_id, body)
        user = await connection.scalar(
            text(
                "INSERT INTO crm.app_users(email,full_name) VALUES(:email,:name) "
                "ON CONFLICT(email) DO UPDATE SET email=EXCLUDED.email RETURNING id"
            ),
            {"email": str(body.email), "name": body.display_name},
        )
        if await connection.scalar(
            text("SELECT 1 FROM crm.platform_operators WHERE user_id=:user"),
            {"user": user},
        ):
            raise AccessError(409, "identity_unavailable")
        member = (
            (
                await connection.execute(
                    text(
                        "SELECT id,status FROM crm.organization_memberships WHERE org_id=:org AND user_id=:user"
                    ),
                    {"org": principal.org_id, "user": user},
                )
            )
            .mappings()
            .first()
        )
        if member is not None:
            if member["status"] != "invited":
                raise AccessError(409, "membership_already_exists")
            member_id = member["id"]
            old_roles = list(
                (
                    await connection.execute(
                        text(
                            "SELECT role_id FROM crm.membership_roles WHERE org_id=:org AND membership_id=:member"
                        ),
                        {"org": principal.org_id, "member": member_id},
                    )
                ).scalars()
            )
            await validate_roles(connection, principal, old_roles, None)
            await connection.execute(
                text(
                    "UPDATE crm.organization_invitations SET consumed_at=now() "
                    "WHERE org_id=:org AND membership_id=:member AND consumed_at IS NULL"
                ),
                {"org": principal.org_id, "member": member_id},
            )
            await connection.execute(
                text(
                    "UPDATE crm.organization_memberships SET display_name=:name,visibility_override=:scope,landing_page=:landing "
                    "WHERE org_id=:org AND id=:member"
                ),
                {
                    "org": principal.org_id,
                    "member": member_id,
                    "name": body.display_name,
                    "scope": body.visibility_override,
                    "landing": body.landing_page,
                },
            )
        else:
            limit, current_users = (
                await connection.execute(
                    text(
                        "SELECT o.max_users,(SELECT count(*) FROM crm.organization_memberships m "
                        "WHERE m.org_id=o.id AND m.status IN ('active','invited')) "
                        "FROM crm.organizations o WHERE o.id=:org"
                    ),
                    {"org": principal.org_id},
                )
            ).one()
            if current_users >= limit:
                raise AccessError(409, "user_limit_reached")
            member_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO crm.organization_memberships(org_id,id,user_id,display_name,visibility_override,landing_page) "
                    "VALUES(:org,:id,:user,:name,:scope,:landing)"
                ),
                {
                    "org": principal.org_id,
                    "id": member_id,
                    "user": user,
                    "name": body.display_name,
                    "scope": body.visibility_override,
                    "landing": body.landing_page,
                },
            )
        await connection.execute(
            text(
                "DELETE FROM crm.membership_roles WHERE org_id=:org AND membership_id=:member"
            ),
            {"org": principal.org_id, "member": member_id},
        )
        for role in set(body.role_ids):
            await connection.execute(
                text(
                    "INSERT INTO crm.membership_roles(org_id,membership_id,role_id) VALUES(:org,:member,:role)"
                ),
                {"org": principal.org_id, "member": member_id, "role": role},
            )
        invite_id = uuid4()
        token = invitation_token(principal.org_id, invite_id, key)
        await connection.execute(
            text(
                "INSERT INTO crm.organization_invitations(org_id,id,membership_id,invited_by,token_hash,expires_at) "
                "VALUES(:org,:id,:member,:actor,:hash,now()+interval '48 hours')"
            ),
            {
                "org": principal.org_id,
                "id": invite_id,
                "member": member_id,
                "actor": principal.member_id,
                "hash": digest(token),
            },
        )
        await bump_access(connection, principal.org_id)
        await audit(
            connection,
            principal.org_id,
            principal.member_id,
            "membership.invited",
            member_id,
        )
        return {
            "membership_id": member_id,
            "invitation_token": token,
            "expires_in_hours": 48,
        }


async def recover_invitation(
    service: IdentityService, principal: Principal, member_id: UUID, key: bytes
) -> dict:
    if not principal.is_owner:
        raise AccessError(403, "permission_denied")
    async with tenant_transaction(service.engine, principal.org_id) as connection:
        invite = (
            (
                await connection.execute(
                    text(
                        "SELECT i.id,i.token_hash,i.expires_at FROM crm.organization_invitations i "
                        "JOIN crm.organization_memberships m ON m.org_id=i.org_id AND m.id=i.membership_id "
                        "WHERE i.org_id=:org AND i.membership_id=:member AND i.consumed_at IS NULL "
                        "AND i.expires_at>now() AND m.status='invited' ORDER BY i.expires_at DESC LIMIT 1"
                    ),
                    {"org": principal.org_id, "member": member_id},
                )
            )
            .mappings()
            .first()
        )
    if invite is not None:
        token = invitation_token(principal.org_id, invite["id"], key)
        if digest(token) == invite["token_hash"]:
            return {"invitation_token": token, "expires_at": invite["expires_at"]}
    raise AccessError(404, "invitation_not_available")


async def accept_invite(
    service: IdentityService, body: AcceptInvite
) -> tuple[str, str]:
    token = body.invitation_token.get_secret_value()
    try:
        org, invite_id = parse_token(token)
    except ValueError:
        raise AccessError(401, "invalid_invitation") from None
    password = body.password.get_secret_value()
    new_hash = await service.passwords.hash(password)
    async with tenant_transaction(service.engine, org) as connection:
        await connection.execute(
            text("SELECT id FROM crm.organizations WHERE id=:org FOR UPDATE"),
            {"org": org},
        )
        if await organization_access_mode(connection, org) != "full":
            raise AccessError(403, "export_only_access")
        invite = (
            (
                await connection.execute(
                    text(
                        "SELECT i.membership_id,m.user_id,i.expires_at FROM crm.organization_invitations i "
                        "JOIN crm.organization_memberships m ON m.org_id=i.org_id AND m.id=i.membership_id "
                        "JOIN crm.organizations o ON o.id=i.org_id "
                        "WHERE i.org_id=:org AND i.id=:id AND i.token_hash=:hash AND i.consumed_at IS NULL "
                        "AND m.status='invited' AND o.status='active' FOR UPDATE OF i,m"
                    ),
                    {"org": org, "id": invite_id, "hash": digest(token)},
                )
            )
            .mappings()
            .first()
        )
        if invite is None or invite["expires_at"] <= datetime.now(timezone.utc):
            raise AccessError(401, "invalid_invitation")
        if await connection.scalar(
            text("SELECT require_mfa FROM crm.organization_settings WHERE org_id=:org"),
            {"org": org},
        ):
            raise AccessError(403, "mfa_required_not_available")
        user = (
            (
                await connection.execute(
                    text(
                        "SELECT password_hash FROM crm.app_users WHERE id=:user FOR UPDATE"
                    ),
                    {"user": invite["user_id"]},
                )
            )
            .mappings()
            .one()
        )
        if user["password_hash"] is not None:
            if not await service.passwords.verify(password, user["password_hash"]):
                raise AccessError(401, "invalid_credentials")
        else:
            await connection.execute(
                text(
                    "UPDATE crm.app_users SET password_hash=:hash,updated_at=now() WHERE id=:user"
                ),
                {"hash": new_hash, "user": invite["user_id"]},
            )
        await connection.execute(
            text(
                "UPDATE crm.organization_memberships SET status='active',updated_at=now() WHERE org_id=:org AND id=:member"
            ),
            {"org": org, "member": invite["membership_id"]},
        )
        await connection.execute(
            text(
                "UPDATE crm.organization_invitations SET consumed_at=now() WHERE org_id=:org AND id=:id"
            ),
            {"org": org, "id": invite_id},
        )
        await bump_access(connection, org)
        await audit(
            connection, org, invite["membership_id"], "invitation.accepted", invite_id
        )
        return await service.issue_session(connection, org, invite["membership_id"])
