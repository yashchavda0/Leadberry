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

from ...core.database import (
    check_database_readiness,
    create_database_engine,
    tenant_transaction,
)
from ...core.settings import Settings
from ..identity.service import AccessError, audit, effective_access
from . import indiamart, tradeindia
from .catalog import provider
from .crypto import decrypt_credentials

logger = logging.getLogger(__name__)

# A run's provider work is cut off well before its lease expires, so an expired lease always means a dead worker.
LEASE_SECONDS = 600
FETCH_TIMEOUT_SECONDS = 300
MAX_CONCURRENT_RUNS = 8
ADAPTERS = "('indiamart','tradeindia')"


def interval(code: str) -> int:
    return provider(code).get("min_interval_seconds", 300)


def cooldown(code: str) -> int:
    return provider(code).get("cooldown_seconds", interval(code))


# Provider-side hiccups: retried on the normal schedule without un-verifying the connection.
TRANSIENT_ERRORS = {"provider_rate_limited", "provider_unavailable", "provider_timeout"}


async def claim(engine, org: UUID) -> dict | None:
    async with tenant_transaction(engine, org) as connection:
        if not await connection.scalar(
            text(
                "SELECT id FROM crm.organizations WHERE id=:org AND status='active' FOR SHARE"
            ),
            {"org": org},
        ):
            return None
        await connection.execute(
            text(
                "UPDATE crm.marketplace_sync_runs SET state='queued',lease_token=NULL,lease_until=NULL WHERE org_id=:org AND state='running' AND lease_until<now()"
            ),
            {"org": org},
        )
        await connection.execute(
            text(
                "INSERT INTO crm.marketplace_sync_runs(org_id,account_id,kind,credential_version) "
                "SELECT org_id,id,'sync',credential_version FROM crm.marketplace_accounts a "
                f"WHERE org_id=:org AND provider_code IN {ADAPTERS} AND status='active' AND next_allowed_at<=now() "
                "AND verified_version=credential_version AND NOT EXISTS(SELECT 1 FROM crm.marketplace_sync_runs r "
                "WHERE r.org_id=a.org_id AND r.account_id=a.id AND r.state IN ('queued','running')) ON CONFLICT DO NOTHING"
            ),
            {"org": org},
        )
        while True:
            # Only runs that can start now are picked, so one throttled key never blocks the rest of the queue.
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT a.*,r.id AS run_id,r.kind FROM crm.marketplace_accounts a JOIN crm.marketplace_sync_runs r "
                            "ON r.org_id=a.org_id AND r.account_id=a.id JOIN crm.organization_memberships m "
                            "ON m.org_id=a.org_id AND m.id=a.created_by AND m.status='active' "
                            f"WHERE a.org_id=:org AND a.provider_code IN {ADAPTERS} AND a.status<>'retired' "
                            "AND a.next_allowed_at<=now() AND r.state='queued' AND r.credential_version=a.credential_version "
                            "AND (r.kind='test' OR a.status='active') AND NOT EXISTS(SELECT 1 FROM crm.marketplace_rate_limits l "
                            "WHERE l.fingerprint=a.credential_fingerprint AND l.next_allowed_at>now()) "
                            "ORDER BY r.created_at LIMIT 1 FOR UPDATE OF a,r SKIP LOCKED"
                        ),
                        {"org": org},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            values = dict(row)
            try:
                _, permissions, _, _ = await effective_access(
                    connection, org, values["created_by"]
                )
            except AccessError:
                permissions = frozenset()
            if "marketplace.manage" in permissions:
                break
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_sync_runs SET state='cancelled',safe_error_code='integration_actor_inactive',finished_at=now() WHERE org_id=:org AND id=:id"
                ),
                {"org": org, "id": values["run_id"]},
            )
        gap = interval(values["provider_code"])
        reserved = await connection.scalar(
            text(
                "INSERT INTO crm.marketplace_rate_limits(fingerprint,next_allowed_at) VALUES(:key,now()+make_interval(secs=>:gap)) "
                "ON CONFLICT(fingerprint) DO UPDATE SET next_allowed_at=excluded.next_allowed_at "
                "WHERE crm.marketplace_rate_limits.next_allowed_at<=now() RETURNING fingerprint"
            ),
            {"key": values["credential_fingerprint"], "gap": gap},
        )
        if not reserved:
            return None
        token = uuid4()
        await connection.execute(
            text(
                "UPDATE crm.marketplace_sync_runs SET state='running',lease_token=:token,lease_until=now()+make_interval(secs=>:lease) WHERE org_id=:org AND id=:id AND state='queued'"
            ),
            {
                "org": org,
                "id": values["run_id"],
                "token": token,
                "lease": LEASE_SECONDS,
            },
        )
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET next_allowed_at=now()+make_interval(secs=>:gap) WHERE org_id=:org AND id=:id"
            ),
            {"org": org, "id": values["id"], "gap": gap},
        )
        values["lease_token"] = token
        return values


