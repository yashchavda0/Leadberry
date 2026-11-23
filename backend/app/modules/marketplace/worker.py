import argparse
import asyncio
import hashlib
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
from ..leads.assignment_rules import route_new_lead
from . import adapters, indiamart
from .catalog import provider
from .crypto import decrypt_credentials
from .schedule import (
    IST,
    LIVE_SLIP_SECONDS,
    MAX_WINDOW_ATTEMPTS,
    backoff,
    history_floor,
    ist_midnight,
    live_window,
    plan_windows,
    slot_seconds,
    split_window,
)

logger = logging.getLogger(__name__)

# A run's provider work is cut off well before its lease expires, so an expired lease always means a dead worker.
LEASE_SECONDS = 600
FETCH_TIMEOUT_SECONDS = 300
MAX_CONCURRENT_RUNS = 8
ADAPTER_CODES = tuple(adapters.REGISTRY)
ADAPTERS = "(" + ",".join(f"'{code}'" for code in ADAPTER_CODES) + ")"
LEAD_SOURCE_FIELDS = (
    "name",
    "company",
    "phone",
    "email",
    "city",
    "state",
    "address",
    "product",
    "enquiry",
)
# A refetch fills blank source fields only, so manual edits survive and the assignee, status and receive time never move.
LEAD_UPSERT = (
    "INSERT INTO crm.leads AS existing(org_id,integration_id,source_record_id,source_provider,created_by,status_id,"
    "assigned_membership_id,name,company,phone,email,city,state,address,product,enquiry,custom_fields,received_at,backfill_id,"
    "campaign_id,ad_id,form_id,description,payload_hash,first_fetched_at,last_fetched_at,fetch_count) "
    "VALUES(:org,:account,:source_record_id,:source,:member,:status,:assignee,:name,:company,:phone,:email,"
    ":city,:state,:address,:product,:enquiry,CAST(:custom AS jsonb),COALESCE(CAST(:received AS timestamptz),now()),:backfill,"
    ":campaign_id,:ad_id,:form_id,:description,:payload_hash,now(),now(),1) "
    "ON CONFLICT(org_id,integration_id,source_record_id) WHERE integration_id IS NOT NULL DO UPDATE SET "
    + ",".join(
        f"{field}=COALESCE(NULLIF(existing.{field},''),EXCLUDED.{field})"
        for field in LEAD_SOURCE_FIELDS
    )
    + ",campaign_id=COALESCE(existing.campaign_id,EXCLUDED.campaign_id),"
    "ad_id=COALESCE(existing.ad_id,EXCLUDED.ad_id),form_id=COALESCE(existing.form_id,EXCLUDED.form_id),"
    "description=COALESCE(NULLIF(existing.description,''),EXCLUDED.description),"
    "payload_hash=EXCLUDED.payload_hash,last_fetched_at=now(),fetch_count=existing.fetch_count+1 "
    "RETURNING id,(xmax=0) AS created"
)
# An import may only take a slot when the next live sync is at least this far away.
IMPORT_LEAD_SECONDS = (
    max(slot_seconds(code) for code in ADAPTER_CODES) - LIVE_SLIP_SECONDS
)


def cooldown(code: str) -> int:
    return provider(code).get("cooldown_seconds", slot_seconds(code))


# Provider-side hiccups: retried on the normal schedule without un-verifying the connection.
TRANSIENT_ERRORS = {"provider_rate_limited", "provider_unavailable", "provider_timeout"}
RETRY_REASONS = {
    "provider_rate_limited": "provider_cooldown",
    "provider_unavailable": "provider_unavailable_retry",
    "provider_timeout": "provider_timeout_retry",
}
# The key itself is no longer trusted, so imports wait for a new successful test.
ACCOUNT_ERRORS = {
    "provider_credentials_rejected",
    "provider_response_rejected",
    "marketplace_key_unavailable",
}


class ClaimConflict(Exception):
    pass


