"""Add optional personal details to organization memberships."""

from alembic import op

revision = "0017_member_profile"
down_revision = "0016_lead_fetch_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm.organization_memberships ADD COLUMN job_title varchar(120)")


def downgrade() -> None:
    op.execute("ALTER TABLE crm.organization_memberships DROP COLUMN job_title")