async def finish(
    engine,
    org: UUID,
    run: dict,
    leads: list[dict],
    end: datetime,
    error: str | None = None,
) -> None:
    async with tenant_transaction(engine, org) as connection:
        await connection.execute(
            text(
                "SELECT id FROM crm.organizations WHERE id=:org AND status='active' FOR SHARE"
            ),
            {"org": org},
        )
        current = (
            (
                await connection.execute(
                    text(
                        "SELECT status,credential_version,row_version FROM crm.marketplace_accounts WHERE org_id=:org AND id=:id FOR UPDATE"
                    ),
                    {"org": org, "id": run["id"]},
                )
            )
            .mappings()
            .first()
        )
        valid = await connection.scalar(
            text(
                "SELECT 1 FROM crm.marketplace_sync_runs WHERE org_id=:org AND id=:id AND state='running' AND lease_token=:token AND lease_until>now() FOR UPDATE"
            ),
            {"org": org, "id": run["run_id"], "token": run["lease_token"]},
        )
        if not valid:
            return
        try:
            _, permissions, _, _ = await effective_access(
                connection, org, run["created_by"]
            )
        except AccessError:
            permissions = frozenset()
        if (
            current is None
            or current["credential_version"] != run["credential_version"]
            or current["row_version"] != run["row_version"]
            or current["status"] == "retired"
            or "marketplace.manage" not in permissions
        ):
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_sync_runs SET state='cancelled',finished_at=now() WHERE org_id=:org AND id=:id"
                ),
                {"org": org, "id": run["run_id"]},
            )
            return
        accepted = 0
        if not error and run["kind"] == "sync":
            status = await connection.scalar(
                text(
                    "SELECT id FROM crm.lead_statuses WHERE org_id=:org AND is_active AND is_default"
                ),
                {"org": org},
            )
            if status is None:
                error = "integration_default_status_missing"
            else:
                assignee = None
                if run["default_assignee_membership_id"] is not None:
                    try:
                        _, assignee_permissions, _, _ = await effective_access(
                            connection, org, run["default_assignee_membership_id"]
                        )
                    except AccessError:
                        assignee_permissions = frozenset()
                    if "leads.assign" in assignee_permissions:
                        assignee = run["default_assignee_membership_id"]
                for lead in leads:
                    values = {
                        key: value
                        for key, value in lead.items()
                        if key != "source_time"
                    }
                    values.update(
                        org=org,
                        account=run["id"],
                        member=run["created_by"],
                        status=status,
                        assignee=assignee,
                        source=run["provider_code"],
                        custom=json.dumps({"source_query_time": lead["source_time"]}),
                    )
                    created = await connection.scalar(
                        text(
                            "INSERT INTO crm.leads(org_id,integration_id,source_record_id,source_provider,created_by,status_id,"
                            "assigned_membership_id,name,company,phone,email,city,state,address,product,enquiry,custom_fields) "
                            "VALUES(:org,:account,:source_record_id,:source,:member,:status,:assignee,:name,:company,:phone,:email,"
                            ":city,:state,:address,:product,:enquiry,CAST(:custom AS jsonb)) "
                            "ON CONFLICT(org_id,integration_id,source_record_id) WHERE integration_id IS NOT NULL DO NOTHING RETURNING id"
                        ),
                        values,
                    )
                    if created:
                        accepted += 1
                        await audit(
                            connection, org, None, "marketplace.lead_received", created
                        )
        parameters = {
            "org": org,
            "id": run["id"],
            "run": run["run_id"],
            "error": error,
            "accepted": accepted,
            "fetched": len(leads),
            "end": end,
        }
        if error in TRANSIENT_ERRORS:
            parameters["cooldown"] = cooldown(run["provider_code"]) if error == "provider_rate_limited" else 0
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_accounts SET safe_error_code=:error,row_version=row_version+1,updated_at=now(),"
                    "next_allowed_at=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)) WHERE org_id=:org AND id=:id"
                ),
                parameters,
            )
            if parameters["cooldown"]:
                await connection.execute(
                    text(
                        "UPDATE crm.marketplace_rate_limits SET next_allowed_at=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)) "
                        "WHERE fingerprint=:fingerprint"
                    ),
                    {"cooldown": parameters["cooldown"], "fingerprint": run["credential_fingerprint"]},
                )
        elif error:
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_accounts SET safe_error_code=:error,verified_version=NULL,status='error',row_version=row_version+1,updated_at=now() WHERE org_id=:org AND id=:id"
                ),
                parameters,
            )
        else:
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_accounts SET safe_error_code=NULL,last_success_at=now(),"
                    "status=CASE WHEN status='error' THEN 'draft' ELSE status END,"
                    "verified_version=credential_version,row_version=row_version+1,updated_at=now() "
                    + (
                        ",watermark=:end,last_received_at=CASE WHEN :accepted>0 THEN now() ELSE last_received_at END "
                        if run["kind"] == "sync"
                        else ""
                    )
                    + "WHERE org_id=:org AND id=:id"
                ),
                parameters,
            )
        parameters["state"] = "failed" if error else "completed"
        await connection.execute(
            text(
                "UPDATE crm.marketplace_sync_runs SET state=:state,safe_error_code=:error,fetched_count=:fetched,accepted_count=:accepted,finished_at=now() WHERE org_id=:org AND id=:run"
            ),
            parameters,
        )


