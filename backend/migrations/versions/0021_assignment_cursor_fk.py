"""Keep assignment cursors bound to organization memberships."""

from alembic import op

revision = "0021_assignment_cursor_fk"
down_revision = "0020_website_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm.source_assignment_rules "
        "ADD CONSTRAINT source_assignment_last_member_fk "
        "FOREIGN KEY(org_id,last_member_id) "
        "REFERENCES crm.organization_memberships(org_id,id)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE crm.source_assignment_rules "
        "DROP CONSTRAINT source_assignment_last_member_fk"
    )
