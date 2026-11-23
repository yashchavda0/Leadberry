"""Record explicit, actor-attributed lead response activities."""

from alembic import op

revision = "0022_lead_activities"
down_revision = "0021_assignment_cursor_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crm.lead_activities (
            org_id uuid NOT NULL,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            lead_id uuid NOT NULL,
            actor_membership_id uuid NOT NULL,
            activity_type text NOT NULL CHECK(activity_type IN ('call','email','meeting','other')),
            outcome text NOT NULL CHECK(outcome IN ('connected','no_answer','left_message','scheduled','not_applicable')),
            note text NOT NULL DEFAULT '' CHECK(length(note)<=2000),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,lead_id) REFERENCES crm.leads(org_id,id) ON DELETE CASCADE,
            FOREIGN KEY(org_id,actor_membership_id) REFERENCES crm.organization_memberships(org_id,id)
        )
    """)
    op.execute(
        "CREATE INDEX lead_activities_recent ON crm.lead_activities(org_id,lead_id,created_at DESC,id DESC)"
    )
    op.execute(
        "CREATE INDEX lead_activities_actor ON crm.lead_activities(org_id,actor_membership_id,created_at DESC,id DESC)"
    )
    op.execute("ALTER TABLE crm.lead_activities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE crm.lead_activities FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_boundary ON crm.lead_activities USING(org_id=crm.current_org_id()) WITH CHECK(org_id=crm.current_org_id())"
    )
    op.execute(
        "CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.lead_activities FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
    )
    op.execute("GRANT SELECT,INSERT ON crm.lead_activities TO crm_api")


def downgrade() -> None:
    raise RuntimeError(
        "Destructive activity downgrade is disabled; use a reviewed forward migration or backup restore."
    )
