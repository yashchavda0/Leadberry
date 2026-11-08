-- Run only against a fresh disposable PostgreSQL database after the schema.
-- Requires a test administrator able to CREATE ROLE. All fixtures and the
-- non-login test role are rolled back; the crm schema is left unchanged.
BEGIN;

INSERT INTO crm.app_users (id, email, full_name)
VALUES ('20000000-0000-4000-8000-000000000001', 'schema-test@example.invalid', 'Schema Test');

INSERT INTO crm.organizations (id, slug, name)
VALUES
    ('10000000-0000-4000-8000-000000000001', 'schema-org-a', 'Schema A'),
    ('10000000-0000-4000-8000-000000000002', 'schema-org-b', 'Schema B');

INSERT INTO crm.organization_memberships (org_id, id, user_id, display_name, status, is_owner)
VALUES
    ('10000000-0000-4000-8000-000000000001', '30000000-0000-4000-8000-000000000001',
     '20000000-0000-4000-8000-000000000001', 'A Owner', 'active', true),
    ('10000000-0000-4000-8000-000000000002', '30000000-0000-4000-8000-000000000002',
     '20000000-0000-4000-8000-000000000001', 'B Owner', 'active', true);

INSERT INTO crm.lead_statuses (org_id, id, name, category, is_default)
VALUES
    ('10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000001', 'New', 'new', true),
    ('10000000-0000-4000-8000-000000000002', '40000000-0000-4000-8000-000000000002', 'New', 'new', true);

UPDATE crm.organizations SET status = 'active'
WHERE id IN ('10000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000002');
SET CONSTRAINTS ALL IMMEDIATE;
SET CONSTRAINTS ALL DEFERRED;

INSERT INTO crm.leads (org_id, id, status_id, source_channel, name, received_at)
VALUES
    ('10000000-0000-4000-8000-000000000001', '50000000-0000-4000-8000-000000000001',
     '40000000-0000-4000-8000-000000000001', 'manual', 'Lead A', now()),
    ('10000000-0000-4000-8000-000000000002', '50000000-0000-4000-8000-000000000001',
     '40000000-0000-4000-8000-000000000002', 'manual', 'Lead B', now());

DO $$
BEGIN
    BEGIN
        UPDATE crm.leads SET status_id = '40000000-0000-4000-8000-000000000002'
        WHERE org_id = '10000000-0000-4000-8000-000000000001';
        RAISE EXCEPTION 'FAIL: cross-tenant status accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        UPDATE crm.leads SET assigned_membership_id = '30000000-0000-4000-8000-000000000002'
        WHERE org_id = '10000000-0000-4000-8000-000000000001';
        RAISE EXCEPTION 'FAIL: cross-tenant assignee accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        UPDATE crm.organization_memberships SET is_owner = false
        WHERE org_id = '10000000-0000-4000-8000-000000000001';
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'FAIL: last Owner removed';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE crm.lead_statuses SET is_default = false
        WHERE org_id = '10000000-0000-4000-8000-000000000001';
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'FAIL: active organization lost default status';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE crm.leads SET org_id = '10000000-0000-4000-8000-000000000002'
        WHERE org_id = '10000000-0000-4000-8000-000000000001';
        RAISE EXCEPTION 'FAIL: tenant reparenting accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
END;
$$;

INSERT INTO crm.provider_catalog (code, name, category, verification_status)
VALUES ('schema-test', 'Schema Provider', 'api', 'needs_verification');
INSERT INTO crm.integrations (org_id, id, provider_code, name, created_by)
VALUES ('10000000-0000-4000-8000-000000000001', '60000000-0000-4000-8000-000000000001',
        'schema-test', 'Schema Integration', '30000000-0000-4000-8000-000000000001');
INSERT INTO crm.integration_mapping_versions (org_id, integration_id, version, mapping, changed_by)
VALUES ('10000000-0000-4000-8000-000000000001', '60000000-0000-4000-8000-000000000001',
        1, '{}', '30000000-0000-4000-8000-000000000001');
INSERT INTO crm.lead_source_records (org_id, integration_id, external_id, lead_id)
VALUES ('10000000-0000-4000-8000-000000000001', '60000000-0000-4000-8000-000000000001',
        'external-1', '50000000-0000-4000-8000-000000000001');