async def claim(engine, org: UUID) -> dict | None:
    try:
        async with tenant_transaction(engine, org) as connection:
            return await _claim(connection, org)
    except ClaimConflict:
        return None


async def _reserve_key(connection, values: dict) -> bool:
    return bool(
        await connection.scalar(
            text(
                "INSERT INTO crm.marketplace_rate_limits(fingerprint,next_allowed_at) VALUES(:key,now()+make_interval(secs=>:gap)) "
                "ON CONFLICT(fingerprint) DO UPDATE SET next_allowed_at=excluded.next_allowed_at "
                "WHERE crm.marketplace_rate_limits.next_allowed_at<=now() RETURNING fingerprint"
            ),
            {
                "key": values["credential_fingerprint"],
                "gap": slot_seconds(values["provider_code"]),
            },
        )
    )


async def _housekeeping(connection, org: UUID) -> None:
    # Import runs are never re-queued: their window simply returns to the ledger.
    await connection.execute(
        text(
            "UPDATE crm.marketplace_sync_runs SET state='cancelled',safe_error_code='worker_lease_expired',finished_at=now() "
            "WHERE org_id=:org AND kind='backfill' AND state='running' AND lease_until<now()"
        ),
        {"org": org},
    )
    await connection.execute(
        text(
            "UPDATE crm.marketplace_sync_runs SET state='queued',lease_token=NULL,lease_until=NULL WHERE org_id=:org AND state='running' AND lease_until<now()"
        ),
        {"org": org},
    )
    await connection.execute(
        text(
            "UPDATE crm.marketplace_backfill_windows w SET state='pending',updated_at=now() WHERE org_id=:org AND state='running' "
            "AND NOT EXISTS(SELECT 1 FROM crm.marketplace_sync_runs r WHERE r.org_id=w.org_id AND r.account_id=w.account_id "
            "AND r.window_id=w.id AND r.state='running')"
        ),
        {"org": org},
    )


async def _permitted(connection, org: UUID, member: UUID) -> bool:
    try:
        _, permissions, _, _ = await effective_access(connection, org, member)
    except AccessError:
        return False
    return "marketplace.manage" in permissions


