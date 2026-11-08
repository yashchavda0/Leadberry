-- Reference baseline for a NEW PostgreSQL 16+ database.
-- Not an application migration. Do not apply to the existing SQLite database.
-- Runtime role grants, encryption keys, partitions and organization seeds are
-- deployment/onboarding concerns described in CRM-ARCHITECTURE.md.
BEGIN;
CREATE SCHEMA crm;
REVOKE ALL ON SCHEMA crm FROM PUBLIC;
SET LOCAL search_path = crm, pg_catalog;

CREATE TABLE app_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL CHECK (email = lower(btrim(email))),
    full_name text NOT NULL CHECK (length(full_name) BETWEEN 1 AND 200),
    password_hash text,
    email_verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (email)
);

CREATE TABLE organizations (
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
);

CREATE TABLE platform_operators (
    user_id uuid PRIMARY KEY REFERENCES app_users(id),
    access_level text NOT NULL CHECK (access_level IN ('support', 'administrator')),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- A deliberately minimal, non-tenant routing directory for authentication.
-- No organization profile or customer data is exposed through it.
CREATE TABLE organization_directory (
    slug text PRIMARY KEY,
    organization_id uuid NOT NULL UNIQUE REFERENCES organizations(id)
);

CREATE TABLE organization_memberships (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app_users(id),
    display_name text NOT NULL,
    phone text,
    status text NOT NULL DEFAULT 'invited'
        CHECK (status IN ('invited', 'active', 'disabled')),
    is_owner boolean NOT NULL DEFAULT false,
    visibility_override text CHECK (visibility_override IN ('own', 'team', 'all')),
    landing_page text CHECK (landing_page IN ('/', '/leads', '/users', '/settings', '/marketplace', '/account')),
    authz_version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, user_id)
);
CREATE INDEX memberships_user ON organization_memberships (user_id, org_id);

CREATE TABLE permissions (
    code text PRIMARY KEY,
    module text NOT NULL,
    page text NOT NULL,
    action text NOT NULL,
    description text NOT NULL,
    is_delegable boolean NOT NULL DEFAULT true
);

CREATE TABLE roles (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    description text,
    data_scope text NOT NULL DEFAULT 'own' CHECK (data_scope IN ('own', 'team', 'all')),
    is_active boolean NOT NULL DEFAULT true,
    reports_to_role_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, name),
    FOREIGN KEY (org_id, reports_to_role_id) REFERENCES roles(org_id, id),
    CHECK (reports_to_role_id IS DISTINCT FROM id)
);
CREATE INDEX roles_parent ON roles (org_id, reports_to_role_id);

CREATE TABLE role_permissions (
    org_id uuid NOT NULL,
    role_id uuid NOT NULL,
    permission_code text NOT NULL REFERENCES permissions(code),
    PRIMARY KEY (org_id, role_id, permission_code),
    FOREIGN KEY (org_id, role_id) REFERENCES roles(org_id, id)
);

CREATE TABLE membership_roles (
    org_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    role_id uuid NOT NULL,
    PRIMARY KEY (org_id, membership_id, role_id),
    FOREIGN KEY (org_id, membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, role_id) REFERENCES roles(org_id, id)
);
CREATE INDEX membership_roles_reverse ON membership_roles (org_id, role_id, membership_id);

CREATE TABLE membership_permission_overrides (
    org_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    permission_code text NOT NULL REFERENCES permissions(code),
    allowed boolean NOT NULL,
    changed_by uuid NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, membership_id, permission_code),
    FOREIGN KEY (org_id, membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, changed_by) REFERENCES organization_memberships(org_id, id)
);

CREATE TABLE teams (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, name)
);

CREATE TABLE team_memberships (
    org_id uuid NOT NULL,
    team_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    PRIMARY KEY (org_id, team_id, membership_id),
    FOREIGN KEY (org_id, team_id) REFERENCES teams(org_id, id),
    FOREIGN KEY (org_id, membership_id) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX team_memberships_reverse ON team_memberships (org_id, membership_id, team_id);

CREATE TABLE organization_settings (
    org_id uuid PRIMARY KEY REFERENCES organizations(id),
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
);

CREATE TABLE auth_sessions (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    membership_id uuid NOT NULL,
    refresh_family_id uuid NOT NULL DEFAULT gen_random_uuid(),
    csrf_token_hash bytea NOT NULL CHECK (octet_length(csrf_token_hash) = 32),
    mfa_verified_at timestamptz,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, membership_id) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX auth_sessions_membership ON auth_sessions (org_id, membership_id, expires_at);

CREATE TABLE session_refresh_tokens (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
    consumed_at timestamptz,
    revoked_at timestamptz,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, session_id) REFERENCES auth_sessions(org_id, id)
);
CREATE INDEX refresh_tokens_session ON session_refresh_tokens (org_id, session_id, expires_at);

