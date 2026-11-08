"""Membership sessions, roles, invitations and access audit."""

from alembic import op
from sqlalchemy import text

revision = "0002_identity"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

PERMISSION_CODES = (
    "dashboard.view", "leads.view", "leads.create", "leads.edit", "leads.assign",
    "leads.share", "leads.archive", "leads.restore", "leads.delete", "leads.import",
    "leads.export", "leads.pii.view", "reports.view", "reports.export",
    "api_integrations.view", "api_integrations.manage", "api_keys.manage",
    "marketplace.view", "marketplace.manage", "marketplace.replay",
    "users.view", "users.manage", "roles.view", "roles.manage",
    "settings.view", "settings.manage", "assignment_rules.manage", "audit.view", "audit.export",
)

TABLES = {
    "permissions": """
        code text PRIMARY KEY, module text NOT NULL, page text NOT NULL,
        action text NOT NULL, description text NOT NULL, is_delegable boolean NOT NULL DEFAULT true
    """,
    "organization_directory": """
        slug text PRIMARY KEY, organization_id uuid NOT NULL UNIQUE REFERENCES crm.organizations(id)
    """,
    "roles": """
        org_id uuid NOT NULL REFERENCES crm.organizations(id), id uuid NOT NULL DEFAULT gen_random_uuid(),
        name text NOT NULL, description text, data_scope text NOT NULL DEFAULT 'own'
        CHECK (data_scope IN ('own','team','all')), is_active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(org_id,id), UNIQUE(org_id,name)
    """,
    "role_permissions": """
        org_id uuid NOT NULL, role_id uuid NOT NULL, permission_code text NOT NULL REFERENCES crm.permissions(code),
        PRIMARY KEY(org_id,role_id,permission_code),
        FOREIGN KEY(org_id,role_id) REFERENCES crm.roles(org_id,id)
    """,
    "membership_roles": """
        org_id uuid NOT NULL, membership_id uuid NOT NULL, role_id uuid NOT NULL,
        PRIMARY KEY(org_id,membership_id,role_id),
        FOREIGN KEY(org_id,membership_id) REFERENCES crm.organization_memberships(org_id,id),
        FOREIGN KEY(org_id,role_id) REFERENCES crm.roles(org_id,id)
    """,
    "membership_permission_overrides": """
        org_id uuid NOT NULL, membership_id uuid NOT NULL,
        permission_code text NOT NULL REFERENCES crm.permissions(code), allowed boolean NOT NULL,
        changed_by uuid NOT NULL, changed_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(org_id,membership_id,permission_code),
        FOREIGN KEY(org_id,membership_id) REFERENCES crm.organization_memberships(org_id,id),
        FOREIGN KEY(org_id,changed_by) REFERENCES crm.organization_memberships(org_id,id)
    """,
    "auth_sessions": """
        org_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), membership_id uuid NOT NULL,
        csrf_token_hash bytea NOT NULL CHECK(octet_length(csrf_token_hash)=32),
        expires_at timestamptz NOT NULL, revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(org_id,id),
        FOREIGN KEY(org_id,membership_id) REFERENCES crm.organization_memberships(org_id,id)
    """,
    "session_refresh_tokens": """
        org_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), session_id uuid NOT NULL,
        token_hash bytea NOT NULL UNIQUE CHECK(octet_length(token_hash)=32),
        consumed_at timestamptz, revoked_at timestamptz, expires_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(org_id,id),
        FOREIGN KEY(org_id,session_id) REFERENCES crm.auth_sessions(org_id,id)
    """,
    "organization_invitations": """
        org_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), membership_id uuid NOT NULL,
        invited_by uuid NOT NULL, token_hash bytea NOT NULL UNIQUE CHECK(octet_length(token_hash)=32),
        expires_at timestamptz NOT NULL, consumed_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(org_id,id),
        FOREIGN KEY(org_id,membership_id) REFERENCES crm.organization_memberships(org_id,id),
        FOREIGN KEY(org_id,invited_by) REFERENCES crm.organization_memberships(org_id,id)
    """,
    "auth_rate_limits": """
        bucket_key bytea PRIMARY KEY CHECK(octet_length(bucket_key)=32),
        attempts integer NOT NULL CHECK(attempts>0), window_end timestamptz NOT NULL
    """,
    "audit_logs": """
        org_id uuid NOT NULL REFERENCES crm.organizations(id), id uuid NOT NULL DEFAULT gen_random_uuid(),
        actor_membership_id uuid, request_id uuid NOT NULL, action text NOT NULL,
        entity_type text NOT NULL, entity_id uuid, changes jsonb NOT NULL DEFAULT '{}',
        occurred_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(org_id,id),
        FOREIGN KEY(org_id,actor_membership_id) REFERENCES crm.organization_memberships(org_id,id)
    """,
}

TENANT_TABLES = (
    "roles", "role_permissions", "membership_roles", "membership_permission_overrides",
    "auth_sessions", "session_refresh_tokens", "organization_invitations", "audit_logs",
)


def upgrade() -> None:
    for name, definition in TABLES.items():
        op.execute(f"CREATE TABLE crm.{name} ({definition})")
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE crm.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_boundary ON crm.{table} USING (org_id = crm.current_org_id()) "
            "WITH CHECK (org_id = crm.current_org_id())"
        )
        op.execute(
            f"CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.{table} "
            "FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
        )
    op.execute("""
        CREATE FUNCTION crm.sync_organization_directory() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        BEGIN
            INSERT INTO crm.organization_directory(slug,organization_id) VALUES(NEW.slug,NEW.id)
            ON CONFLICT(organization_id) DO UPDATE SET slug=EXCLUDED.slug;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER organization_route AFTER INSERT OR UPDATE OF slug ON crm.organizations
        FOR EACH ROW EXECUTE FUNCTION crm.sync_organization_directory()
    """)
    # The migration owner backfills routing under the transactional DDL lock.
    op.execute("ALTER TABLE crm.organizations NO FORCE ROW LEVEL SECURITY")
    op.execute("INSERT INTO crm.organization_directory(slug,organization_id) SELECT slug,id FROM crm.organizations")
    op.execute("ALTER TABLE crm.organizations FORCE ROW LEVEL SECURITY")
    op.execute("CREATE INDEX roles_members ON crm.membership_roles(org_id,role_id,membership_id)")
    op.execute("CREATE INDEX sessions_member ON crm.auth_sessions(org_id,membership_id,expires_at)")
    op.execute("CREATE INDEX session_tokens_session ON crm.session_refresh_tokens(org_id,session_id)")
    op.execute("CREATE INDEX invitations_member ON crm.organization_invitations(org_id,membership_id)")
    op.execute("CREATE INDEX audit_time ON crm.audit_logs(org_id,occurred_at DESC,id DESC)")
    op.execute("CREATE INDEX auth_rate_limit_expiry ON crm.auth_rate_limits(window_end)")
    for code in PERMISSION_CODES:
        module, action = code.split(".", 1)
        op.execute(
            text("INSERT INTO crm.permissions(code,module,page,action,description) "
                 "VALUES(:code,:module,:module,:action,:code)")
            .bindparams(code=code, module=module, action=action)
        )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA crm FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA crm FROM PUBLIC")


def downgrade() -> None:
    raise RuntimeError("Identity downgrade would destroy access data; use a reviewed forward migration")
