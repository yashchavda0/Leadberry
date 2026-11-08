"""Let one connector worker serve every organization, report liveness and expose masked key hints."""

from alembic import op

revision = "0009_marketplace_worker"
down_revision = "0008_lead_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The directory holds only routing identifiers; tenant data stays behind RLS per organization.
    op.execute(
        "GRANT SELECT(organization_id) ON crm.organization_directory TO crm_worker"
    )
    op.execute("""
        CREATE TABLE crm.marketplace_worker_heartbeat (
            id boolean PRIMARY KEY DEFAULT true CHECK(id),
            last_seen_at timestamptz NOT NULL
        )
    """)
    op.execute("GRANT SELECT ON crm.marketplace_worker_heartbeat TO crm_api")
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON crm.marketplace_worker_heartbeat TO crm_worker"
    )
    op.execute(
        "ALTER TABLE crm.marketplace_accounts ADD COLUMN credential_hint jsonb NOT NULL DEFAULT '{}'::jsonb "
        "CHECK(jsonb_typeof(credential_hint)='object')"
    )
    op.execute("GRANT SELECT(credential_hint) ON crm.marketplace_accounts TO crm_api")


def downgrade() -> None:
    op.execute("ALTER TABLE crm.marketplace_accounts DROP COLUMN credential_hint")
    op.execute("DROP TABLE crm.marketplace_worker_heartbeat")
    op.execute(
        "REVOKE SELECT(organization_id) ON crm.organization_directory FROM crm_worker"
    )
