"""Add tenant-scoped marketplace accounts, encrypted credentials and durable sync runs."""

from alembic import op

revision = "0005_marketplace"
down_revision = "0004_role_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crm.marketplace_accounts (
            org_id uuid NOT NULL REFERENCES crm.organizations(id), id uuid NOT NULL,
            provider_code text NOT NULL, name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
            status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','paused','error','retired')),
            config jsonb NOT NULL CHECK(jsonb_typeof(config)='object'),
            credential_envelope jsonb NOT NULL, credential_fingerprint text NOT NULL,
            credential_version integer NOT NULL DEFAULT 1, verified_version integer,
            row_version bigint NOT NULL DEFAULT 1, created_by uuid NOT NULL,
            last_success_at timestamptz, last_received_at timestamptz, safe_error_code text,
            watermark timestamptz NOT NULL DEFAULT now()-interval '1 day',
            next_allowed_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,created_by) REFERENCES crm.organization_memberships(org_id,id)
        )
    """)
    op.execute("CREATE UNIQUE INDEX marketplace_account_names ON crm.marketplace_accounts(org_id,lower(name)) WHERE status<>'retired'")
    op.execute("CREATE UNIQUE INDEX marketplace_account_credentials ON crm.marketplace_accounts(org_id,provider_code,credential_fingerprint) WHERE status<>'retired'")
    op.execute("""
        CREATE TABLE crm.marketplace_sync_runs (
            org_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), account_id uuid NOT NULL,
            kind text NOT NULL CHECK(kind IN ('test','sync')), credential_version integer NOT NULL,
            state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','completed','failed','cancelled')),
            fetched_count integer NOT NULL DEFAULT 0, accepted_count integer NOT NULL DEFAULT 0,
            safe_error_code text, lease_token uuid, lease_until timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
            PRIMARY KEY(org_id,id), FOREIGN KEY(org_id,account_id) REFERENCES crm.marketplace_accounts(org_id,id)
        )
    """)
    op.execute("CREATE UNIQUE INDEX marketplace_one_pending_run ON crm.marketplace_sync_runs(org_id,account_id) WHERE state IN ('queued','running')")
    op.execute("CREATE INDEX marketplace_run_history ON crm.marketplace_sync_runs(org_id,account_id,created_at DESC)")
    op.execute("CREATE TABLE crm.marketplace_rate_limits (fingerprint text PRIMARY KEY, next_allowed_at timestamptz NOT NULL)")
    op.execute("ALTER TABLE crm.leads ADD COLUMN integration_id uuid, ADD COLUMN source_record_id text")
    op.execute("ALTER TABLE crm.leads ADD FOREIGN KEY(org_id,integration_id) REFERENCES crm.marketplace_accounts(org_id,id)")
    op.execute("CREATE UNIQUE INDEX leads_integration_identity ON crm.leads(org_id,integration_id,source_record_id) WHERE integration_id IS NOT NULL")
    for table in ("marketplace_accounts", "marketplace_sync_runs"):
        op.execute(f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE crm.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_boundary ON crm.{table} USING(org_id=crm.current_org_id()) WITH CHECK(org_id=crm.current_org_id())")
        op.execute(f"CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.{table} FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()")


def downgrade() -> None:
    raise RuntimeError("Destructive marketplace downgrade is disabled; use a reviewed forward migration.")