async def process_once(
    engine, org: UUID, private: rsa.RSAPrivateKey, client: httpx.AsyncClient
) -> bool:
    run = await claim(engine, org)
    if run is None:
        return False
    await execute(engine, org, run, private, client)
    return True


async def execute(
    engine, org: UUID, run: dict, private: rsa.RSAPrivateKey, client: httpx.AsyncClient
) -> None:
    now = datetime.now(timezone.utc)
    start = (
        now - timedelta(minutes=5)
        if run["kind"] == "test"
        else run["watermark"] - timedelta(minutes=5)
    )
    end = min(now, start + timedelta(days=7))
    try:
        if start < now - timedelta(days=365):
            raise AccessError(409, "provider_history_expired")
        credentials = decrypt_credentials(
            private,
            run["credential_envelope"],
            str(org),
            str(run["id"]),
            run["credential_version"],
        )
        if run["provider_code"] == "tradeindia":
            config = (
                run["config"]
                if isinstance(run["config"], dict)
                else json.loads(run["config"])
            )
            fetch = tradeindia.fetch_leads(
                client, config, credentials["api_key"], start, end
            )
        else:
            fetch = indiamart.fetch_leads(client, credentials["crm_key"], start, end)
        try:
            async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
                leads = await fetch
        except TimeoutError:
            raise AccessError(504, "provider_timeout") from None
        await finish(engine, org, run, leads, end)
    except AccessError as error:
        await finish(engine, org, run, [], end, error.code)
    except (ValueError, KeyError, TypeError, InvalidTag):
        await finish(engine, org, run, [], end, "marketplace_key_unavailable")
    except SQLAlchemyError:
        raise
    except Exception:
        logger.exception(
            "marketplace_run_failed_unexpectedly provider=%s", run["provider_code"]
        )
        await finish(engine, org, run, [], end, "connector_internal_error")