async def _claim(connection, org: UUID) -> dict | None:
    if not await connection.scalar(
        text(
            "SELECT id FROM crm.organizations WHERE id=:org AND status='active' FOR SHARE"
        ),
        {"org": org},
    ):
        return None
    await _housekeeping(connection, org)
    await connection.execute(
        text(
            "INSERT INTO crm.marketplace_sync_runs(org_id,account_id,kind,credential_version) "
            "SELECT org_id,id,'sync',credential_version FROM crm.marketplace_accounts a "
            f"WHERE org_id=:org AND provider_code IN {ADAPTERS} AND status='active' AND next_live_at<=now() "
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
            return await _claim_window(connection, org)
        values = dict(row)
        if await _permitted(connection, org, values["created_by"]):
            break
        await connection.execute(
            text(
                "UPDATE crm.marketplace_sync_runs SET state='cancelled',safe_error_code='integration_actor_inactive',finished_at=now() WHERE org_id=:org AND id=:id"
            ),
            {"org": org, "id": values["run_id"]},
        )
    if not await _reserve_key(connection, values):
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
    # Scheduled runs keep their cadence; a manual or very late run restarts it from now.
    live = (
        ",next_live_at=CASE WHEN next_live_at<=now() AND next_live_at+make_interval(secs=>sync_interval_seconds)>now() "
        "THEN next_live_at+make_interval(secs=>sync_interval_seconds) ELSE now()+make_interval(secs=>sync_interval_seconds) END"
        if values["kind"] == "sync"
        else ""
    )
    await connection.execute(
        text(
            "UPDATE crm.marketplace_accounts SET next_allowed_at=now()+make_interval(secs=>:gap),last_request_at=now()"
            + live
            + " WHERE org_id=:org AND id=:id"
        ),
        {"org": org, "id": values["id"], "gap": slot_seconds(values["provider_code"])},
    )
    values["lease_token"] = token
    return values


async def _claim_window(connection, org: UUID) -> dict | None:
    while True:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT a.*,w.id AS window_id,w.backfill_id,w.window_start,w.window_end,w.next_page,w.attempts "
                        "FROM crm.marketplace_accounts a "
                        "JOIN crm.marketplace_backfills b ON b.org_id=a.org_id AND b.account_id=a.id AND b.state='active' "
                        "JOIN crm.marketplace_backfill_windows w ON w.org_id=b.org_id AND w.backfill_id=b.id "
                        "AND w.state='pending' AND w.next_attempt_at<=now() "
                        f"WHERE a.org_id=:org AND a.provider_code IN {ADAPTERS} AND a.status='active' "
                        "AND a.verified_version=a.credential_version AND a.next_allowed_at<=now() "
                        "AND a.next_live_at>=now()+make_interval(secs=>:lead) "
                        "AND NOT EXISTS(SELECT 1 FROM crm.marketplace_sync_runs r WHERE r.org_id=a.org_id AND r.account_id=a.id "
                        "AND r.state IN ('queued','running')) "
                        "AND NOT EXISTS(SELECT 1 FROM crm.marketplace_rate_limits l "
                        "WHERE l.fingerprint=a.credential_fingerprint AND l.next_allowed_at>now()) "
                        "ORDER BY w.window_end DESC LIMIT 1 FOR UPDATE OF a,b,w SKIP LOCKED"
                    ),
                    {"org": org, "lead": IMPORT_LEAD_SECONDS},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        values = dict(row)
        parameters = {
            "org": org,
            "window": values["window_id"],
            "backfill": values["backfill_id"],
        }
        if not await _permitted(connection, org, values["created_by"]):
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_backfills SET state='cancelled',hold_reason='import_cancelled_actor_inactive',"
                    "hold_until=NULL,finished_at=now() WHERE org_id=:org AND id=:backfill"
                ),
                parameters,
            )
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_backfill_windows SET state='cancelled',updated_at=now() "
                    "WHERE org_id=:org AND backfill_id=:backfill AND state='pending'"
                ),
                parameters,
            )
            continue
        floor = history_floor(values["provider_code"], datetime.now(timezone.utc))
        if values["window_end"] <= floor:
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_backfill_windows SET state='expired',hold_reason='history_expired',updated_at=now() "
                    "WHERE org_id=:org AND id=:window"
                ),
                parameters,
            )
            await complete_if_done(connection, org, values["backfill_id"])
            continue
        break
    if not await _reserve_key(connection, values):
        return None
    token = uuid4()
    run_id = await connection.scalar(
        text(
            "INSERT INTO crm.marketplace_sync_runs(org_id,account_id,kind,credential_version,state,lease_token,lease_until,"
            "window_id,window_start,window_end) VALUES(:org,:account,'backfill',:version,'running',:token,"
            "now()+make_interval(secs=>:lease),:window,:start,:end) "
            "ON CONFLICT(org_id,account_id) WHERE state IN ('queued','running') DO NOTHING RETURNING id"
        ),
        {
            **parameters,
            "account": values["id"],
            "version": values["credential_version"],
            "token": token,
            "lease": LEASE_SECONDS,
            "start": values["window_start"],
            "end": values["window_end"],
        },
    )
    if run_id is None:
        # A manual run was queued concurrently; roll back the key reservation and let it go first.
        raise ClaimConflict
    await connection.execute(
        text(
            "UPDATE crm.marketplace_backfill_windows SET state='running',updated_at=now() WHERE org_id=:org AND id=:window"
        ),
        parameters,
    )
    await connection.execute(
        text(
            "UPDATE crm.marketplace_accounts SET next_allowed_at=now()+make_interval(secs=>:gap),last_request_at=now() "
            "WHERE org_id=:org AND id=:id"
        ),
        {"org": org, "id": values["id"], "gap": slot_seconds(values["provider_code"])},
    )
    values.update(
        run_id=run_id,
        kind="backfill",
        lease_token=token,
        fetch_start=max(values["window_start"], floor),
    )
    return values


