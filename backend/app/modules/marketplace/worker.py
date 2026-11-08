import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ...core.database import check_database_readiness, create_database_engine, tenant_transaction
from ...core.settings import Settings
from ..identity.service import AccessError, audit, effective_access
from . import indiamart, tradeindia
from .crypto import decrypt_credentials

logger = logging.getLogger(__name__)


async def claim(engine, org: UUID) -> dict | None:
    async with tenant_transaction(engine, org) as connection:
        if not await connection.scalar(text("SELECT id FROM crm.organizations WHERE id=:org AND status='active' FOR SHARE"), {"org": org}):
            return None
        await connection.execute(text("UPDATE crm.marketplace_sync_runs SET state='queued',lease_token=NULL,lease_until=NULL WHERE org_id=:org AND state='running' AND lease_until<now()"), {"org": org})
        await connection.execute(text(
            "INSERT INTO crm.marketplace_sync_runs(org_id,account_id,kind,credential_version) "
            "SELECT org_id,id,'sync',credential_version FROM crm.marketplace_accounts a "
                        "WHERE org_id=:org AND provider_code IN ('indiamart','tradeindia') AND status='active' AND next_allowed_at<=now() "
            "AND verified_version=credential_version AND NOT EXISTS(SELECT 1 FROM crm.marketplace_sync_runs r "
            "WHERE r.org_id=a.org_id AND r.account_id=a.id AND r.state IN ('queued','running')) ON CONFLICT DO NOTHING"
        ), {"org": org})
        row = (await connection.execute(text(
            "SELECT a.*,r.id AS run_id,r.kind FROM crm.marketplace_accounts a JOIN crm.marketplace_sync_runs r "
            "ON r.org_id=a.org_id AND r.account_id=a.id JOIN crm.organization_memberships m "
            "ON m.org_id=a.org_id AND m.id=a.created_by AND m.status='active' "
            "WHERE a.org_id=:org AND a.provider_code IN ('indiamart','tradeindia') AND a.status<>'retired' "
            "AND a.next_allowed_at<=now() AND r.state='queued' AND r.credential_version=a.credential_version "
            "AND (r.kind='test' OR a.status='active') ORDER BY r.created_at LIMIT 1 FOR UPDATE OF a SKIP LOCKED"
        ), {"org": org})).mappings().first()
        if row is None:
            return None
        values = dict(row)
        try:
            _, permissions, _, _ = await effective_access(connection, org, values["created_by"])
        except AccessError:
            permissions = frozenset()
        if "marketplace.manage" not in permissions:
            await connection.execute(text("UPDATE crm.marketplace_sync_runs SET state='cancelled',safe_error_code='integration_actor_inactive',finished_at=now() WHERE org_id=:org AND id=:id"), {"org": org, "id": values["run_id"]})
            return None
        reserved = await connection.scalar(text(
            "INSERT INTO crm.marketplace_rate_limits(fingerprint,next_allowed_at) VALUES(:key,now()+interval '5 minutes') "
            "ON CONFLICT(fingerprint) DO UPDATE SET next_allowed_at=excluded.next_allowed_at "
            "WHERE crm.marketplace_rate_limits.next_allowed_at<=now() RETURNING fingerprint"
        ), {"key": values["credential_fingerprint"]})
        if not reserved:
            return None
        token = uuid4()
        await connection.execute(text("UPDATE crm.marketplace_sync_runs SET state='running',lease_token=:token,lease_until=now()+interval '2 minutes' WHERE org_id=:org AND id=:id AND state='queued'"), {"org": org, "id": values["run_id"], "token": token})
        await connection.execute(text("UPDATE crm.marketplace_accounts SET next_allowed_at=now()+interval '5 minutes' WHERE org_id=:org AND id=:id"), {"org": org, "id": values["id"]})
        values["lease_token"] = token
        return values


