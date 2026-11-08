"""Configurable live sync interval, history import ledger and user-visible hold reasons."""

from alembic import op

revision = "0010_marketplace_schedule"
down_revision = "0009_marketplace_worker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crm.marketplace_accounts
            ADD COLUMN sync_interval_seconds integer NOT NULL DEFAULT 900
                CHECK(sync_interval_seconds IN (300,600,900,1200,1800,3600)),
            ADD COLUMN next_live_at timestamptz NOT NULL DEFAULT now(),
            ADD COLUMN hold_reason text CHECK(length(hold_reason)<=80),
            ADD COLUMN hold_until timestamptz,
            ADD COLUMN last_request_at timestamptz
    """)
    op.execute(
        "ALTER TABLE crm.marketplace_sync_runs DROP CONSTRAINT marketplace_sync_runs_kind_check"
    )
    op.execute("""
        ALTER TABLE crm.marketplace_sync_runs
            ADD CONSTRAINT marketplace_sync_runs_kind_check CHECK(kind IN ('test','sync','backfill')),
            ADD COLUMN window_id uuid,
            ADD COLUMN window_start timestamptz,
            ADD COLUMN window_end timestamptz
    """)
    op.execute("""
        CREATE TABLE crm.marketplace_backfills (
            org_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), account_id uuid NOT NULL,
            range_start timestamptz NOT NULL, range_end timestamptz NOT NULL CHECK(range_end>range_start),
            state text NOT NULL DEFAULT 'active' CHECK(state IN ('active','completed','cancelled')),
            hold_reason text CHECK(length(hold_reason)<=80), hold_until timestamptz,
            windows_total integer NOT NULL DEFAULT 0, fetched_count integer NOT NULL DEFAULT 0,
            accepted_count integer NOT NULL DEFAULT 0, empty_streak integer NOT NULL DEFAULT 0,
            created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,account_id) REFERENCES crm.marketplace_accounts(org_id,id),
            FOREIGN KEY(org_id,created_by) REFERENCES crm.organization_memberships(org_id,id)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX marketplace_one_active_backfill ON crm.marketplace_backfills(org_id,account_id) WHERE state='active'"
    )
    op.execute(
        "CREATE INDEX marketplace_backfill_history ON crm.marketplace_backfills(org_id,account_id,created_at DESC)"
    )
    op.execute("""
        CREATE TABLE crm.marketplace_backfill_windows (
            org_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(),
            backfill_id uuid NOT NULL, account_id uuid NOT NULL,
            window_start timestamptz NOT NULL, window_end timestamptz NOT NULL CHECK(window_end>window_start),
            state text NOT NULL DEFAULT 'pending'
                CHECK(state IN ('pending','running','completed','failed','expired','skipped','split','cancelled')),
            next_page integer NOT NULL DEFAULT 1 CHECK(next_page>=1),
            attempts integer NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(),
            hold_reason text CHECK(length(hold_reason)<=80), safe_error_code text,
            fetched_count integer NOT NULL DEFAULT 0, accepted_count integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,id),
            UNIQUE(org_id,backfill_id,window_start,window_end),
            FOREIGN KEY(org_id,backfill_id) REFERENCES crm.marketplace_backfills(org_id,id),
            FOREIGN KEY(org_id,account_id) REFERENCES crm.marketplace_accounts(org_id,id)
        )
    """)
    op.execute(
        "CREATE INDEX marketplace_backfill_queue ON crm.marketplace_backfill_windows(org_id,backfill_id,window_end DESC) WHERE state='pending'"
    )
    op.execute(
        "CREATE INDEX marketplace_backfill_windows_by_job ON crm.marketplace_backfill_windows(org_id,backfill_id,window_end DESC,window_start DESC)"
    )
    for table in ("marketplace_backfills", "marketplace_backfill_windows"):
        op.execute(f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE crm.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_boundary ON crm.{table} USING(org_id=crm.current_org_id()) "
            "WITH CHECK(org_id=crm.current_org_id())"
        )
        op.execute(
            f"CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.{table} FOR EACH ROW "
            "EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
        )
    # Exposes only when a shared key is free again; the fingerprint itself stays unreadable to the API.
    op.execute("""
        CREATE FUNCTION crm.marketplace_key_available_at(account uuid) RETURNS timestamptz
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, crm AS $$
            SELECT l.next_allowed_at FROM crm.marketplace_rate_limits l
            JOIN crm.marketplace_accounts a ON a.credential_fingerprint=l.fingerprint
            WHERE a.org_id=crm.current_org_id() AND a.id=account
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION crm.marketplace_key_available_at(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION crm.marketplace_key_available_at(uuid) TO crm_api")
    op.execute(
        "GRANT SELECT(sync_interval_seconds,next_live_at,next_allowed_at,hold_reason,hold_until,last_request_at) "
        "ON crm.marketplace_accounts TO crm_api"
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON crm.marketplace_backfills,crm.marketplace_backfill_windows TO crm_api, crm_worker"
    )


def downgrade() -> None:
    raise RuntimeError("Destructive marketplace downgrade is disabled; use a reviewed forward migration.")