async def complete_if_done(connection, org: UUID, backfill: UUID) -> None:
    await connection.execute(
        text(
            "UPDATE crm.marketplace_backfills b SET state='completed',finished_at=now(),hold_until=NULL,"
            "hold_reason=CASE WHEN b.hold_reason='import_stopped_no_older_data' THEN b.hold_reason "
            "WHEN EXISTS(SELECT 1 FROM crm.marketplace_backfill_windows f WHERE f.org_id=b.org_id AND f.backfill_id=b.id "
            "AND f.state='failed') THEN 'import_completed_with_failures' ELSE NULL END "
            "WHERE b.org_id=:org AND b.id=:id AND b.state='active' AND NOT EXISTS(SELECT 1 FROM crm.marketplace_backfill_windows w "
            "WHERE w.org_id=b.org_id AND w.backfill_id=b.id AND w.state IN ('pending','running'))"
        ),
        {"org": org, "id": backfill},
    )


async def _finish_window(
    connection,
    org: UUID,
    run: dict,
    error: str | None,
    fetched: int,
    accepted: int,
    next_page: int | None,
    until: datetime | None,
) -> None:
    code = run["provider_code"]
    parameters = {
        "org": org,
        "window": run["window_id"],
        "backfill": run["backfill_id"],
        "fetched": fetched,
        "accepted": accepted,
        "error": error,
    }

    async def window(assignments: str, **extra) -> None:
        await connection.execute(
            text(
                f"UPDATE crm.marketplace_backfill_windows SET {assignments},updated_at=now() "
                "WHERE org_id=:org AND id=:window AND state='running'"
            ),
            {**parameters, **extra},
        )

    async def job(assignments: str, **extra) -> None:
        await connection.execute(
            text(
                f"UPDATE crm.marketplace_backfills SET {assignments} WHERE org_id=:org AND id=:backfill AND state='active'"
            ),
            {**parameters, **extra},
        )

    if not error:
        counts = "fetched_count=fetched_count+:fetched,accepted_count=accepted_count+:accepted"
        if next_page:
            await window(
                f"state='pending',next_page=:page,attempts=0,next_attempt_at=now(),"
                f"hold_reason='window_continues_next_slot',safe_error_code=NULL,{counts}",
                page=next_page,
            )
            await job(f"hold_reason=NULL,hold_until=NULL,{counts}")
        else:
            await window(
                f"state='completed',hold_reason=NULL,safe_error_code=NULL,{counts}"
            )
            await job(
                f"hold_reason=NULL,hold_until=NULL,{counts},"
                "empty_streak=CASE WHEN :fetched=0 THEN empty_streak+1 ELSE 0 END"
            )
            threshold = provider(code).get("empty_stop_windows")
            if threshold:
                stopped = await connection.scalar(
                    text(
                        "UPDATE crm.marketplace_backfills SET hold_reason='import_stopped_no_older_data' "
                        "WHERE org_id=:org AND id=:backfill AND state='active' AND empty_streak>=:threshold RETURNING id"
                    ),
                    {**parameters, "threshold": threshold},
                )
                if stopped:
                    await connection.execute(
                        text(
                            "UPDATE crm.marketplace_backfill_windows SET state='skipped',hold_reason='import_stopped_no_older_data',"
                            "updated_at=now() WHERE org_id=:org AND backfill_id=:backfill AND state='pending'"
                        ),
                        parameters,
                    )
    elif error == "provider_history_not_ready":
        release = until or datetime.now(timezone.utc) + timedelta(hours=1)
        await window(
            "state='pending',next_attempt_at=:until,hold_reason='history_not_ready',safe_error_code=:error",
            until=release,
        )
        await job("hold_reason='history_not_ready',hold_until=:until", until=release)
    elif error == "provider_history_expired":
        await window(
            "state='expired',hold_reason='history_expired',safe_error_code=:error"
        )
    elif error == "provider_payload_too_large":
        parts = split_window(code, run["window_start"], run["window_end"])
        if not parts:
            await window("state='failed',hold_reason=NULL,safe_error_code=:error")
        else:
            await window(
                "state='split',hold_reason='window_split_large',safe_error_code=:error"
            )
        for start, end in parts or []:
            await connection.execute(
                text(
                    "INSERT INTO crm.marketplace_backfill_windows(org_id,backfill_id,account_id,window_start,window_end) "
                    "VALUES(:org,:backfill,:account,:start,:end) ON CONFLICT DO NOTHING"
                ),
                {**parameters, "account": run["id"], "start": start, "end": end},
            )
    elif error in ACCOUNT_ERRORS:
        await window(
            "state='pending',hold_reason='import_paused_needs_test',safe_error_code=:error"
        )
    else:
        attempts = run["attempts"] + 1
        if attempts >= MAX_WINDOW_ATTEMPTS:
            await window(
                "state='failed',attempts=:attempts,hold_reason=NULL,safe_error_code=:error",
                attempts=attempts,
            )
        else:
            delay = backoff(attempts)
            if error == "provider_rate_limited":
                delay = max(delay, timedelta(seconds=cooldown(code)))
            retry = datetime.now(timezone.utc) + delay
            reason = RETRY_REASONS.get(error, "provider_error_retry")
            await window(
                "state='pending',attempts=:attempts,next_attempt_at=:until,hold_reason=:reason,safe_error_code=:error",
                attempts=attempts,
                until=retry,
                reason=reason,
            )
            await job(
                "hold_reason=:reason,hold_until=:until", reason=reason, until=retry
            )
    await complete_if_done(connection, org, run["backfill_id"])


