"""Track the first conversion for repeat-customer matching."""

from alembic import op

revision = "0015_repeat_customers"
down_revision = "0014_organization_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm.leads ADD COLUMN converted_at timestamptz")
    op.execute("""
        DO $$
        DECLARE tenant record;
        BEGIN
            FOR tenant IN SELECT organization_id FROM crm.organization_directory LOOP
                PERFORM set_config('app.org_id', tenant.organization_id::text, true);
                UPDATE crm.leads l SET converted_at=l.status_changed_at
                FROM crm.lead_statuses s
                WHERE l.org_id=tenant.organization_id AND s.org_id=l.org_id
                  AND s.id=l.status_id AND s.category='won';
                UPDATE crm.leads l SET converted_at=LEAST(l.converted_at, conversions.first_conversion)
                FROM (
                    SELECT h.lead_id,min(h.created_at) AS first_conversion
                    FROM crm.lead_status_history h
                    JOIN crm.lead_statuses s ON s.org_id=h.org_id AND s.name=h.to_status AND s.category='won'
                    WHERE h.org_id=tenant.organization_id GROUP BY h.lead_id
                ) conversions
                WHERE l.org_id=tenant.organization_id AND l.id=conversions.lead_id;
            END LOOP;
            PERFORM set_config('app.org_id', '', true);
        END $$
    """)
    op.execute("""
        CREATE FUNCTION crm.record_first_lead_conversion() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,crm AS $$
        BEGIN
            IF NEW.converted_at IS NULL AND EXISTS (
                SELECT 1 FROM crm.lead_statuses s
                WHERE s.org_id=NEW.org_id AND s.id=NEW.status_id AND s.category='won'
            ) THEN
                NEW.converted_at := now();
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER leads_first_conversion BEFORE INSERT OR UPDATE OF status_id ON crm.leads FOR EACH ROW EXECUTE FUNCTION crm.record_first_lead_conversion()")
    op.execute("""
        CREATE FUNCTION crm.repeat_phone_key(value text) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path=pg_catalog AS $$
            SELECT CASE WHEN value !~ '^[+0-9()[:space:].-]+$' THEN NULL
                WHEN digits ~ '^(91|0091)[0-9]{10}$' THEN right(digits, 10)
                ELSE digits END
            FROM (SELECT regexp_replace(value, '[^0-9]', '', 'g') AS digits) normalized
        $$
    """)
    op.execute("CREATE INDEX leads_converted_phone ON crm.leads (org_id, crm.repeat_phone_key(phone)) WHERE converted_at IS NOT NULL")
    op.execute("CREATE INDEX leads_converted_email ON crm.leads (org_id, (lower(btrim(email)))) WHERE converted_at IS NOT NULL")


def downgrade() -> None:
    raise RuntimeError("Destructive repeat-customer downgrade is disabled; use a reviewed forward migration or backup restore.")