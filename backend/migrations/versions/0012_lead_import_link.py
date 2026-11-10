"""Link leads to the history import that created them so imports can be viewed and exported."""

from alembic import op

revision = "0012_lead_import_link"
down_revision = "0011_marketplace_gap_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm.leads ADD COLUMN backfill_id uuid")
    op.execute(
        "ALTER TABLE crm.leads ADD CONSTRAINT leads_backfill_fk FOREIGN KEY(org_id,backfill_id) "
        "REFERENCES crm.marketplace_backfills(org_id,id)"
    )
    op.execute(
        "CREATE INDEX leads_backfill ON crm.leads(org_id,backfill_id,received_at DESC,id DESC) "
        "WHERE backfill_id IS NOT NULL"
    )
    # Live inserts get received_at=created_at in one transaction; only imported history carries an older enquiry time.
    # Row-level security also binds the migrator, so the link is set per organization.
    op.execute("""
        DO $$ DECLARE organization uuid; BEGIN
        FOR organization IN SELECT organization_id FROM crm.organization_directory LOOP
            PERFORM set_config('app.org_id', organization::text, true);
            UPDATE crm.leads l SET backfill_id=b.id
            FROM crm.marketplace_backfills b
            WHERE l.org_id=b.org_id AND l.integration_id=b.account_id AND l.backfill_id IS NULL
              AND l.received_at<l.created_at AND l.received_at>=b.range_start AND l.received_at<b.range_end
              AND l.created_at>=b.created_at AND l.created_at<=COALESCE(b.finished_at,now());
        END LOOP;
        PERFORM set_config('app.org_id', '', true);
        END $$
    """)


def downgrade() -> None:
    op.execute("DROP INDEX crm.leads_backfill")
    op.execute("ALTER TABLE crm.leads DROP COLUMN backfill_id")