async def finish(
    engine,
    org: UUID,
    run: dict,
    leads: list[dict],
    end: datetime,
    error: str | None = None,
    next_page: int | None = None,
    until: datetime | None = None,
    gap: tuple[datetime, datetime] | None = None,
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
        imported = run["kind"] == "backfill"
        if not error and run["kind"] in ("sync", "backfill"):
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
                    content = {
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
                        # Imported history keeps the enquiry time so old leads don't surface as new today.
                        received=lead["source_time"] if imported else None,
                        backfill=run["backfill_id"] if imported else None,
                        campaign_id=lead.get("campaign_id"),
                        ad_id=lead.get("ad_id"),
                        form_id=lead.get("form_id"),
                        description=lead.get("description", ""),
                        payload_hash=hashlib.sha256(
                            json.dumps(content, sort_keys=True, default=str).encode()
                        ).hexdigest(),
                    )
                    row = (await connection.execute(text(LEAD_UPSERT), values)).one()
                    if row.created:
                        await route_new_lead(
                            connection, org, run["provider_code"], row.id
                        )
                        accepted += 1
                        await audit(
                            connection, org, None, "marketplace.lead_received", row.id
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
        if imported:
            await _finish_window(
                connection, org, run, error, len(leads), accepted, next_page, until
            )
            await _account_after_import(connection, run, error, parameters)
        else:
            if gap and not error:
                await _record_gap(connection, org, run, gap)
            await _account_after_live(connection, run, error, parameters)
        parameters["state"] = "failed" if error else "completed"
        await connection.execute(
            text(
                "UPDATE crm.marketplace_sync_runs SET state=:state,safe_error_code=:error,fetched_count=:fetched,accepted_count=:accepted,finished_at=now() WHERE org_id=:org AND id=:run"
            ),
            parameters,
        )


async def _record_gap(
    connection, org: UUID, run: dict, gap: tuple[datetime, datetime]
) -> None:
    code = run["provider_code"]
    start = max(gap[0], history_floor(code, datetime.now(timezone.utc)))
    windows = plan_windows(code, start, gap[1]) if gap[1] > start else []
    if not windows:
        return
    parameters = {
        "org": org,
        "account": run["id"],
        "start": windows[-1][0],
        "end": windows[0][1],
        "total": len(windows),
        "member": run["created_by"],
    }
    # An import that is already running absorbs the gap, keeping one history job per connection.
    backfill = await connection.scalar(
        text(
            "UPDATE crm.marketplace_backfills SET range_start=LEAST(range_start,:start),range_end=GREATEST(range_end,:end),"
            "windows_total=windows_total+:total WHERE org_id=:org AND account_id=:account AND state='active' RETURNING id"
        ),
        parameters,
    ) or await connection.scalar(
        text(
            "INSERT INTO crm.marketplace_backfills(org_id,account_id,kind,range_start,range_end,windows_total,created_by) "
            "VALUES(:org,:account,'gap',:start,:end,:total,:member) RETURNING id"
        ),
        parameters,
    )
    await connection.execute(
        text(
            "INSERT INTO crm.marketplace_backfill_windows(org_id,backfill_id,account_id,window_start,window_end) "
            "VALUES(:org,:backfill,:account,:start,:end) ON CONFLICT DO NOTHING"
        ),
        [
            {
                "org": org,
                "backfill": backfill,
                "account": run["id"],
                "start": window_start,
                "end": window_end,
            }
            for window_start, window_end in windows
        ],
    )
    await audit(connection, org, None, "marketplace.gap_recovery_started", run["id"])


async def _cool_key(connection, run: dict, seconds: int) -> None:
    await connection.execute(
        text(
            "UPDATE crm.marketplace_rate_limits SET next_allowed_at=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)) "
            "WHERE fingerprint=:fingerprint"
        ),
        {"cooldown": seconds, "fingerprint": run["credential_fingerprint"]},
    )


async def _account_after_import(
    connection, run: dict, error: str | None, parameters: dict
) -> None:
    # Import results never move the live watermark or the row version the UI edits against.
    if error in ACCOUNT_ERRORS:
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET safe_error_code=:error,verified_version=NULL,status='error',"
                "hold_reason=NULL,hold_until=NULL,row_version=row_version+1,updated_at=now() WHERE org_id=:org AND id=:id"
            ),
            parameters,
        )
    elif error == "provider_rate_limited":
        seconds = cooldown(run["provider_code"])
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET hold_reason='provider_cooldown',"
                "next_allowed_at=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)),"
                "hold_until=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)) WHERE org_id=:org AND id=:id"
            ),
            {**parameters, "cooldown": seconds},
        )
        await _cool_key(connection, run, seconds)
    elif not error or error in (
        "provider_history_not_ready",
        "provider_history_expired",
    ):
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET last_success_at=now() WHERE org_id=:org AND id=:id"
            ),
            parameters,
        )


