"""Track marketplace refetches, lead assignment history and connector retry state."""

from alembic import op

revision = "0016_lead_fetch_tracking"
down_revision = "0015_repeat_customers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crm.leads
            ADD COLUMN first_fetched_at timestamptz,
            ADD COLUMN last_fetched_at timestamptz,
            ADD COLUMN fetch_count integer NOT NULL DEFAULT 0 CHECK(fetch_count>=0),
            ADD COLUMN campaign_id text CHECK(campaign_id IS NULL OR length(campaign_id) BETWEEN 1 AND 200),
            ADD COLUMN ad_id text CHECK(ad_id IS NULL OR length(ad_id) BETWEEN 1 AND 200),
            ADD COLUMN form_id text CHECK(form_id IS NULL OR length(form_id) BETWEEN 1 AND 200),
            ADD COLUMN description text NOT NULL DEFAULT '' CHECK(length(description)<=4000),
            ADD COLUMN payload_hash text CHECK(payload_hash IS NULL OR length(payload_hash)=64)
    """)
    op.execute("""
        DO $$
        DECLARE tenant record;
        BEGIN
            FOR tenant IN SELECT organization_id FROM crm.organization_directory LOOP
                PERFORM set_config('app.org_id', tenant.organization_id::text, true);
                UPDATE crm.leads
                SET first_fetched_at=created_at,last_fetched_at=created_at,fetch_count=1
                WHERE org_id=tenant.organization_id AND integration_id IS NOT NULL;
            END LOOP;
            PERFORM set_config('app.org_id', '', true);
        END $$
    """)
    op.execute(
        "GRANT UPDATE(name,company,phone,email,city,state,address,product,enquiry,description,"
        "campaign_id,ad_id,form_id,payload_hash,last_fetched_at,fetch_count) ON crm.leads TO crm_worker"
    )
    op.execute(
        "ALTER TABLE crm.marketplace_accounts "
        "ADD COLUMN consecutive_failures integer NOT NULL DEFAULT 0 CHECK(consecutive_failures>=0)"
    )
    op.execute("""
        CREATE TABLE crm.lead_assignments (
            org_id uuid NOT NULL,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            lead_id uuid NOT NULL,
            from_membership_id uuid,
            to_membership_id uuid,
            actor_membership_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,lead_id) REFERENCES crm.leads(org_id,id) ON DELETE CASCADE,
            FOREIGN KEY(org_id,from_membership_id) REFERENCES crm.organization_memberships(org_id,id),
            FOREIGN KEY(org_id,to_membership_id) REFERENCES crm.organization_memberships(org_id,id),
            FOREIGN KEY(org_id,actor_membership_id) REFERENCES crm.organization_memberships(org_id,id)
        )
    """)
    op.execute(
        "CREATE INDEX lead_assignments_recent "
        "ON crm.lead_assignments(org_id,lead_id,created_at DESC,id DESC)"
    )
    op.execute("ALTER TABLE crm.lead_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE crm.lead_assignments FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_boundary ON crm.lead_assignments "
        "USING(org_id=crm.current_org_id()) WITH CHECK(org_id=crm.current_org_id())"
    )
    op.execute(
        "CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.lead_assignments "
        "FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
    )
    op.execute("GRANT SELECT,INSERT ON crm.lead_assignments TO crm_api, crm_worker")
    # The actor is the transaction's membership setting; the worker leaves it empty.
    op.execute("""
        CREATE FUNCTION crm.record_lead_assignment() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,crm AS $$
        BEGIN
            IF TG_OP='INSERT' AND NEW.assigned_membership_id IS NULL THEN
                RETURN NULL;
            END IF;
            IF TG_OP='UPDATE' AND NEW.assigned_membership_id IS NOT DISTINCT FROM OLD.assigned_membership_id THEN
                RETURN NULL;
            END IF;
            INSERT INTO crm.lead_assignments(org_id,lead_id,from_membership_id,to_membership_id,actor_membership_id)
            VALUES (
                NEW.org_id,
                NEW.id,
                CASE WHEN TG_OP='UPDATE' THEN OLD.assigned_membership_id END,
                NEW.assigned_membership_id,
                NULLIF(current_setting('app.membership_id', true),'')::uuid
            );
            RETURN NULL;
        END $$
    """)
    op.execute(
        "CREATE TRIGGER record_lead_assignment AFTER INSERT OR UPDATE OF assigned_membership_id "
        "ON crm.leads FOR EACH ROW EXECUTE FUNCTION crm.record_lead_assignment()"
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported for marketplace lead sync tracking")
