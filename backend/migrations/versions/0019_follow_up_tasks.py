"""Track follow-up tasks while preserving the lead follow-up timestamp."""

from alembic import op

revision = "0019_follow_up_tasks"
down_revision = "0018_member_personal_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crm.follow_up_tasks (
            org_id uuid NOT NULL,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            lead_id uuid NOT NULL,
            assigned_membership_id uuid,
            due_at timestamptz NOT NULL,
            state text NOT NULL DEFAULT 'open' CHECK(state IN ('open','completed','cancelled')),
            note text NOT NULL DEFAULT '' CHECK(length(note)<=2000),
            completed_by uuid,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            row_version bigint NOT NULL DEFAULT 1 CHECK(row_version>0),
            PRIMARY KEY(org_id,id),
            FOREIGN KEY(org_id,lead_id) REFERENCES crm.leads(org_id,id) ON DELETE CASCADE,
            FOREIGN KEY(org_id,assigned_membership_id) REFERENCES crm.organization_memberships(org_id,id),
            FOREIGN KEY(org_id,completed_by) REFERENCES crm.organization_memberships(org_id,id),
            CHECK ((state='completed') = (completed_at IS NOT NULL AND completed_by IS NOT NULL))
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX follow_up_one_open ON crm.follow_up_tasks(org_id,lead_id) WHERE state='open'"
    )
    op.execute(
        "CREATE INDEX follow_up_queue ON crm.follow_up_tasks(org_id,due_at,id) WHERE state='open'"
    )
    op.execute(
        "CREATE INDEX follow_up_history ON crm.follow_up_tasks(org_id,lead_id,created_at DESC,id DESC)"
    )
    op.execute("ALTER TABLE crm.follow_up_tasks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE crm.follow_up_tasks FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_boundary ON crm.follow_up_tasks USING(org_id=crm.current_org_id()) WITH CHECK(org_id=crm.current_org_id())"
    )
    op.execute(
        "CREATE TRIGGER immutable_org BEFORE UPDATE ON crm.follow_up_tasks FOR EACH ROW EXECUTE FUNCTION crm.prevent_tenant_reparenting()"
    )
    op.execute("GRANT SELECT,INSERT,UPDATE ON crm.follow_up_tasks TO crm_api")
    op.execute("""
        DO $$
        DECLARE tenant record;
        BEGIN
            FOR tenant IN SELECT organization_id FROM crm.organization_directory LOOP
                PERFORM set_config('app.org_id', tenant.organization_id::text, true);
                INSERT INTO crm.follow_up_tasks(org_id,lead_id,assigned_membership_id,due_at)
                SELECT org_id,id,assigned_membership_id,next_follow_up_at
                FROM crm.leads WHERE org_id=tenant.organization_id
                  AND next_follow_up_at IS NOT NULL AND archived_at IS NULL;
            END LOOP;
            PERFORM set_config('app.org_id', '', true);
        END $$
    """)
    op.execute("""
        CREATE FUNCTION crm.sync_lead_follow_up() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,crm AS $$
        BEGIN
            IF NEW.next_follow_up_at IS NULL OR NEW.archived_at IS NOT NULL THEN
                IF TG_OP='UPDATE' AND (OLD.next_follow_up_at IS NOT NULL AND OLD.archived_at IS NULL) THEN
                    UPDATE crm.follow_up_tasks SET state='cancelled',updated_at=now(),row_version=row_version+1
                    WHERE org_id=NEW.org_id AND lead_id=NEW.id AND state='open';
                END IF;
            ELSE
                INSERT INTO crm.follow_up_tasks(org_id,lead_id,assigned_membership_id,due_at)
                VALUES(NEW.org_id,NEW.id,NEW.assigned_membership_id,NEW.next_follow_up_at)
                ON CONFLICT(org_id,lead_id) WHERE state='open' DO UPDATE
                SET due_at=EXCLUDED.due_at,assigned_membership_id=EXCLUDED.assigned_membership_id,
                    updated_at=now(),row_version=crm.follow_up_tasks.row_version+1
                WHERE crm.follow_up_tasks.due_at IS DISTINCT FROM EXCLUDED.due_at
                   OR crm.follow_up_tasks.assigned_membership_id IS DISTINCT FROM EXCLUDED.assigned_membership_id;
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute(
        "CREATE TRIGGER leads_sync_follow_up AFTER INSERT OR UPDATE OF next_follow_up_at,assigned_membership_id,archived_at ON crm.leads FOR EACH ROW EXECUTE FUNCTION crm.sync_lead_follow_up()"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive follow-up downgrade is disabled; use a reviewed forward migration or backup restore."
    )