async def _account_after_live(
    connection, run: dict, error: str | None, parameters: dict
) -> None:
    if error in TRANSIENT_ERRORS:
        failures = run["consecutive_failures"] + 1
        delay = backoff(failures)
        if error == "provider_rate_limited":
            delay = max(delay, timedelta(seconds=cooldown(run["provider_code"])))
        parameters["cooldown"] = int(delay.total_seconds())
        parameters["failures"] = failures
        parameters["hold"] = RETRY_REASONS[error]
        # Repeated transient failures back off exponentially; the live sync resumes once the delay passes.
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET safe_error_code=:error,consecutive_failures=:failures,"
                "row_version=row_version+1,updated_at=now(),"
                "next_allowed_at=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)),hold_reason=:hold,"
                "hold_until=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)),"
                "next_live_at=GREATEST(next_allowed_at,now()+make_interval(secs=>:cooldown)) "
                "WHERE org_id=:org AND id=:id"
            ),
            parameters,
        )
        # Only a provider rate limit cools the shared credential bucket; other failures stay per account.
        if error == "provider_rate_limited":
            await _cool_key(connection, run, parameters["cooldown"])
    elif error:
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET safe_error_code=:error,verified_version=NULL,status='error',"
                "hold_reason=NULL,hold_until=NULL,row_version=row_version+1,updated_at=now() WHERE org_id=:org AND id=:id"
            ),
            parameters,
        )
    else:
        # A window that ended before now (day providers stop at midnight) leaves more to fetch at the next slot.
        live = (
            ",watermark=:end,last_received_at=CASE WHEN :accepted>0 THEN now() ELSE last_received_at END,"
            "next_live_at=CASE WHEN CAST(:end AS timestamptz)<now()-interval '1 minute' THEN now() ELSE next_live_at END"
            if run["kind"] == "sync"
            else ""
        )
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET safe_error_code=NULL,last_success_at=now(),hold_reason=NULL,hold_until=NULL,consecutive_failures=0,"
                "status=CASE WHEN status='error' THEN 'draft' ELSE status END,"
                "verified_version=credential_version,row_version=row_version+1,updated_at=now()"
                + live
                + " WHERE org_id=:org AND id=:id"
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


