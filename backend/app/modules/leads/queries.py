from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import text

from ...core.database import tenant_transaction
from ..identity.service import AccessError, Principal, effective_access


@asynccontextmanager
async def access(request: Request, user: Principal, permission: str):
    async with tenant_transaction(
        request.app.state.database_engine, user.org_id, user.member_id
    ) as connection:
        # Shared locks let lead requests run concurrently while access writers use an exclusive lock.
        await connection.execute(
            text("SELECT id FROM crm.organizations WHERE id=:org FOR SHARE"),
            {"org": user.org_id},
        )
        owner, codes, scope, identity = await effective_access(
            connection, user.org_id, user.member_id
        )
        current = Principal(
            user.org_id, user.member_id, user.session_id, identity, owner, codes, scope
        )
        if permission not in codes:
            raise AccessError(403, "permission_denied")
        yield connection, current


def visibility(user: Principal) -> str:
    own = "(l.assigned_membership_id=:member OR l.assigned_membership_id IS NULL)"
    if user.data_scope == "all":
        return "TRUE"
    if user.data_scope == "team":
        return (
            f"({own} OR EXISTS(SELECT 1 FROM crm.team_memberships tm JOIN crm.teams t "
            "ON t.org_id=tm.org_id AND t.id=tm.team_id AND t.is_active "
            "WHERE tm.org_id=l.org_id AND tm.membership_id=:member AND tm.team_id=l.team_id))"
        )
    return own


def fields(user: Principal) -> str:
    pii = "leads.pii.view" in user.permissions
    contacts = (
        "l.phone,l.email,l.address,l.enquiry,l.custom_fields"
        if pii
        else "NULL::text AS phone,NULL::text AS email,NULL::text AS address,NULL::text AS enquiry,'{}'::jsonb AS custom_fields"
    )
    return (
        "l.id,l.name,l.company,l.city,l.state,l.product,l.source_provider,l.source_record_id,l.status_id,"
        "l.integration_id,a.name AS source_account_name,"
        "s.name AS status,s.color AS status_color,l.assigned_membership_id,m.display_name AS assignee,"
        "l.team_id,l.tags,l.next_follow_up_at,l.archived_at,l.row_version,l.received_at,l.updated_at,l.status_changed_at,"
        f"{contacts},{'false' if pii else 'true'} AS pii_redacted"
    )


JOINS = (
    "FROM crm.leads l JOIN crm.lead_statuses s ON s.org_id=l.org_id AND s.id=l.status_id "
    "LEFT JOIN crm.organization_memberships m ON m.org_id=l.org_id AND m.id=l.assigned_membership_id "
    "LEFT JOIN crm.marketplace_accounts a ON a.org_id=l.org_id AND a.id=l.integration_id "
)
