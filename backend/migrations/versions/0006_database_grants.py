"""Grant least-privilege table access to the login roles created by the local database init script."""

from alembic import op

revision = "0006_database_grants"
down_revision = "0005_marketplace"
branch_labels = None
depends_on = None

GRANTS = (
    "GRANT USAGE ON SCHEMA crm, public TO crm_auth, crm_api, crm_worker",
    "GRANT SELECT ON public.alembic_version TO crm_auth, crm_api, crm_worker",
    "GRANT EXECUTE ON FUNCTION crm.current_org_id() TO crm_auth, crm_api, crm_worker",
    "GRANT SELECT,INSERT,UPDATE ON crm.app_users TO crm_auth",
    "GRANT SELECT ON crm.organization_directory,crm.permissions,crm.roles,crm.role_permissions TO crm_auth",
    "GRANT SELECT,INSERT,UPDATE ON crm.organizations,crm.organization_memberships,"
    "crm.organization_settings,crm.lead_statuses,crm.auth_sessions,crm.session_refresh_tokens,"
    "crm.organization_invitations,crm.auth_rate_limits TO crm_auth",
    "GRANT SELECT,INSERT,DELETE ON crm.membership_roles TO crm_auth",
    "GRANT SELECT ON crm.membership_permission_overrides TO crm_auth",
    "GRANT INSERT ON crm.audit_logs TO crm_auth",
    "GRANT SELECT ON crm.organizations,crm.organization_memberships,crm.lead_statuses,crm.organization_settings,crm.permissions TO crm_api",
    "GRANT SELECT,INSERT,UPDATE ON crm.roles TO crm_api",
    "GRANT SELECT,INSERT,DELETE ON crm.role_permissions,crm.membership_roles,crm.membership_permission_overrides TO crm_api",
    "GRANT UPDATE ON crm.organizations,crm.organization_memberships,crm.auth_sessions TO crm_api",
    "GRANT SELECT(org_id,membership_id) ON crm.auth_sessions TO crm_api",
    "GRANT INSERT ON crm.audit_logs TO crm_api",
    "GRANT SELECT,INSERT,UPDATE ON crm.leads,crm.teams TO crm_api",
    "GRANT SELECT,INSERT,DELETE ON crm.team_memberships TO crm_api",
    "GRANT INSERT,UPDATE ON crm.marketplace_accounts TO crm_api",
    "GRANT SELECT(org_id,id,provider_code,name,status,config,credential_version,verified_version,row_version,"
    "created_by,last_success_at,last_received_at,safe_error_code,created_at,updated_at) ON crm.marketplace_accounts TO crm_api",
    "GRANT SELECT,INSERT,UPDATE ON crm.marketplace_sync_runs TO crm_api",
    "GRANT UPDATE(id) ON crm.organizations TO crm_worker",
    "GRANT SELECT ON crm.organizations,crm.organization_memberships,crm.permissions,crm.roles,"
    "crm.role_permissions,crm.membership_roles,crm.membership_permission_overrides,crm.lead_statuses TO crm_worker",
    "GRANT SELECT,INSERT,UPDATE ON crm.marketplace_accounts,crm.marketplace_sync_runs,crm.marketplace_rate_limits TO crm_worker",
    "GRANT SELECT,INSERT ON crm.leads TO crm_worker",
    "GRANT INSERT ON crm.audit_logs TO crm_worker",
)


def upgrade() -> None:
    # GRANT CONNECT needs an identifier, so resolve the current database name in a DO block.
    op.execute(
        "DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO crm_auth, crm_api, crm_worker', "
        "current_database()); END $$"
    )
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # Grants are idempotent and carry no data; leaving them in place is safe on downgrade.
    pass