CREATE TABLE auth_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app_users(id),
    purpose text NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
    token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE organization_invitations (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    membership_id uuid NOT NULL,
    invited_by uuid NOT NULL,
    token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, invited_by) REFERENCES organization_memberships(org_id, id)
);

CREATE TABLE user_mfa_factors (
    user_id uuid NOT NULL REFERENCES app_users(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    ciphertext bytea NOT NULL,
    nonce bytea NOT NULL CHECK (octet_length(nonce) = 12),
    wrapped_data_key bytea NOT NULL,
    key_reference text NOT NULL,
    verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, id)
);

CREATE TABLE mfa_recovery_codes (
    user_id uuid NOT NULL REFERENCES app_users(id),
    code_hash bytea NOT NULL CHECK (octet_length(code_hash) = 32),
    consumed_at timestamptz,
    PRIMARY KEY (user_id, code_hash)
);

CREATE TABLE provider_catalog (
    code text PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL CHECK (category IN ('marketplace', 'social', 'form', 'commerce', 'api', 'telephony')),
    verification_status text NOT NULL CHECK (verification_status IN ('contract_verified', 'needs_verification')),
    capabilities jsonb NOT NULL DEFAULT '{}',
    config_schema jsonb NOT NULL DEFAULT '{}',
    documentation_url text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integrations (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    provider_code text NOT NULL REFERENCES provider_catalog(code),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'error', 'retired')),
    config jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(config) = 'object'),
    intake_policy jsonb NOT NULL DEFAULT '{"existing":"preserve_manual_fields"}',
    mapping_version integer NOT NULL DEFAULT 1 CHECK (mapping_version > 0),
    credential_version integer NOT NULL DEFAULT 1 CHECK (credential_version > 0),
    authz_version bigint NOT NULL DEFAULT 1,
    created_by uuid NOT NULL,
    last_received_at timestamptz,
    last_success_at timestamptz,
    safe_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, name),
    FOREIGN KEY (org_id, created_by) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX integrations_provider ON integrations (org_id, provider_code, status);

CREATE TABLE encrypted_secrets (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    integration_id uuid,
    purpose text NOT NULL,
    ciphertext bytea NOT NULL,
    nonce bytea NOT NULL CHECK (octet_length(nonce) = 12),
    wrapped_data_key bytea NOT NULL,
    key_reference text NOT NULL,
    algorithm text NOT NULL DEFAULT 'AES-256-GCM' CHECK (algorithm = 'AES-256-GCM'),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    display_suffix text,
    retired_at timestamptz,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    FOREIGN KEY (org_id, created_by) REFERENCES organization_memberships(org_id, id)
);
CREATE UNIQUE INDEX secrets_current_integration ON encrypted_secrets (org_id, integration_id, purpose)
    WHERE retired_at IS NULL AND integration_id IS NOT NULL;

CREATE TABLE api_keys (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    integration_id uuid NOT NULL,
    created_by uuid NOT NULL,
    name text NOT NULL,
    prefix text NOT NULL UNIQUE,
    secret_hash bytea NOT NULL UNIQUE CHECK (octet_length(secret_hash) = 32),
    pepper_version integer NOT NULL DEFAULT 1,
    data_scope text NOT NULL DEFAULT 'own' CHECK (data_scope IN ('own', 'team', 'all')),
    expires_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    FOREIGN KEY (org_id, created_by) REFERENCES organization_memberships(org_id, id)
);

CREATE TABLE api_key_scopes (
    org_id uuid NOT NULL,
    api_key_id uuid NOT NULL,
    permission_code text NOT NULL REFERENCES permissions(code),
    PRIMARY KEY (org_id, api_key_id, permission_code),
    FOREIGN KEY (org_id, api_key_id) REFERENCES api_keys(org_id, id)
);

