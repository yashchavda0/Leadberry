"""Let a marketplace connection assign its new leads to one organization member."""

from alembic import op

revision = "0007_marketplace_assignee"
down_revision = "0006_database_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crm.marketplace_accounts
            ADD COLUMN default_assignee_membership_id uuid,
            ADD CONSTRAINT marketplace_accounts_default_assignee_fk
                FOREIGN KEY(org_id,default_assignee_membership_id)
                REFERENCES crm.organization_memberships(org_id,id)
    """)
    op.execute("GRANT SELECT(default_assignee_membership_id) ON crm.marketplace_accounts TO crm_api")


def downgrade() -> None:
    op.execute("ALTER TABLE crm.marketplace_accounts DROP COLUMN default_assignee_membership_id")