DO $$
BEGIN
    BEGIN
        INSERT INTO crm.lead_source_records (org_id, integration_id, external_id, lead_id)
        VALUES ('10000000-0000-4000-8000-000000000001', '60000000-0000-4000-8000-000000000001',
                'external-1', '50000000-0000-4000-8000-000000000001');
        RAISE EXCEPTION 'FAIL: duplicate source identity accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
END;
$$;

INSERT INTO crm.ingestion_receipts
    (org_id, integration_id, dedupe_key, request_hash, mapping_version, inline_payload)
VALUES ('10000000-0000-4000-8000-000000000001', '60000000-0000-4000-8000-000000000001',
        'delivery-1', decode(repeat('00', 32), 'hex'), 1, '{"name":"example"}');
DO $$
BEGIN
    BEGIN
        INSERT INTO crm.ingestion_receipts
            (org_id, integration_id, dedupe_key, request_hash, mapping_version, inline_payload)
        VALUES ('10000000-0000-4000-8000-000000000001', '60000000-0000-4000-8000-000000000001',
                'delivery-1', decode(repeat('00', 32), 'hex'), 1, '{"name":"example"}');
        RAISE EXCEPTION 'FAIL: repeated delivery accepted as new';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
END;
$$;

UPDATE crm.leads SET name = 'Updated A'
WHERE org_id = '10000000-0000-4000-8000-000000000001' AND row_version = 1;
DO $$
DECLARE affected bigint;
BEGIN
    UPDATE crm.leads SET name = 'Stale A'
    WHERE org_id = '10000000-0000-4000-8000-000000000001' AND row_version = 1;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 0 THEN RAISE EXCEPTION 'FAIL: stale row version accepted'; END IF;
END;
$$;

INSERT INTO crm.lead_daily_rollups
    (org_id, metric_version, day, source_provider, status_id, status_category, lead_count)
VALUES ('10000000-0000-4000-8000-000000000001', 1, current_date, 'manual',
        '40000000-0000-4000-8000-000000000001', 'new', 1);
DO $$
BEGIN
    BEGIN
        INSERT INTO crm.lead_daily_rollups
            (org_id, metric_version, day, source_provider, status_id, status_category, lead_count)
        VALUES ('10000000-0000-4000-8000-000000000001', 1, current_date, 'manual',
                '40000000-0000-4000-8000-000000000001', 'new', 2);
        RAISE EXCEPTION 'FAIL: duplicate unassigned rollup accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
END;
$$;

CREATE ROLE crm_schema_smoke_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA crm TO crm_schema_smoke_runtime;
GRANT SELECT, INSERT, UPDATE ON crm.leads TO crm_schema_smoke_runtime;
GRANT EXECUTE ON FUNCTION crm.current_org_id() TO crm_schema_smoke_runtime;
SELECT set_config('app.org_id', '', true);
SET LOCAL ROLE crm_schema_smoke_runtime;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM crm.leads) THEN
        RAISE EXCEPTION 'FAIL: rows visible without tenant context';
    END IF;
END;
$$;
SELECT set_config('app.org_id', '10000000-0000-4000-8000-000000000001', true);
DO $$
BEGIN
    IF (SELECT count(*) FROM crm.leads) <> 1
       OR EXISTS (SELECT 1 FROM crm.leads WHERE name <> 'Updated A') THEN
        RAISE EXCEPTION 'FAIL: tenant read isolation';
    END IF;
    BEGIN
        INSERT INTO crm.leads (org_id, status_id, source_channel, received_at)
        VALUES ('10000000-0000-4000-8000-000000000002',
                '40000000-0000-4000-8000-000000000002', 'manual', now());
        RAISE EXCEPTION 'FAIL: cross-tenant insert permitted';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END;
$$;
RESET ROLE;

DO $$
BEGIN
    IF (SELECT crm.resolve_organization_slug('schema-org-a'))
        IS DISTINCT FROM '10000000-0000-4000-8000-000000000001'::uuid THEN
        RAISE EXCEPTION 'FAIL: authentication routing';
    END IF;
    RAISE NOTICE 'PASS: schema smoke checks (not multi-connection concurrency or load tests)';
END;
$$;
ROLLBACK;