CREATE TABLE webhook_routes (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    integration_id uuid NOT NULL,
    public_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    verification_mode text NOT NULL CHECK (verification_mode IN ('hmac', 'oauth_provider', 'bearer')),
    signing_secret_id uuid,
    bearer_hash bytea CHECK (bearer_hash IS NULL OR octet_length(bearer_hash) = 32),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    FOREIGN KEY (org_id, signing_secret_id) REFERENCES encrypted_secrets(org_id, id),
    CHECK (
        (verification_mode = 'bearer' AND bearer_hash IS NOT NULL AND signing_secret_id IS NULL)
        OR (verification_mode IN ('hmac', 'oauth_provider') AND signing_secret_id IS NOT NULL AND bearer_hash IS NULL)
    )
);

CREATE TABLE api_key_directory (
    prefix text PRIMARY KEY,
    organization_id uuid NOT NULL,
    api_key_id uuid NOT NULL,
    FOREIGN KEY (organization_id, api_key_id) REFERENCES api_keys(org_id, id)
);

CREATE TABLE webhook_directory (
    public_id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    route_id uuid NOT NULL,
    FOREIGN KEY (organization_id, route_id) REFERENCES webhook_routes(org_id, id)
);

CREATE TABLE integration_mapping_versions (
    org_id uuid NOT NULL,
    integration_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    mapping jsonb NOT NULL CHECK (jsonb_typeof(mapping) = 'object'),
    changed_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, integration_id, version),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    FOREIGN KEY (org_id, changed_by) REFERENCES organization_memberships(org_id, id)
);

CREATE TABLE connector_cursors (
    org_id uuid NOT NULL,
    integration_id uuid NOT NULL,
    committed_watermark timestamptz,
    provider_cursor jsonb NOT NULL DEFAULT '{}',
    next_allowed_at timestamptz NOT NULL DEFAULT now(),
    lease_token uuid,
    lease_until timestamptz,
    generation bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (org_id, integration_id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id)
);

CREATE TABLE integration_sync_runs (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    integration_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('incremental', 'backfill', 'manual')),
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    attempt integer NOT NULL DEFAULT 0,
    lease_token uuid,
    lease_until timestamptz,
    fetched_count bigint NOT NULL DEFAULT 0,
    accepted_count bigint NOT NULL DEFAULT 0,
    safe_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    CHECK (window_start < window_end)
);
CREATE INDEX sync_runs_history ON integration_sync_runs (org_id, integration_id, created_at DESC, id DESC);

CREATE TABLE lead_statuses (
    org_id uuid NOT NULL REFERENCES organizations(id),
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
);
CREATE UNIQUE INDEX statuses_one_default ON lead_statuses (org_id) WHERE is_default;

CREATE TABLE custom_field_definitions (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    field_key text NOT NULL CHECK (field_key ~ '^[a-z][a-z0-9_]{0,62}$'),
    label text NOT NULL,
    field_type text NOT NULL
        CHECK (field_type IN ('text', 'number', 'email', 'phone', 'date', 'select', 'multiselect', 'boolean', 'url')),
    is_required boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    is_filterable boolean NOT NULL DEFAULT false,
    is_visible_in_table boolean NOT NULL DEFAULT false,
    is_sensitive boolean NOT NULL DEFAULT false,
    position integer NOT NULL DEFAULT 0,
    validation jsonb NOT NULL DEFAULT '{}',
    definition_version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, field_key)
);

CREATE TABLE custom_field_options (
    org_id uuid NOT NULL,
    field_id uuid NOT NULL,
    option_key text NOT NULL,
    label text NOT NULL,
    position integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, field_id, option_key),
    FOREIGN KEY (org_id, field_id) REFERENCES custom_field_definitions(org_id, id)
);

CREATE TABLE assignment_rules (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    method text NOT NULL CHECK (method IN ('round_robin', 'least_open', 'fixed')),
    priority integer NOT NULL,
    conditions jsonb NOT NULL DEFAULT '{}',
    is_active boolean NOT NULL DEFAULT true,
    rotation_counter bigint NOT NULL DEFAULT 0,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, name)
);
CREATE INDEX assignment_rules_order ON assignment_rules (org_id, priority, id) WHERE is_active;

