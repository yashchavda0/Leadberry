"""Add platform administration and subscription lifecycle controls."""

from alembic import op

revision = "0023_platform_administration"
down_revision = "0022_lead_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm.app_users ADD COLUMN password_change_required boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE crm.organizations ADD COLUMN subscription_plan text NOT NULL DEFAULT 'legacy'")
    op.execute(
        "ALTER TABLE crm.organizations ADD COLUMN subscription_status text NOT NULL DEFAULT 'active' "
        "CHECK (subscription_status IN ('trialing','active','past_due','expired','canceled'))"
    )
    op.execute("ALTER TABLE crm.organizations ADD COLUMN subscription_started_at timestamptz")
    op.execute("ALTER TABLE crm.organizations ADD COLUMN subscription_ends_at timestamptz")
    op.execute("ALTER TABLE crm.organizations ADD COLUMN export_access_until timestamptz")
    op.execute("ALTER TABLE crm.organizations ADD COLUMN max_users integer NOT NULL DEFAULT 100 CHECK (max_users > 0)")
    op.execute(
        "CREATE TABLE crm.platform_operators ("
        "user_id uuid PRIMARY KEY REFERENCES crm.app_users(id), "
        "access_level text NOT NULL CHECK (access_level IN ('support','administrator')), "
        "created_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE crm.platform_sessions ("
        "id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES crm.app_users(id), "
        "token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash)=32), "
        "csrf_token_hash bytea NOT NULL CHECK (octet_length(csrf_token_hash)=32), "
        "expires_at timestamptz NOT NULL, revoked_at timestamptz, "
        "created_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute("CREATE INDEX platform_sessions_user ON crm.platform_sessions(user_id,expires_at)")
    op.execute(
        "CREATE TABLE crm.platform_audit_logs ("
        "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
        "actor_user_id uuid NOT NULL REFERENCES crm.app_users(id), "
        "organization_id uuid REFERENCES crm.organizations(id), "
        "action text NOT NULL, entity_type text NOT NULL, entity_id uuid, "
        "details jsonb NOT NULL DEFAULT '{}', occurred_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE INDEX platform_audit_org_time ON crm.platform_audit_logs(organization_id,occurred_at DESC,id DESC)"
    )
    op.execute("REVOKE ALL ON crm.platform_operators,crm.platform_sessions,crm.platform_audit_logs FROM PUBLIC")
    op.execute("GRANT SELECT ON crm.platform_operators TO crm_auth")
    op.execute("GRANT SELECT,INSERT,UPDATE ON crm.platform_sessions TO crm_auth")
    op.execute("GRANT SELECT,INSERT ON crm.platform_audit_logs TO crm_auth")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='crm_platform_provisioner') THEN "
        "EXECUTE format('GRANT CONNECT ON DATABASE %I TO crm_platform_provisioner',current_database()); "
        "EXECUTE 'GRANT USAGE ON SCHEMA crm TO crm_platform_provisioner'; "
        "EXECUTE 'GRANT SELECT,INSERT,UPDATE ON crm.app_users TO crm_platform_provisioner'; "
        "EXECUTE 'GRANT SELECT,INSERT,UPDATE ON crm.platform_operators TO crm_platform_provisioner'; "
        "END IF; END $$"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Platform administration downgrade is disabled; use a reviewed forward migration or backup restore."
    )