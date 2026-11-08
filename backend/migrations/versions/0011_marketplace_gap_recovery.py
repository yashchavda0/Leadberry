"""Record whether a history job was requested by a user or created to recover leads missed during a long pause."""

from alembic import op

revision = "0011_marketplace_gap_recovery"
down_revision = "0010_marketplace_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm.marketplace_backfills ADD COLUMN kind text NOT NULL DEFAULT 'import' "
        "CHECK(kind IN ('import','gap'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE crm.marketplace_backfills DROP COLUMN kind")