CREATE TABLE assignment_rule_members (
    org_id uuid NOT NULL,
    rule_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    position integer NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, rule_id, membership_id),
    FOREIGN KEY (org_id, rule_id) REFERENCES assignment_rules(org_id, id),
    FOREIGN KEY (org_id, membership_id) REFERENCES organization_memberships(org_id, id)
);

CREATE TABLE leads (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    status_id uuid NOT NULL,
    integration_id uuid,
    source_channel text NOT NULL CHECK (source_channel IN ('marketplace', 'social', 'form', 'commerce', 'api', 'telephony', 'manual', 'import')),
    source_provider text REFERENCES provider_catalog(code),
    name text,
    company text,
    phone text,
    phone_lookup_hash bytea CHECK (phone_lookup_hash IS NULL OR octet_length(phone_lookup_hash) = 32),
    email text,
    email_lookup_hash bytea CHECK (email_lookup_hash IS NULL OR octet_length(email_lookup_hash) = 32),
    country char(2),
    state text,
    city text,
    address text,
    postal_code text,
    enquiry text,
    subject text,
    product text,
    query_type text,
    extra_contact_data jsonb NOT NULL DEFAULT '{}',
    custom_fields jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(custom_fields) = 'object'),
    field_provenance jsonb NOT NULL DEFAULT '{}',
    assigned_membership_id uuid,
    assigned_at timestamptz,
    received_at timestamptz NOT NULL,
    last_source_at timestamptz,
    next_follow_up_at timestamptz,
    archived_at timestamptz,
    deleted_at timestamptz,
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    search_document tsvector GENERATED ALWAYS AS (
        to_tsvector('simple'::regconfig,
            coalesce(name, '') || ' ' || coalesce(company, '') || ' ' ||
            coalesce(product, '') || ' ' || coalesce(city, ''))
    ) STORED,
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, status_id) REFERENCES lead_statuses(org_id, id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    FOREIGN KEY (org_id, assigned_membership_id) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX leads_received ON leads (org_id, received_at DESC, id DESC) WHERE deleted_at IS NULL AND archived_at IS NULL;
CREATE INDEX leads_status ON leads (org_id, status_id, received_at DESC, id DESC) WHERE deleted_at IS NULL AND archived_at IS NULL;
CREATE INDEX leads_assignee ON leads (org_id, assigned_membership_id, received_at DESC, id DESC) WHERE deleted_at IS NULL AND archived_at IS NULL;
CREATE INDEX leads_source ON leads (org_id, source_provider, received_at DESC, id DESC) WHERE deleted_at IS NULL AND archived_at IS NULL;
CREATE INDEX leads_integration ON leads (org_id, integration_id, received_at DESC, id DESC);
CREATE INDEX leads_phone ON leads (org_id, phone_lookup_hash) WHERE phone_lookup_hash IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX leads_email ON leads (org_id, email_lookup_hash) WHERE email_lookup_hash IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX leads_search ON leads USING gin (search_document);
CREATE INDEX leads_custom_fields ON leads USING gin (custom_fields jsonb_path_ops);
CREATE INDEX leads_modified ON leads (org_id, updated_at, id);

CREATE TABLE lead_source_records (
    org_id uuid NOT NULL,
    integration_id uuid NOT NULL,
    external_id text NOT NULL CHECK (length(external_id) BETWEEN 1 AND 512),
    lead_id uuid NOT NULL,
    latest_source_version text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, integration_id, external_id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id)
);
CREATE INDEX lead_source_records_lead ON lead_source_records (org_id, lead_id);

CREATE TABLE tags (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    color text NOT NULL DEFAULT '#3b82f6' CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    is_active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, name)
);

CREATE TABLE lead_tags (
    org_id uuid NOT NULL,
    lead_id uuid NOT NULL,
    tag_id uuid NOT NULL,
    added_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, lead_id, tag_id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, tag_id) REFERENCES tags(org_id, id),
    FOREIGN KEY (org_id, added_by) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX lead_tags_filter ON lead_tags (org_id, tag_id, lead_id);

CREATE TABLE lead_shares (
    org_id uuid NOT NULL,
    lead_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    granted_by uuid NOT NULL,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, lead_id, membership_id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, granted_by) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX lead_shares_member ON lead_shares (org_id, membership_id, lead_id);

