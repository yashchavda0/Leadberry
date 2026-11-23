"""Add personal details (date of birth, gender, location) to organization memberships."""

from alembic import op

revision = "0018_member_personal_details"
down_revision = "0017_member_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crm.organization_memberships
            ADD COLUMN date_of_birth date,
            ADD COLUMN gender text CHECK(gender IN ('female','male','non_binary','prefer_not_to_say')),
            ADD COLUMN address varchar(300),
            ADD COLUMN city varchar(100),
            ADD COLUMN state varchar(100)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE crm.organization_memberships
            DROP COLUMN date_of_birth, DROP COLUMN gender, DROP COLUMN address,
            DROP COLUMN city, DROP COLUMN state
    """)
