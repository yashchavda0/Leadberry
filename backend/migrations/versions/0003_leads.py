"""Add scoped lead storage and organization teams."""

from alembic import op

revision = "0003_leads"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crm.teams (
            org_id uuid NOT NULL REFERENCES crm.organizations(id),
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
            is_active boolean NOT NULL DEFAULT true,
            PRIMARY KEY(org_id,id), UNIQUE(org_id,name)
        )
    """)
    op.execute("""
        CREATE TABLE crm.team_memberships (
            org_id uuid NOT NULL, team_id uuid NOT NULL, membership_id uuid NOT NULL,
            PRIMARY KEY(org_id,team_id,membership_id),
            FOREIGN KEY(org_id,team_id) REFERENCES crm.teams(org_id,id),
            FOREIGN KEY(org_id,membership_id) REFERENCES crm.organization_memberships(org_id,id)
        )
    """)
    op.execute("CREATE INDEX team_memberships_reverse ON crm.team_memberships(org_id,membership_id,team_id)")
    op.execute("""
        CREATE TABLE crm.leads (
            org_id uuid NOT NULL REFERENCES crm.organizations(id),
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            name text NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
            company text NOT NULL DEFAULT '', phone text NOT NULL DEFAULT '',
            email text NOT NULL DEFAULT '', city text NOT NULL DEFAULT '',
            state text NOT NULL DEFAULT '', address text NOT NULL DEFAULT '',
            product text NOT NULL DEFAULT '', enquiry text NOT NULL DEFAULT '',
            source_provider text NOT NULL DEFAULT 'manual' CHECK(length(source_provider) BETWEEN 1 AND 100),
            status_id uuid NOT NULL, assigned_membership_id uuid, team_id uuid,
            created_by uuid NOT NULL,
            tags text[] NOT NULL DEFAULT '{}' CHECK(cardinality(tags)<=20),
            custom_fields jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(custom_fields)='object'),
            next_follow_up_at timestamptz, archived_at timestamptz,
            row_version bigint NOT NULL DEFAULT 1 CHECK(row_version>0),
            received_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            search_document tsvector GENERATED ALWAYS AS (
                to_tsvector('simple'::regconfig,name || ' ' || company || ' ' || product || ' ' || city)
            ) STORED,
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,status_id) REFERENCES crm.lead_statuses(org_id,id),
            FOREIGN KEY(org_id,assigned_membership_id) REFERENCES crm.organization_memberships(org_id,id),
            FOREIGN KEY(org_id,created_by) REFERENCES crm.organization_memberships(org_id,id),
            FOREIGN KEY(org_id,team_id) REFERENCES crm.teams(org_id,id)
        )
    """)
    for name, columns in (
        ("received", "received_at DESC,id DESC"),
        ("status", "status_id,received_at DESC,id DESC"),
        ("assignee", "assigned_membership_id,received_at DESC,id DESC"),
        ("creator", "created_by,received_at DESC,id DESC"),
        ("team", "team_id,received_at DESC,id DESC"),
        ("source", "source_provider,received_at DESC,id DESC"),
    ):
        op.execute(f"CREATE INDEX leads_{name} ON crm.leads(org_id,{columns}) WHERE archived_at IS NULL")
    op.execute("CREATE INDEX leads_search ON crm.leads USING gin(search_document)")
    op.execute("CREATE INDEX leads_tags ON crm.leads USING gin(tags)")
    for table in ("teams", "team_memberships", "leads"):
        op.execute(f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE crm.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_boundary ON crm.{table} USING(org_id=crm.current_org_id()) "
            "WITH CHECK(org_id=crm.current_org_id())"
        )
        op.execute(
            f"CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.{table} "
            "FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
        )


def downgrade() -> None:
    raise RuntimeError("Destructive lead downgrade is disabled; use a reviewed forward migration or backup restore.")