CREATE TABLE lead_activities (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL,
    actor_membership_id uuid,
    integration_id uuid,
    event_type text NOT NULL,
    lead_version bigint NOT NULL,
    old_values jsonb NOT NULL DEFAULT '{}',
    new_values jsonb NOT NULL DEFAULT '{}',
    note text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, actor_membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    UNIQUE (org_id, lead_id, lead_version, event_type)
);
CREATE INDEX lead_activities_timeline ON lead_activities (org_id, lead_id, occurred_at DESC, id DESC);
CREATE INDEX lead_activities_reports ON lead_activities (org_id, event_type, occurred_at, id);

CREATE TABLE lead_assignment_history (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL,
    old_membership_id uuid,
    new_membership_id uuid,
    actor_membership_id uuid,
    rule_id uuid,
    assignment_type text NOT NULL CHECK (assignment_type IN ('manual', 'automatic', 'unassign')),
    lead_version bigint NOT NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, old_membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, new_membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, actor_membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, rule_id) REFERENCES assignment_rules(org_id, id),
    UNIQUE (org_id, lead_id, lead_version)
);
CREATE INDEX assignment_history_lead ON lead_assignment_history (org_id, lead_id, assigned_at DESC, id DESC);

CREATE TABLE follow_ups (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL,
    assigned_membership_id uuid NOT NULL,
    created_by uuid NOT NULL,
    due_at timestamptz NOT NULL,
    note text,
    completed_at timestamptz,
    cancelled_at timestamptz,
    row_version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, assigned_membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, created_by) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX follow_ups_due ON follow_ups (org_id, assigned_membership_id, due_at, id)
    WHERE completed_at IS NULL AND cancelled_at IS NULL;
CREATE INDEX follow_ups_lead ON follow_ups (org_id, lead_id, due_at)
    WHERE completed_at IS NULL AND cancelled_at IS NULL;

CREATE TABLE duplicate_candidates (
    org_id uuid NOT NULL,
    lead_a uuid NOT NULL,
    lead_b uuid NOT NULL,
    reason text NOT NULL CHECK (reason IN ('phone', 'email', 'manual')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'dismissed', 'merged')),
    reviewed_by uuid,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, lead_a, lead_b, reason),
    FOREIGN KEY (org_id, lead_a) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, lead_b) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, reviewed_by) REFERENCES organization_memberships(org_id, id),
    CHECK (lead_a < lead_b)
);

CREATE TABLE ingestion_receipts (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    integration_id uuid NOT NULL,
    dedupe_key text NOT NULL CHECK (length(dedupe_key) BETWEEN 1 AND 512),
    request_hash bytea NOT NULL CHECK (octet_length(request_hash) = 32),
    mapping_version integer NOT NULL,
    payload_object_key text,
    inline_payload jsonb,
    state text NOT NULL DEFAULT 'accepted'
        CHECK (state IN ('accepted', 'processing', 'processed', 'rejected', 'dead_letter')),
    attempt integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_token uuid,
    lease_until timestamptz,
    result_lead_id uuid,
    safe_error_code text,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    payload_purged_at timestamptz,
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, integration_id, dedupe_key),
    FOREIGN KEY (org_id, integration_id) REFERENCES integrations(org_id, id),
    FOREIGN KEY (org_id, integration_id, mapping_version)
        REFERENCES integration_mapping_versions(org_id, integration_id, version),
    FOREIGN KEY (org_id, result_lead_id) REFERENCES leads(org_id, id),
    CHECK (
        (payload_purged_at IS NULL AND ((inline_payload IS NULL) <> (payload_object_key IS NULL)))
        OR (payload_purged_at IS NOT NULL AND inline_payload IS NULL AND payload_object_key IS NULL)
    )
);
CREATE INDEX ingestion_pending ON ingestion_receipts (org_id, available_at, id)
    WHERE state IN ('accepted', 'processing');
CREATE INDEX ingestion_history ON ingestion_receipts (org_id, integration_id, received_at DESC, id DESC);

CREATE TABLE outbox_events (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    topic text NOT NULL,
    aggregate_id uuid NOT NULL,
    aggregate_version bigint NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    available_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, topic, aggregate_id, aggregate_version)
);
CREATE INDEX outbox_pending ON outbox_events (org_id, available_at, id) WHERE published_at IS NULL;

CREATE TABLE consumer_checkpoints (
    org_id uuid NOT NULL,
    consumer_name text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, consumer_name, event_id),
    FOREIGN KEY (org_id, event_id) REFERENCES outbox_events(org_id, id)
);

