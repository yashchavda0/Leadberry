"""Create the first tenant/identity foundation, not the complete CRM schema."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = (
    "CREATE SCHEMA crm",
    "REVOKE ALL ON SCHEMA crm FROM PUBLIC",
    """
    CREATE TABLE crm.app_users (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        email text NOT NULL UNIQUE CHECK (email = lower(btrim(email))),
        full_name text NOT NULL CHECK (length(full_name) BETWEEN 1 AND 200),
        password_hash text,
        email_verified_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE crm.organizations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{2,62}$'),
        name text NOT NULL,
        status text NOT NULL DEFAULT 'provisioning'
            CHECK (status IN ('provisioning', 'active', 'suspended', 'closed')),
        timezone text NOT NULL DEFAULT 'Asia/Kolkata',
        currency char(3) NOT NULL DEFAULT 'INR',
        profile jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(profile) = 'object'),
        authz_version bigint NOT NULL DEFAULT 1,
        settings_version bigint NOT NULL DEFAULT 1,
        administration_version bigint NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE crm.organization_memberships (
        org_id uuid NOT NULL REFERENCES crm.organizations(id),
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES crm.app_users(id),
        display_name text NOT NULL,
        phone text,
        status text NOT NULL DEFAULT 'invited' CHECK (status IN ('invited', 'active', 'disabled')),
        is_owner boolean NOT NULL DEFAULT false,
        visibility_override text CHECK (visibility_override IN ('own', 'team', 'all')),
        authz_version bigint NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (org_id, id),
        UNIQUE (org_id, user_id)
    )
    """,
    "CREATE INDEX memberships_user ON crm.organization_memberships (user_id, org_id)",
    """
    CREATE TABLE crm.lead_statuses (
        org_id uuid NOT NULL REFERENCES crm.organizations(id),
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        name text NOT NULL,
        category text NOT NULL CHECK (category IN ('new', 'pending', 'working', 'won', 'lost')),
        color text NOT NULL DEFAULT '#64748b' CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
        position integer NOT NULL DEFAULT 0,
        is_active boolean NOT NULL DEFAULT true,
        is_default boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (org_id, id),
        UNIQUE (org_id, name),
        CHECK (NOT is_default OR is_active)
    )
    """,
    "CREATE UNIQUE INDEX statuses_one_default ON crm.lead_statuses (org_id) WHERE is_default",
    """
    CREATE TABLE crm.organization_settings (
        org_id uuid PRIMARY KEY REFERENCES crm.organizations(id),
        active_metric_version integer NOT NULL DEFAULT 1 CHECK (active_metric_version > 0),
        require_mfa boolean NOT NULL DEFAULT false,
        lead_retention_days integer CHECK (lead_retention_days > 0),
        raw_payload_retention_days integer NOT NULL DEFAULT 30 CHECK (raw_payload_retention_days > 0),
        export_retention_hours integer NOT NULL DEFAULT 24 CHECK (export_retention_hours BETWEEN 1 AND 168),
        max_export_rows integer NOT NULL DEFAULT 1000000 CHECK (max_export_rows > 0),
        max_concurrent_exports integer NOT NULL DEFAULT 2 CHECK (max_concurrent_exports BETWEEN 1 AND 10),
        duplicate_policy jsonb NOT NULL DEFAULT '{"phone":"warn","email":"warn"}',
        security_policy jsonb NOT NULL DEFAULT '{}',
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE FUNCTION crm.current_org_id() RETURNS uuid
    LANGUAGE sql STABLE SET search_path = pg_catalog
    AS $$ SELECT nullif(current_setting('app.org_id', true), '')::uuid $$
    """,
    """
    CREATE FUNCTION crm.prevent_tenant_reparenting() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
        IF NEW.org_id IS DISTINCT FROM OLD.org_id THEN
            RAISE EXCEPTION 'Organization ownership is immutable' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$
    """,
    """
    CREATE FUNCTION crm.lock_administration() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    DECLARE target_org uuid;
    BEGIN
        IF TG_OP = 'UPDATE' AND NEW.org_id IS DISTINCT FROM OLD.org_id THEN
            RAISE EXCEPTION 'Organization ownership is immutable' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'DELETE' THEN target_org := OLD.org_id; ELSE target_org := NEW.org_id; END IF;
        UPDATE crm.organizations SET administration_version = administration_version + 1
        WHERE id = target_org;
        IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END;
    $$
    """,
    """
    CREATE FUNCTION crm.assert_active_organization() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    DECLARE target_org uuid;
    BEGIN
        IF TG_TABLE_NAME = 'organizations' THEN target_org := NEW.id;
        ELSIF TG_OP = 'DELETE' THEN target_org := OLD.org_id;
        ELSE target_org := NEW.org_id;
        END IF;
        IF EXISTS (SELECT 1 FROM crm.organizations WHERE id = target_org AND status = 'active') THEN
            IF NOT EXISTS (
                SELECT 1 FROM crm.organization_memberships
                WHERE org_id = target_org AND status = 'active' AND is_owner
            ) THEN
                RAISE EXCEPTION 'An active organization requires an active Owner' USING ERRCODE = '23514';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM crm.lead_statuses
                WHERE org_id = target_org AND is_default AND is_active
            ) THEN
                RAISE EXCEPTION 'An active organization requires a default status' USING ERRCODE = '23514';
            END IF;
        END IF;
        RETURN NULL;
    END;
    $$
    """,
    "ALTER TABLE crm.organizations ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE crm.organizations FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY tenant_boundary ON crm.organizations
    USING (id = crm.current_org_id()) WITH CHECK (id = crm.current_org_id())
    """,
    """
    CREATE CONSTRAINT TRIGGER organization_invariants AFTER INSERT OR UPDATE ON crm.organizations
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION crm.assert_active_organization()
    """,
)

TENANT_TABLES = ("organization_memberships", "lead_statuses", "organization_settings")


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE crm.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_boundary ON crm.{table} "
            "USING (org_id = crm.current_org_id()) WITH CHECK (org_id = crm.current_org_id())"
        )
        op.execute(
            f"CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.{table} "
            "FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
        )
    for table in ("organization_memberships", "lead_statuses"):
        op.execute(
            f"CREATE TRIGGER administration_lock BEFORE INSERT OR UPDATE OR DELETE ON crm.{table} "
            "FOR EACH ROW EXECUTE FUNCTION crm.lock_administration()"
        )
        op.execute(
            f"CREATE CONSTRAINT TRIGGER active_organization_invariants AFTER INSERT OR UPDATE OR DELETE ON crm.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION crm.assert_active_organization()"
        )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA crm FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA crm FROM PUBLIC")


def downgrade() -> None:
    raise RuntimeError("Foundation downgrade is destructive; use an approved backup/restore or forward migration")
