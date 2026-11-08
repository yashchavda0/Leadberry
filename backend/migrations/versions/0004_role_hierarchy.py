"""Reporting hierarchy and per-membership landing pages."""

from alembic import op

revision = "0004_role_hierarchy"
down_revision = "0003_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crm.roles ADD COLUMN reports_to_role_id uuid,
        ADD CONSTRAINT role_parent_tenant FOREIGN KEY(org_id,reports_to_role_id)
            REFERENCES crm.roles(org_id,id),
        ADD CONSTRAINT role_not_self_parent CHECK(reports_to_role_id IS DISTINCT FROM id)
    """)
    op.execute("CREATE INDEX roles_parent ON crm.roles(org_id,reports_to_role_id)")
    op.execute("""
        ALTER TABLE crm.organization_memberships ADD COLUMN landing_page text,
        ADD CONSTRAINT membership_landing_page CHECK(
            landing_page IS NULL OR landing_page IN ('/','/leads','/users','/settings','/marketplace','/account')
        )
    """)


def downgrade() -> None:
    raise RuntimeError("Use a reviewed forward migration to preserve reporting and landing preferences")