CREATE TABLE saved_lead_views (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    created_by uuid NOT NULL,
    name text NOT NULL,
    visibility text NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'organization')),
    filter_version integer NOT NULL DEFAULT 1,
    filters jsonb NOT NULL DEFAULT '{}',
    columns jsonb NOT NULL DEFAULT '[]',
    sort jsonb NOT NULL DEFAULT '[]',
    row_version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, created_by) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX saved_views_owner ON saved_lead_views (org_id, created_by);

CREATE TABLE async_jobs (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    requested_by uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('export', 'bulk_update', 'import', 'snapshot_report')),
    operation_key uuid NOT NULL,
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    filter_version integer NOT NULL DEFAULT 1,
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'expired')),
    scope_fingerprint text NOT NULL,
    org_authz_version bigint NOT NULL,
    member_authz_version bigint NOT NULL,
    cutoff_at timestamptz NOT NULL DEFAULT now(),
    snapshot_at timestamptz,
    lease_token uuid,
    lease_until timestamptz,
    attempt integer NOT NULL DEFAULT 0,
    rows_processed bigint NOT NULL DEFAULT 0 CHECK (rows_processed >= 0),
    rows_failed bigint NOT NULL DEFAULT 0 CHECK (rows_failed >= 0),
    safe_error_code text,
    cancel_requested_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    expires_at timestamptz,
    PRIMARY KEY (org_id, id),
    UNIQUE (org_id, requested_by, operation_key),
    FOREIGN KEY (org_id, requested_by) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX jobs_user_history ON async_jobs (org_id, requested_by, created_at DESC, id DESC);
CREATE INDEX jobs_queue ON async_jobs (org_id, state, created_at, id);

CREATE TABLE job_artifacts (
    org_id uuid NOT NULL,
    job_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    object_key text NOT NULL,
    file_name text NOT NULL,
    mime_type text NOT NULL,
    byte_count bigint NOT NULL CHECK (byte_count >= 0),
    row_count bigint NOT NULL CHECK (row_count >= 0),
    checksum_sha256 bytea NOT NULL CHECK (octet_length(checksum_sha256) = 32),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, job_id) REFERENCES async_jobs(org_id, id)
);
CREATE INDEX artifacts_job ON job_artifacts (org_id, job_id);

CREATE TABLE job_lead_manifest (
    org_id uuid NOT NULL,
    job_id uuid NOT NULL,
    lead_id uuid NOT NULL,
    lead_version bigint NOT NULL,
    PRIMARY KEY (org_id, job_id, lead_id),
    FOREIGN KEY (org_id, job_id) REFERENCES async_jobs(org_id, id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id)
);
CREATE INDEX job_manifest_lead ON job_lead_manifest (org_id, lead_id, job_id);

CREATE TABLE reporting_lead_facts (
    org_id uuid NOT NULL,
    metric_version integer NOT NULL CHECK (metric_version > 0),
    lead_id uuid NOT NULL,
    last_lead_version bigint NOT NULL,
    acquired_at timestamptz NOT NULL,
    acquired_day date NOT NULL,
    source_provider text NOT NULL,
    status_id uuid NOT NULL,
    status_category text NOT NULL CHECK (status_category IN ('new', 'pending', 'working', 'won', 'lost')),
    assigned_membership_id uuid,
    excluded boolean NOT NULL DEFAULT false,
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, metric_version, lead_id),
    FOREIGN KEY (org_id, lead_id) REFERENCES leads(org_id, id),
    FOREIGN KEY (org_id, status_id) REFERENCES lead_statuses(org_id, id),
    FOREIGN KEY (org_id, assigned_membership_id) REFERENCES organization_memberships(org_id, id)
);
CREATE INDEX reporting_facts_scope ON reporting_lead_facts (org_id, metric_version, assigned_membership_id, acquired_day);

CREATE TABLE lead_daily_rollups (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    metric_version integer NOT NULL,
    day date NOT NULL,
    source_provider text NOT NULL,
    status_id uuid NOT NULL,
    status_category text NOT NULL CHECK (status_category IN ('new', 'pending', 'working', 'won', 'lost')),
    assigned_membership_id uuid,
    lead_count bigint NOT NULL CHECK (lead_count >= 0),
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, status_id) REFERENCES lead_statuses(org_id, id),
    FOREIGN KEY (org_id, assigned_membership_id) REFERENCES organization_memberships(org_id, id),
    UNIQUE NULLS NOT DISTINCT (org_id, metric_version, day, source_provider, status_id, status_category, assigned_membership_id)
);
CREATE INDEX rollups_scope ON lead_daily_rollups (org_id, assigned_membership_id, day, metric_version);

