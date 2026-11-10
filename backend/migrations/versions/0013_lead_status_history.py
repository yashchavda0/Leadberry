"""Persist lead status transitions with their notes."""

from alembic import op

revision = "0013_lead_status_history"
down_revision = "0012_lead_import_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crm.lead_status_history (
            org_id uuid NOT NULL,
            id uuid NOT NULL,
            lead_id uuid NOT NULL,
            from_status text NOT NULL,
            to_status text NOT NULL,
            note text NOT NULL CHECK(length(note) BETWEEN 1 AND 2000),
            actor_name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,lead_id) REFERENCES crm.leads(org_id,id) ON DELETE CASCADE
        )
    """)
    op.execute(
        "CREATE INDEX lead_status_history_recent "
        "ON crm.lead_status_history(org_id,lead_id,created_at DESC,id DESC)"
    )
    op.execute("ALTER TABLE crm.lead_status_history ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE crm.lead_status_history FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_boundary ON crm.lead_status_history "
        "USING(org_id=crm.current_org_id()) WITH CHECK(org_id=crm.current_org_id())"
    )
    op.execute(
        "CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.lead_status_history "
        "FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
    )
    op.execute("GRANT SELECT,INSERT ON crm.lead_status_history TO crm_api")


def downgrade() -> None:
    op.execute("DROP TABLE crm.lead_status_history")