async def heartbeat(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO crm.marketplace_worker_heartbeat(id,last_seen_at) VALUES(true,now()) "
                "ON CONFLICT(id) DO UPDATE SET last_seen_at=excluded.last_seen_at"
            )
        )


async def organizations(engine) -> list[UUID]:
    async with engine.connect() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "SELECT organization_id FROM crm.organization_directory ORDER BY organization_id"
                    )
                )
            ).scalars()
        )


async def run_safely(
    engine, org: UUID, run: dict, private: rsa.RSAPrivateKey, client: httpx.AsyncClient
) -> None:
    try:
        await execute(engine, org, run, private, client)
    except Exception:
        # The lease expires and the run is re-queued, so nothing stays stuck.
        logger.exception("marketplace_run_failed_unexpectedly run=%s", run["run_id"])


async def dispatch(
    engine,
    targets: list[UUID],
    private: rsa.RSAPrivateKey,
    client: httpx.AsyncClient,
    running: set[asyncio.Task],
) -> bool:
    started = False
    for org in targets:
        while len(running) < MAX_CONCURRENT_RUNS:
            try:
                run = await claim(engine, org)
            except Exception:
                logger.exception("marketplace_claim_failed org=%s", org)
                break
            if run is None:
                break
            task = asyncio.create_task(run_safely(engine, org, run, private, client))
            running.add(task)
            task.add_done_callback(running.discard)
            started = True
    return started


async def wait_until_ready(engine) -> None:
    while True:
        try:
            async with engine.connect() as connection:
                role = await connection.scalar(text("SELECT current_user"))
            if role != "crm_worker":
                raise RuntimeError(
                    "Worker must use its dedicated crm_worker database role"
                )
            if await check_database_readiness(engine):
                return
            logger.error(
                "marketplace_worker_waiting_for_database reason=schema_not_ready"
            )
        except SQLAlchemyError:
            logger.error("marketplace_worker_waiting_for_database reason=unavailable")
        await asyncio.sleep(10)


async def main(arguments) -> None:
    settings = Settings()
    if settings.app_environment == "production":
        raise RuntimeError(
            "Production connectors require a managed key-service implementation"
        )
    private = serialization.load_pem_private_key(
        arguments.private_key.read_bytes(), password=None
    )
    if not isinstance(private, rsa.RSAPrivateKey) or private.key_size < 3072:
        raise RuntimeError("Worker key must be RSA 3072 or stronger")
    engine = create_database_engine(settings)
    running: set[asyncio.Task] = set()
    try:
        await wait_until_ready(engine)
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=False, trust_env=False
        ) as client:
            logger.warning(
                "marketplace_worker_started scope=%s",
                arguments.organization or "all-organizations",
            )
            while True:
                started = False
                try:
                    await heartbeat(engine)
                    targets = (
                        [arguments.organization]
                        if arguments.organization
                        else await organizations(engine)
                    )
                    started = await dispatch(engine, targets, private, client, running)
                except Exception:
                    logger.exception("marketplace_worker_cycle_failed")
                if arguments.once:
                    if running:
                        await asyncio.gather(*running)
                    return
                await asyncio.sleep(1 if started else 5)
    finally:
        for task in running:
            task.cancel()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--organization",
        type=UUID,
        help="Limit the worker to one organization (default: all)",
    )
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    asyncio.run(
        main(parser.parse_args()),
        loop_factory=(
            asyncio.SelectorEventLoop if __import__("sys").platform == "win32" else None
        ),
    )