CREATE TABLE webhook_subscriptions (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    created_by uuid NOT NULL,
    target_url text NOT NULL CHECK (target_url ~ '^https://'),
    signing_secret_id uuid NOT NULL,
    event_types text[] NOT NULL CHECK (cardinality(event_types) > 0),
    data_scope text NOT NULL DEFAULT 'own' CHECK (data_scope IN ('own', 'team', 'all')),
    include_pii boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, created_by) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, signing_secret_id) REFERENCES encrypted_secrets(org_id, id)
);

CREATE TABLE webhook_deliveries (
    org_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    subscription_id uuid NOT NULL,
    event_id uuid NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'delivered', 'failed', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_token uuid,
    lease_until timestamptz,
    response_code integer,
    safe_error_code text,
    delivered_at timestamptz,
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, subscription_id) REFERENCES webhook_subscriptions(org_id, id),
    FOREIGN KEY (org_id, event_id) REFERENCES outbox_events(org_id, id),
    UNIQUE (org_id, subscription_id, event_id)
);
CREATE INDEX webhook_pending ON webhook_deliveries (org_id, next_attempt_at, id)
    WHERE state IN ('queued', 'running');

CREATE TABLE audit_logs (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    actor_membership_id uuid,
    actor_api_key_id uuid,
    request_id uuid NOT NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid,
    changes jsonb NOT NULL DEFAULT '{}',
    ip_address inet,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, actor_membership_id) REFERENCES organization_memberships(org_id, id),
    FOREIGN KEY (org_id, actor_api_key_id) REFERENCES api_keys(org_id, id)
);
CREATE INDEX audit_time ON audit_logs (org_id, occurred_at DESC, id DESC);
CREATE INDEX audit_actor ON audit_logs (org_id, actor_membership_id, occurred_at DESC, id DESC);

CREATE TABLE platform_audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_user_id uuid NOT NULL REFERENCES platform_operators(user_id),
    target_org_id uuid REFERENCES organizations(id),
    action text NOT NULL,
    request_id uuid NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}',
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION current_org_id() RETURNS uuid
LANGUAGE sql STABLE
SET search_path = pg_catalog
AS $$ SELECT nullif(current_setting('app.org_id', true), '')::uuid $$;