async def finish(engine, org: UUID, run: dict, leads: list[dict], end: datetime, error: str | None = None) -> None:
    async with tenant_transaction(engine, org) as connection:
        await connection.execute(text("SELECT id FROM crm.organizations WHERE id=:org AND status='active' FOR SHARE"), {"org": org})
        current = (await connection.execute(text("SELECT status,credential_version,row_version FROM crm.marketplace_accounts WHERE org_id=:org AND id=:id FOR UPDATE"), {"org": org, "id": run["id"]})).mappings().first()
        valid = await connection.scalar(text("SELECT 1 FROM crm.marketplace_sync_runs WHERE org_id=:org AND id=:id AND state='running' AND lease_token=:token AND lease_until>now() FOR UPDATE"), {"org": org, "id": run["run_id"], "token": run["lease_token"]})
        if not valid:
            return
        try:
            _, permissions, _, _ = await effective_access(connection, org, run["created_by"])
        except AccessError:
            permissions = frozenset()
        if current is None or current["credential_version"] != run["credential_version"] or current["row_version"] != run["row_version"] or current["status"] == "retired" or "marketplace.manage" not in permissions:
            await connection.execute(text("UPDATE crm.marketplace_sync_runs SET state='cancelled',finished_at=now() WHERE org_id=:org AND id=:id"), {"org": org, "id": run["run_id"]})
            return
        accepted = 0
        if not error and run["kind"] == "sync":
            status = await connection.scalar(text("SELECT id FROM crm.lead_statuses WHERE org_id=:org AND is_active AND is_default"), {"org": org})
            if status is None:
                error = "integration_default_status_missing"
            else:
                assignee = None
                if run["default_assignee_membership_id"] is not None:
                    try:
                        _, assignee_permissions, _, _ = await effective_access(connection, org, run["default_assignee_membership_id"])
                    except AccessError:
                        assignee_permissions = frozenset()
                    if "leads.assign" in assignee_permissions:
                        assignee = run["default_assignee_membership_id"]
                for lead in leads:
                    values = {key: value for key, value in lead.items() if key != "source_time"}
                    values.update(org=org, account=run["id"], member=run["created_by"], status=status, assignee=assignee,
                                  source=run["provider_code"], custom=json.dumps({"source_query_time": lead["source_time"]}))
                    created = await connection.scalar(text(
                        "INSERT INTO crm.leads(org_id,integration_id,source_record_id,source_provider,created_by,status_id,"
                        "assigned_membership_id,name,company,phone,email,city,state,address,product,enquiry,custom_fields) "
                        "VALUES(:org,:account,:source_record_id,:source,:member,:status,:assignee,:name,:company,:phone,:email,"
                        ":city,:state,:address,:product,:enquiry,CAST(:custom AS jsonb)) "
                        "ON CONFLICT(org_id,integration_id,source_record_id) WHERE integration_id IS NOT NULL DO NOTHING RETURNING id"
                    ), values)
                    if created:
                        accepted += 1
                        await audit(connection, org, None, "marketplace.lead_received", created)
        parameters = {"org": org, "id": run["id"], "run": run["run_id"], "error": error, "accepted": accepted, "fetched": len(leads), "end": end}
        if error:
            await connection.execute(text("UPDATE crm.marketplace_accounts SET safe_error_code=:error,verified_version=NULL,status='error',row_version=row_version+1,updated_at=now() WHERE org_id=:org AND id=:id"), parameters)
        else:
            await connection.execute(text(
                "UPDATE crm.marketplace_accounts SET safe_error_code=NULL,last_success_at=now(),"
                "verified_version=credential_version,row_version=row_version+1,updated_at=now() "
                + (",watermark=:end,last_received_at=CASE WHEN :accepted>0 THEN now() ELSE last_received_at END " if run["kind"] == "sync" else "")
                + "WHERE org_id=:org AND id=:id"
            ), parameters)
        parameters["state"] = "failed" if error else "completed"
        await connection.execute(text("UPDATE crm.marketplace_sync_runs SET state=:state,safe_error_code=:error,fetched_count=:fetched,accepted_count=:accepted,finished_at=now() WHERE org_id=:org AND id=:run"), parameters)


async def process_once(engine, org: UUID, private: rsa.RSAPrivateKey, client: httpx.AsyncClient) -> bool:
    run = await claim(engine, org)
    if run is None:
        return False
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=5) if run["kind"] == "test" else run["watermark"] - timedelta(minutes=5)
    end = min(now, start + timedelta(days=7))
    try:
        if start < now - timedelta(days=365):
            raise AccessError(409, "provider_history_expired")
        credentials = decrypt_credentials(private, run["credential_envelope"], str(org), str(run["id"]), run["credential_version"])
        if run["provider_code"] == "tradeindia":
            config = run["config"] if isinstance(run["config"], dict) else json.loads(run["config"])
            leads = await tradeindia.fetch_leads(client, config, credentials["api_key"], start, end)
        else:
            leads = await indiamart.fetch_leads(client, credentials["crm_key"], start, end)
        await finish(engine, org, run, leads, end)
    except AccessError as error:
        await finish(engine, org, run, [], end, error.code)
    except (ValueError, KeyError, TypeError, InvalidTag):
        await finish(engine, org, run, [], end, "marketplace_key_unavailable")
    return True


async def main(arguments) -> None:
    settings = Settings()
    if settings.app_environment == "production":
        raise RuntimeError("Production connectors require a managed key-service implementation")
    private = serialization.load_pem_private_key(arguments.private_key.read_bytes(), password=None)
    if not isinstance(private, rsa.RSAPrivateKey) or private.key_size < 3072:
        raise RuntimeError("Worker key must be RSA 3072 or stronger")
    engine = create_database_engine(settings)
    try:
        if not await check_database_readiness(engine):
            raise RuntimeError("Worker schema or database role is not ready")
        async with engine.connect() as connection:
            if await connection.scalar(text("SELECT current_user")) != "crm_worker":
                raise RuntimeError("Worker must use its dedicated crm_worker database role")
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            while True:
                try:
                    did_work = await process_once(engine, arguments.organization, private, client)
                except SQLAlchemyError:
                    logger.error("marketplace_database_operation_failed")
                    did_work = False
                if arguments.once:
                    return
                await asyncio.sleep(1 if did_work else 10)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", type=UUID, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    asyncio.run(main(parser.parse_args()), loop_factory=asyncio.SelectorEventLoop if __import__("sys").platform == "win32" else None)