def window_for(run: dict, now: datetime) -> tuple[datetime, datetime]:
    if run["kind"] == "test":
        start = now - timedelta(minutes=5)
        if provider(run["provider_code"])["window_unit"] == "day":
            start = max(start, ist_midnight(now.astimezone(IST).date()))
        return start, now
    return run["fetch_start"], run["window_end"]


async def execute(
    engine, org: UUID, run: dict, private: rsa.RSAPrivateKey, client: httpx.AsyncClient
) -> None:
    now = datetime.now(timezone.utc)
    next_page = None
    gap = None
    if run["kind"] == "sync":
        start, end, gap = live_window(run["provider_code"], run["watermark"], now)
    else:
        start, end = window_for(run, now)
    try:
        credentials = decrypt_credentials(
            private,
            run["credential_envelope"],
            str(org),
            str(run["id"]),
            run["credential_version"],
        )
        config = (
            run["config"]
            if isinstance(run["config"], dict)
            else json.loads(run["config"])
        )
        fetch = adapters.fetch(
            run["provider_code"],
            client,
            config,
            credentials,
            start,
            end,
            run["kind"],
            run.get("next_page") or 1,
        )
        try:
            async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
                leads = await fetch
        except TimeoutError:
            raise AccessError(504, "provider_timeout") from None
        if isinstance(leads, tuple):
            leads, next_page = leads
        await finish(engine, org, run, leads, end, next_page=next_page, gap=gap)
    except indiamart.HistoryNotReady as error:
        await finish(engine, org, run, [], end, error.code, until=error.until)
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
    max_concurrent: int = MAX_CONCURRENT_RUNS,
    max_per_org: int = 2,
) -> bool:
    started = False
    while len(running) < max_concurrent:
        progressed = False
        for org in targets:
            if len(running) >= max_concurrent:
                break
            active_for_org = sum(
                1 for task in running if getattr(task, "crm_org_id", None) == org
            )
            if active_for_org >= max_per_org:
                continue
            try:
                run = await claim(engine, org)
            except Exception:
                logger.exception("marketplace_claim_failed org=%s", org)
                continue
            if run is None:
                continue
            task = asyncio.create_task(run_safely(engine, org, run, private, client))
            task.crm_org_id = org
            running.add(task)
            task.add_done_callback(running.discard)
            started = True
            progressed = True
        if not progressed:
            break
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
                    started = await dispatch(
                        engine,
                        targets,
                        private,
                        client,
                        running,
                        settings.marketplace_worker_concurrency,
                        settings.marketplace_org_concurrency,
                    )
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