-- Credential-checked authentication uses a separate restricted DB role.
-- This routing function reveals only the UUID for a public organization slug.
CREATE FUNCTION resolve_organization_slug(p_slug text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog
AS $$ SELECT organization_id FROM crm.organization_directory WHERE slug = p_slug $$;
REVOKE ALL ON FUNCTION resolve_organization_slug(text) FROM PUBLIC;

CREATE FUNCTION sync_organization_directory() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    INSERT INTO crm.organization_directory(slug, organization_id) VALUES (NEW.slug, NEW.id)
    ON CONFLICT (organization_id) DO UPDATE SET slug = EXCLUDED.slug;
    RETURN NEW;
END;
$$;
CREATE TRIGGER organization_route AFTER INSERT OR UPDATE OF slug ON organizations
    FOR EACH ROW EXECUTE FUNCTION sync_organization_directory();

CREATE FUNCTION sync_credential_directory() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_TABLE_NAME = 'api_keys' THEN
        INSERT INTO crm.api_key_directory(prefix, organization_id, api_key_id)
        VALUES (NEW.prefix, NEW.org_id, NEW.id);
    ELSE
        INSERT INTO crm.webhook_directory(public_id, organization_id, route_id)
        VALUES (NEW.public_id, NEW.org_id, NEW.id);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER api_key_route AFTER INSERT ON api_keys
    FOR EACH ROW EXECUTE FUNCTION sync_credential_directory();
CREATE TRIGGER webhook_route AFTER INSERT ON webhook_routes
    FOR EACH ROW EXECUTE FUNCTION sync_credential_directory();

CREATE FUNCTION advance_lead_version() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.org_id IS DISTINCT FROM OLD.org_id OR NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'Lead identity is immutable' USING ERRCODE = '23514';
    END IF;
    NEW.row_version := OLD.row_version + 1;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
CREATE TRIGGER leads_version BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION advance_lead_version();

CREATE FUNCTION prevent_tenant_reparenting() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.org_id IS DISTINCT FROM OLD.org_id THEN
        RAISE EXCEPTION 'Organization ownership is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION lock_membership_organization() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
DECLARE
    target_org uuid;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.org_id IS DISTINCT FROM OLD.org_id THEN
        RAISE EXCEPTION 'Membership organization is immutable' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN target_org := OLD.org_id; ELSE target_org := NEW.org_id; END IF;
    -- A real row update also fences concurrent snapshot-isolation transactions.
    UPDATE crm.organizations SET administration_version = administration_version + 1
    WHERE id = target_org;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;
CREATE TRIGGER membership_org_lock BEFORE INSERT OR UPDATE OR DELETE ON organization_memberships
    FOR EACH ROW EXECUTE FUNCTION lock_membership_organization();

CREATE FUNCTION assert_active_owner() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
DECLARE
    target_org uuid;
BEGIN
    IF TG_TABLE_NAME = 'organizations' THEN
        target_org := NEW.id;
    ELSIF TG_OP = 'DELETE' THEN
        target_org := OLD.org_id;
    ELSE
        target_org := NEW.org_id;
    END IF;
    IF EXISTS (SELECT 1 FROM crm.organizations WHERE id = target_org AND status = 'active')
       AND NOT EXISTS (
           SELECT 1 FROM crm.organization_memberships
           WHERE org_id = target_org AND status = 'active' AND is_owner
       ) THEN
        RAISE EXCEPTION 'An active organization requires an active Owner' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER membership_owner_required
    AFTER INSERT OR UPDATE OR DELETE ON organization_memberships
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_active_owner();
CREATE CONSTRAINT TRIGGER organization_owner_required
    AFTER INSERT OR UPDATE ON organizations
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_active_owner();

CREATE FUNCTION assert_default_status() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
DECLARE
    target_org uuid;
BEGIN
    IF TG_TABLE_NAME = 'organizations' THEN target_org := NEW.id;
    ELSIF TG_OP = 'DELETE' THEN target_org := OLD.org_id;
    ELSE target_org := NEW.org_id;
    END IF;
    IF EXISTS (SELECT 1 FROM crm.organizations WHERE id = target_org AND status = 'active')
       AND NOT EXISTS (SELECT 1 FROM crm.lead_statuses WHERE org_id = target_org AND is_default AND is_active) THEN
        RAISE EXCEPTION 'An active organization requires an active default lead status' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER status_org_lock BEFORE INSERT OR UPDATE OR DELETE ON lead_statuses
    FOR EACH ROW EXECUTE FUNCTION lock_membership_organization();
CREATE CONSTRAINT TRIGGER status_default_required
    AFTER INSERT OR UPDATE OR DELETE ON lead_statuses
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_default_status();
CREATE CONSTRAINT TRIGGER organization_default_required
    AFTER INSERT OR UPDATE ON organizations
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_default_status();

-- Policies isolate tenants; row visibility and action permissions are ALSO
-- applied by service queries. Never connect runtime code as the schema owner.
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_boundary ON organizations
    USING (id = crm.current_org_id()) WITH CHECK (id = crm.current_org_id());

DO $$
DECLARE
    tab record;
BEGIN
    FOR tab IN
        SELECT table_name FROM information_schema.columns
        WHERE table_schema = 'crm' AND column_name = 'org_id'
    LOOP
        EXECUTE format('ALTER TABLE crm.%I ENABLE ROW LEVEL SECURITY', tab.table_name);
        EXECUTE format('ALTER TABLE crm.%I FORCE ROW LEVEL SECURITY', tab.table_name);
        EXECUTE format(
            'CREATE POLICY tenant_boundary ON crm.%I USING (org_id = crm.current_org_id()) WITH CHECK (org_id = crm.current_org_id())',
            tab.table_name
        );
        EXECUTE format(
            'CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.%I FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()',
            tab.table_name
        );
    END LOOP;
END;
$$;
REVOKE ALL ON ALL TABLES IN SCHEMA crm FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA crm FROM PUBLIC;
COMMIT;
