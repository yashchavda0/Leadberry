"""Add scoped server-to-server website intake credentials and receipts."""

from alembic import op

revision = "0020_website_intake"
down_revision = "0019_follow_up_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crm.intake_keys (
            org_id uuid NOT NULL REFERENCES crm.organizations(id),
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
            secret_hash bytea NOT NULL CHECK(octet_length(secret_hash)=32),
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            revoked_at timestamptz,
            window_started_at timestamptz NOT NULL DEFAULT now(),
            window_count integer NOT NULL DEFAULT 0 CHECK(window_count>=0),
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,created_by) REFERENCES crm.organization_memberships(org_id,id)
        )
    """)
    op.execute("""
        CREATE TABLE crm.intake_receipts (
            org_id uuid NOT NULL,
            key_id uuid NOT NULL,
            idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
            payload_hash bytea NOT NULL CHECK(octet_length(payload_hash)=32),
            lead_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,key_id,idempotency_key),
            FOREIGN KEY(org_id,key_id) REFERENCES crm.intake_keys(org_id,id),
            FOREIGN KEY(org_id,lead_id) REFERENCES crm.leads(org_id,id)
        )
    """)
    op.execute("""
        CREATE TABLE crm.source_assignment_rules (
            org_id uuid NOT NULL REFERENCES crm.organizations(id),
            source text NOT NULL CHECK(source IN ('website','indiamart','tradeindia')),
            team_id uuid NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            last_member_id uuid,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,source),
            FOREIGN KEY(org_id,team_id) REFERENCES crm.teams(org_id,id)
        )
    """)
    for table in ("intake_keys", "intake_receipts", "source_assignment_rules"):
        op.execute(f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE crm.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_boundary ON crm.{table} USING(org_id=crm.current_org_id()) WITH CHECK(org_id=crm.current_org_id())"
        )
        op.execute(
            f"CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.{table} FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
        )
    op.execute("GRANT SELECT,INSERT,UPDATE ON crm.intake_keys TO crm_api")
    op.execute("GRANT SELECT,INSERT ON crm.intake_receipts TO crm_api")
    op.execute("GRANT SELECT,INSERT,UPDATE ON crm.source_assignment_rules TO crm_api")
    op.execute("GRANT SELECT,UPDATE ON crm.source_assignment_rules TO crm_worker")
    op.execute("GRANT SELECT ON crm.teams,crm.team_memberships TO crm_worker")
    op.execute(
        "GRANT UPDATE(assigned_membership_id,team_id,row_version,updated_at) ON crm.leads TO crm_worker"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive intake downgrade is disabled; use a reviewed forward migration or backup restore."
    )
