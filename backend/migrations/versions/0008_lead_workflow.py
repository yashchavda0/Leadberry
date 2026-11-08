"""Add organization lead fields, status rules and per-member table preferences."""

from alembic import op

revision = "0008_lead_workflow"
down_revision = "0007_marketplace_assignee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm.lead_statuses ADD COLUMN is_system boolean NOT NULL DEFAULT false"
    )
    op.execute("UPDATE crm.lead_statuses SET is_system=true")
    op.execute(
        "ALTER TABLE crm.leads ADD COLUMN status_changed_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute("UPDATE crm.leads SET status_changed_at=updated_at")
    op.execute("""
        CREATE TABLE crm.lead_custom_fields (
            org_id uuid NOT NULL REFERENCES crm.organizations(id),
            field_key text NOT NULL CHECK(length(field_key) BETWEEN 1 AND 100),
            label text NOT NULL CHECK(length(label) BETWEEN 1 AND 100),
            field_type text NOT NULL CHECK(field_type IN ('text','number','boolean','select')),
            options jsonb NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(options)='array'),
            position integer NOT NULL DEFAULT 0,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,field_key),
            UNIQUE(org_id,label)
        )
    """)
    op.execute("""
        CREATE TABLE crm.lead_status_rules (
            org_id uuid NOT NULL,
            status_id uuid NOT NULL,
            tag_on_entry text CHECK(tag_on_entry IS NULL OR length(tag_on_entry) BETWEEN 1 AND 50),
            auto_assign boolean NOT NULL DEFAULT false,
            round_robin_cursor bigint NOT NULL DEFAULT 0 CHECK(round_robin_cursor>=0),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,status_id),
            FOREIGN KEY(org_id,status_id) REFERENCES crm.lead_statuses(org_id,id)
        )
    """)
    op.execute("""
        CREATE TABLE crm.lead_status_rule_members (
            org_id uuid NOT NULL,
            status_id uuid NOT NULL,
            membership_id uuid NOT NULL,
            position integer NOT NULL DEFAULT 0,
            PRIMARY KEY(org_id,status_id,membership_id),
            FOREIGN KEY(org_id,status_id) REFERENCES crm.lead_status_rules(org_id,status_id) ON DELETE CASCADE,
            FOREIGN KEY(org_id,membership_id) REFERENCES crm.organization_memberships(org_id,id)
        )
    """)
    op.execute("""
        CREATE TABLE crm.lead_status_rule_roles (
            org_id uuid NOT NULL,
            status_id uuid NOT NULL,
            role_id uuid NOT NULL,
            PRIMARY KEY(org_id,status_id,role_id),
            FOREIGN KEY(org_id,status_id) REFERENCES crm.lead_status_rules(org_id,status_id) ON DELETE CASCADE,
            FOREIGN KEY(org_id,role_id) REFERENCES crm.roles(org_id,id)
        )
    """)
    op.execute("""
        CREATE TABLE crm.lead_status_required_fields (
            org_id uuid NOT NULL,
            status_id uuid NOT NULL,
            field_key text NOT NULL CHECK(length(field_key) BETWEEN 1 AND 100),
            PRIMARY KEY(org_id,status_id,field_key),
            FOREIGN KEY(org_id,status_id) REFERENCES crm.lead_status_rules(org_id,status_id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE crm.lead_table_preferences (
            org_id uuid NOT NULL,
            membership_id uuid NOT NULL,
            columns jsonb NOT NULL CHECK(jsonb_typeof(columns)='array'),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,membership_id),
            FOREIGN KEY(org_id,membership_id) REFERENCES crm.organization_memberships(org_id,id) ON DELETE CASCADE
        )
    """)
    for table in (
        "lead_custom_fields",
        "lead_status_rules",
        "lead_status_rule_members",
        "lead_status_rule_roles",
        "lead_status_required_fields",
        "lead_table_preferences",
    ):
        op.execute(f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE crm.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_boundary ON crm.{table} "
            "USING(org_id=crm.current_org_id()) WITH CHECK(org_id=crm.current_org_id())"
        )
        op.execute(
            f"CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.{table} "
            "FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
        )
    op.execute("GRANT SELECT,INSERT,UPDATE ON crm.lead_statuses TO crm_api")
    op.execute(
        "GRANT SELECT,INSERT,UPDATE,DELETE ON crm.lead_custom_fields,crm.lead_status_rules,"
        "crm.lead_status_rule_members,crm.lead_status_rule_roles,crm.lead_status_required_fields "
        "TO crm_api"
    )
    op.execute("GRANT SELECT,INSERT,UPDATE ON crm.lead_table_preferences TO crm_api")


def downgrade() -> None:
    raise RuntimeError(
        "Destructive lead workflow downgrade is disabled; use a reviewed forward migration or backup restore."
    )
