import hashlib
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..identity.dependencies import User
from ..identity.service import AccessError, audit
from ..leads.queries import access
from .catalog import PROVIDERS, provider, validate_configuration
from .crypto import encrypt_credentials, load_public_key
from .schedule import (
    history_floor,
    history_status,
    ist_midnight,
    live_status,
    plan_windows,
)

router = APIRouter(prefix="/api/v1/marketplace", tags=["Marketplace"])
SAFE_FIELDS = "id,provider_code,name,status,config,credential_hint,credential_version,verified_version,row_version,last_success_at,last_received_at,safe_error_code,created_at,updated_at,sync_interval_seconds"
# Read only to derive schedule_status; never returned as-is.
SCHEDULE_FIELDS = "next_live_at,next_allowed_at,hold_reason,hold_until,last_request_at"
WORKER_STALE_SECONDS = 120
BACKFILL_FIELDS = (
    "id",
    "kind",
    "state",
    "range_start",
    "range_end",
    "hold_reason",
    "hold_until",
    "fetched_count",
    "accepted_count",
    "created_at",
    "finished_at",
    "windows_total",
    "windows_done",
    "windows_failed",
    "windows_pending",
    "windows_running",
)
BACKFILL_SUMMARY = (
    "SELECT b.id,b.kind,b.state,b.range_start,b.range_end,b.hold_reason,b.hold_until,b.fetched_count,b.accepted_count,"
    "b.created_at,b.finished_at,"
    "count(w.id) FILTER(WHERE w.state NOT IN ('split','cancelled')) AS windows_total,"
    "count(w.id) FILTER(WHERE w.state IN ('completed','expired','skipped')) AS windows_done,"
    "count(w.id) FILTER(WHERE w.state='failed') AS windows_failed,"
    "count(w.id) FILTER(WHERE w.state='pending') AS windows_pending,"
    "count(w.id) FILTER(WHERE w.state='running') AS windows_running "
    "FROM crm.marketplace_backfills b LEFT JOIN crm.marketplace_backfill_windows w "
    "ON w.org_id=b.org_id AND w.backfill_id=b.id "
)
ACCOUNT_SELECT = (
    "SELECT "
    + ",".join(f"a.{name}" for name in f"{SAFE_FIELDS},{SCHEDULE_FIELDS}".split(","))
    + ",r.kind AS last_run_kind,"
    "r.state AS last_run_state,r.safe_error_code AS last_run_error,r.created_at AS last_run_at,"
    "crm.marketplace_key_available_at(a.id) AS key_available_at,"
    + ",".join(f"h.{name} AS backfill_{name}" for name in BACKFILL_FIELDS)
    + " FROM crm.marketplace_accounts a LEFT JOIN LATERAL (SELECT kind,state,safe_error_code,created_at "
    "FROM crm.marketplace_sync_runs s WHERE s.org_id=a.org_id AND s.account_id=a.id ORDER BY created_at DESC LIMIT 1) r ON true "
    "LEFT JOIN LATERAL ("
    + BACKFILL_SUMMARY
    + "WHERE b.org_id=a.org_id AND b.account_id=a.id GROUP BY b.org_id,b.id ORDER BY b.created_at DESC LIMIT 1) h ON true "
)


def credential_hint(values: dict[str, str]) -> str:
    # Only the last four characters of long keys are kept; short values reveal nothing.
    return json.dumps(
        {
            key: "•" * 8 + (value[-4:] if len(value) >= 12 else "")
            for key, value in values.items()
        }
    )


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider_code: str = Field(max_length=40)
    name: str = Field(min_length=1, max_length=100)
    config: dict[str, str] = Field(default_factory=dict, max_length=10)
    credentials: dict[str, SecretStr] = Field(default_factory=dict, max_length=10)
    row_version: int | None = Field(None, ge=1)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Account name is required")
        return value.strip()

    @field_validator("config", "credentials")
    @classmethod
    def bounded_fields(cls, value: dict) -> dict:
        if any(
            len(key) > 40
            or len(item.get_secret_value() if isinstance(item, SecretStr) else item)
            > 4096
            for key, item in value.items()
        ):
            raise ValueError("Configuration field exceeds maximum length")
        return value


class AccountAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_version: int = Field(ge=1)


class AccountCreate(AccountInput):
    sync_interval_seconds: int | None = None
    import_history: bool = False


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sync_interval_seconds: int


class BackfillInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_date: date | None = None
    to_date: date | None = None


def valid_interval(code: str, value: int) -> int:
    if value not in provider(code).get("allowed_intervals", []):
        raise AccessError(422, "invalid_sync_interval")
    return value


async def worker_state(connection) -> dict | None:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT last_seen_at,last_seen_at>now()-make_interval(secs=>:stale) AS online FROM crm.marketplace_worker_heartbeat WHERE id"
                ),
                {"stale": WORKER_STALE_SECONDS},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def present(row: dict, online: bool, now: datetime) -> dict:
    values = dict(row)
    backfill = (
        {name: values[f"backfill_{name}"] for name in BACKFILL_FIELDS}
        if values.get("backfill_id")
        else None
    )
    live = live_status(values, values["key_available_at"], online, now)
    history = history_status(values, backfill, online, now)
    for name in (*SCHEDULE_FIELDS.split(","), "key_available_at"):
        values.pop(name)
    for name in BACKFILL_FIELDS:
        values.pop(f"backfill_{name}")
    values["schedule_status"] = {"live": live, "history": history}
    return values


async def presented(connection, org: UUID, identity: UUID) -> dict:
    worker = await worker_state(connection)
    return present(
        await account(connection, org, identity),
        bool(worker and worker["online"]),
        datetime.now(timezone.utc),
    )


async def cancel_backfills(connection, org: UUID, account_id: UUID, reason: str) -> None:
    parameters = {"org": org, "id": account_id, "reason": reason}
    await connection.execute(
        text(
            "UPDATE crm.marketplace_backfills SET state='cancelled',hold_reason=:reason,hold_until=NULL,finished_at=now() "
            "WHERE org_id=:org AND account_id=:id AND state='active'"
        ),
        parameters,
    )
    await connection.execute(
        text(
            "UPDATE crm.marketplace_backfill_windows SET state='cancelled',updated_at=now() "
            "WHERE org_id=:org AND account_id=:id AND state IN ('pending','running')"
        ),
        parameters,
    )


async def start_backfill(
    connection,
    org: UUID,
    member: UUID,
    existing: dict,
    start: datetime,
    end: datetime,
) -> UUID:
    code = existing["provider_code"]
    if not provider(code)["adapter"]:
        raise AccessError(409, "provider_adapter_unavailable")
    now = datetime.now(timezone.utc)
    start, end = max(start, history_floor(code, now)), min(end, now)
    windows = plan_windows(code, start, end) if end > start else []
    if not windows:
        raise AccessError(409, "marketplace_backfill_range_empty")
    identity = uuid4()
    try:
        async with connection.begin_nested():
            await connection.execute(
                text(
                    "INSERT INTO crm.marketplace_backfills(org_id,id,account_id,range_start,range_end,windows_total,created_by) "
                    "VALUES(:org,:id,:account,:start,:end,:total,:member)"
                ),
                {
                    "org": org,
                    "id": identity,
                    "account": existing["id"],
                    "start": windows[-1][0],
                    "end": windows[0][1],
                    "total": len(windows),
                    "member": member,
                },
            )
    except IntegrityError:
        raise AccessError(409, "marketplace_backfill_active") from None
    await connection.execute(
        text(
            "INSERT INTO crm.marketplace_backfill_windows(org_id,backfill_id,account_id,window_start,window_end) "
            "VALUES(:org,:backfill,:account,:start,:end)"
        ),
        [
            {
                "org": org,
                "backfill": identity,
                "account": existing["id"],
                "start": window_start,
                "end": window_end,
            }
            for window_start, window_end in windows
        ],
    )
    await audit(connection, org, member, "marketplace.backfill_started", existing["id"])
    return identity


async def account(connection, org: UUID, identity: UUID) -> dict:
    row = (
        (
            await connection.execute(
                text(ACCOUNT_SELECT + "WHERE a.org_id=:org AND a.id=:id"),
                {"org": org, "id": identity},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise AccessError(404, "marketplace_account_not_found")
    return dict(row)


@asynccontextmanager
async def unique_account(connection):
    try:
        async with connection.begin_nested():
            yield
    except IntegrityError as error:
        constraint = getattr(
            getattr(getattr(error, "orig", None), "diag", None), "constraint_name", None
        )
        if constraint == "marketplace_account_names":
            raise AccessError(409, "marketplace_name_in_use") from None
        if constraint == "marketplace_account_credentials":
            raise AccessError(409, "marketplace_credentials_in_use") from None
        raise


@router.get("/providers")
async def providers(request: Request, user: User):
    async with access(request, user, "marketplace.view") as (connection, _):
        configuration = request.app.state.configuration
        try:
            load_public_key(configuration)
            ready = True
        except AccessError:
            ready = False
        worker = await worker_state(connection)
        return {
            "data": PROVIDERS,
            "credential_storage_ready": ready,
            "worker_online": bool(worker and worker["online"]),
            "worker_last_seen_at": worker["last_seen_at"] if worker else None,
        }


@router.get("/accounts")
async def list_accounts(
    request: Request,
    user: User,
    after: UUID | None = None,
    limit: int = Query(25, ge=1, le=100),
):
    async with access(request, user, "marketplace.view") as (connection, current):
        rows = (
            (
                await connection.execute(
                    text(
                        ACCOUNT_SELECT + "WHERE a.org_id=:org AND a.status<>'retired' "
                        "AND (CAST(:after AS uuid) IS NULL OR a.id>:after) ORDER BY a.id LIMIT :limit"
                    ),
                    {"org": current.org_id, "after": after, "limit": limit + 1},
                )
            )
            .mappings()
            .all()
        )
        worker = await worker_state(connection)
        online, now = bool(worker and worker["online"]), datetime.now(timezone.utc)
        return {
            "data": [present(row, online, now) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }


@router.post("/accounts", status_code=201)
async def create_account(body: AccountCreate, request: Request, user: User):
    values = {
        key: value.get_secret_value().strip() for key, value in body.credentials.items()
    }
    validate_configuration(body.provider_code, body.config, values)
    item = provider(body.provider_code)
    interval = valid_interval(
        body.provider_code,
        body.sync_interval_seconds or item.get("default_interval_seconds", 900),
    )
    identity = uuid4()
    async with access(request, user, "marketplace.manage") as (connection, current):
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:org),hashtext(:provider))"),
            {"org": str(current.org_id), "provider": body.provider_code},
        )
        if provider(body.provider_code)[
            "multiple_accounts"
        ] is not True and await connection.scalar(
            text(
                "SELECT 1 FROM crm.marketplace_accounts WHERE org_id=:org AND provider_code=:provider AND status<>'retired' LIMIT 1"
            ),
            {"org": current.org_id, "provider": body.provider_code},
        ):
            raise AccessError(409, "provider_account_limit_unverified")
        envelope = encrypt_credentials(
            request.app.state.configuration,
            values,
            str(current.org_id),
            str(identity),
            1,
        )
        async with unique_account(connection):
            await connection.execute(
                text(
                    "INSERT INTO crm.marketplace_accounts(org_id,id,provider_code,name,config,credential_envelope,credential_fingerprint,credential_hint,created_by,sync_interval_seconds) "
                    "VALUES(:org,:id,:provider,:name,CAST(:config AS jsonb),CAST(:envelope AS jsonb),:fingerprint,CAST(:hint AS jsonb),:member,:interval)"
                ),
                {
                    "org": current.org_id,
                    "id": identity,
                    "provider": body.provider_code,
                    "name": body.name,
                    "config": json.dumps(body.config),
                    "envelope": json.dumps(envelope),
                    "member": current.member_id,
                    "hint": credential_hint(values),
                    "interval": interval,
                    "fingerprint": hashlib.sha256(
                        json.dumps(values, sort_keys=True).encode()
                    ).hexdigest(),
                },
            )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "marketplace.account_created",
            identity,
        )
        if body.import_history:
            created = await account(connection, current.org_id, identity)
            await start_backfill(
                connection,
                current.org_id,
                current.member_id,
                created,
                datetime.min.replace(tzinfo=timezone.utc),
                created["created_at"],
            )
        return await presented(connection, current.org_id, identity)


@router.put("/accounts/{account_id}")
async def update_account(
    account_id: UUID, body: AccountInput, request: Request, user: User
):
    if body.row_version is None:
        raise AccessError(422, "marketplace_version_required")
    async with access(request, user, "marketplace.manage") as (connection, current):
        existing = await account(connection, current.org_id, account_id)
        if (
            existing["status"] == "retired"
            or body.provider_code != existing["provider_code"]
        ):
            raise AccessError(409, "marketplace_account_unavailable")
        values = {
            key: value.get_secret_value().strip()
            for key, value in body.credentials.items()
        }
        validate_configuration(body.provider_code, body.config, values, replacing=True)
        parameters = {
            "org": current.org_id,
            "id": account_id,
            "name": body.name,
            "config": json.dumps(body.config),
            "version": body.row_version,
        }
        secret_assignment = ""
        if values:
            version = existing["credential_version"] + 1
            envelope = encrypt_credentials(
                request.app.state.configuration,
                values,
                str(current.org_id),
                str(account_id),
                version,
            )
            parameters.update(
                envelope=json.dumps(envelope),
                hint=credential_hint(values),
                fingerprint=hashlib.sha256(
                    json.dumps(values, sort_keys=True).encode()
                ).hexdigest(),
            )
            secret_assignment = (
                ",credential_envelope=CAST(:envelope AS jsonb),credential_fingerprint=:fingerprint,"
                "credential_hint=CAST(:hint AS jsonb),credential_version=credential_version+1,hold_reason=NULL,hold_until=NULL"
            )
        async with unique_account(connection):
            changed = await connection.scalar(
                text(
                    "UPDATE crm.marketplace_accounts SET name=:name,config=CAST(:config AS jsonb),status='draft',verified_version=NULL,"
                    "default_assignee_membership_id=NULL,"
                    f"safe_error_code=NULL,row_version=row_version+1,updated_at=now(){secret_assignment} "
                    "WHERE org_id=:org AND id=:id AND row_version=:version RETURNING id"
                ),
                parameters,
            )
        if not changed:
            raise AccessError(409, "marketplace_version_conflict")
        await connection.execute(
            text(
                "UPDATE crm.marketplace_sync_runs SET state='cancelled',finished_at=now() WHERE org_id=:org AND account_id=:id AND state IN ('queued','running')"
            ),
            parameters,
        )
        if values:
            # A replaced key may belong to a different seller account, so its history must be imported afresh.
            await cancel_backfills(
                connection, current.org_id, account_id, "import_cancelled_credentials_changed"
            )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "marketplace.account_updated",
            account_id,
        )
        return await presented(connection, current.org_id, account_id)


@router.put("/accounts/{account_id}/schedule")
async def update_schedule(
    account_id: UUID, body: ScheduleInput, request: Request, user: User
):
    async with access(request, user, "marketplace.manage") as (connection, current):
        existing = await account(connection, current.org_id, account_id)
        if existing["status"] == "retired":
            raise AccessError(409, "marketplace_account_unavailable")
        # Row version stays unchanged so an in-flight run is not discarded by a cadence change.
        await connection.execute(
            text(
                "UPDATE crm.marketplace_accounts SET sync_interval_seconds=:interval,"
                "next_live_at=LEAST(next_live_at,now()+make_interval(secs=>:interval)) WHERE org_id=:org AND id=:id"
            ),
            {
                "org": current.org_id,
                "id": account_id,
                "interval": valid_interval(
                    existing["provider_code"], body.sync_interval_seconds
                ),
            },
        )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "marketplace.schedule_updated",
            account_id,
        )
        return await presented(connection, current.org_id, account_id)


@router.post("/accounts/{account_id}/backfills", status_code=201)
async def create_backfill(
    account_id: UUID, body: BackfillInput, request: Request, user: User
):
    async with access(request, user, "marketplace.manage") as (connection, current):
        existing = await account(connection, current.org_id, account_id)
        if existing["status"] == "retired":
            raise AccessError(409, "marketplace_account_unavailable")
        if body.from_date and body.to_date and body.from_date > body.to_date:
            raise AccessError(422, "marketplace_backfill_range_invalid")
        await start_backfill(
            connection,
            current.org_id,
            current.member_id,
            existing,
            ist_midnight(body.from_date)
            if body.from_date
            else datetime.min.replace(tzinfo=timezone.utc),
            ist_midnight(body.to_date + timedelta(days=1))
            if body.to_date
            else existing["created_at"],
        )
        return await presented(connection, current.org_id, account_id)


@router.get("/accounts/{account_id}/backfills")
async def list_backfills(account_id: UUID, request: Request, user: User):
    async with access(request, user, "marketplace.view") as (connection, current):
        existing = await account(connection, current.org_id, account_id)
        rows = (
            (
                await connection.execute(
                    text(
                        BACKFILL_SUMMARY
                        + "WHERE b.org_id=:org AND b.account_id=:id GROUP BY b.org_id,b.id ORDER BY b.created_at DESC LIMIT 10"
                    ),
                    {"org": current.org_id, "id": account_id},
                )
            )
            .mappings()
            .all()
        )
        worker = await worker_state(connection)
        online, now = bool(worker and worker["online"]), datetime.now(timezone.utc)
        return {
            "data": [history_status(existing, dict(row), online, now) for row in rows]
        }


@router.get("/accounts/{account_id}/backfills/{backfill_id}/windows")
async def backfill_windows(
    account_id: UUID,
    backfill_id: UUID,
    request: Request,
    user: User,
    after: UUID | None = None,
    limit: int = Query(25, ge=1, le=100),
):
    async with access(request, user, "marketplace.view") as (connection, current):
        await account(connection, current.org_id, account_id)
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT id,window_start,window_end,state,attempts,next_attempt_at,next_page,hold_reason,safe_error_code,"
                        "fetched_count,accepted_count,updated_at FROM crm.marketplace_backfill_windows w "
                        "WHERE org_id=:org AND account_id=:account AND backfill_id=:backfill AND (CAST(:after AS uuid) IS NULL OR "
                        "(w.window_end,w.window_start)<(SELECT window_end,window_start FROM crm.marketplace_backfill_windows "
                        "WHERE org_id=:org AND backfill_id=:backfill AND id=:after)) "
                        "ORDER BY window_end DESC,window_start DESC LIMIT :limit"
                    ),
                    {
                        "org": current.org_id,
                        "account": account_id,
                        "backfill": backfill_id,
                        "after": after,
                        "limit": limit + 1,
                    },
                )
            )
            .mappings()
            .all()
        )
        return {
            "data": [dict(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }


@router.post("/accounts/{account_id}/backfills/{backfill_id}/{action}")
async def backfill_action(
    account_id: UUID,
    backfill_id: UUID,
    action: Literal["cancel", "retry"],
    request: Request,
    user: User,
):
    async with access(request, user, "marketplace.manage") as (connection, current):
        await account(connection, current.org_id, account_id)
        parameters = {"org": current.org_id, "account": account_id, "id": backfill_id}
        state = await connection.scalar(
            text(
                "SELECT state FROM crm.marketplace_backfills WHERE org_id=:org AND account_id=:account AND id=:id FOR UPDATE"
            ),
            parameters,
        )
        if state is None:
            raise AccessError(404, "marketplace_backfill_not_found")
        if action == "cancel":
            if state != "active":
                raise AccessError(409, "marketplace_backfill_closed")
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_sync_runs SET state='cancelled',finished_at=now() WHERE org_id=:org AND account_id=:account "
                    "AND state='running' AND window_id IN (SELECT id FROM crm.marketplace_backfill_windows WHERE org_id=:org AND backfill_id=:id)"
                ),
                parameters,
            )
            await cancel_backfills(
                connection, current.org_id, account_id, "import_cancelled_by_user"
            )
        else:
            if state == "cancelled":
                raise AccessError(409, "marketplace_backfill_closed")
            retried = (
                await connection.execute(
                    text(
                        "UPDATE crm.marketplace_backfill_windows SET state='pending',attempts=0,next_attempt_at=now(),"
                        "hold_reason=NULL,safe_error_code=NULL,updated_at=now() WHERE org_id=:org AND backfill_id=:id AND state='failed'"
                    ),
                    parameters,
                )
            ).rowcount
            if not retried:
                raise AccessError(409, "marketplace_backfill_nothing_to_retry")
            try:
                async with connection.begin_nested():
                    await connection.execute(
                        text(
                            "UPDATE crm.marketplace_backfills SET state='active',hold_reason=NULL,hold_until=NULL,finished_at=NULL "
                            "WHERE org_id=:org AND id=:id"
                        ),
                        parameters,
                    )
            except IntegrityError:
                raise AccessError(409, "marketplace_backfill_active") from None
        await audit(
            connection,
            current.org_id,
            current.member_id,
            f"marketplace.backfill_{action}",
            account_id,
        )
        return await presented(connection, current.org_id, account_id)


@router.post("/accounts/{account_id}/{action}")
async def action_account(
    account_id: UUID,
    action: Literal["test", "sync", "activate", "pause", "retire"],
    body: AccountAction,
    request: Request,
    user: User,
):
    async with access(request, user, "marketplace.manage") as (connection, current):
        await connection.execute(
            text(
                "SELECT id FROM crm.marketplace_accounts WHERE org_id=:org AND id=:id FOR UPDATE"
            ),
            {"org": current.org_id, "id": account_id},
        )
        existing = await account(connection, current.org_id, account_id)
        if existing["row_version"] != body.row_version:
            raise AccessError(409, "marketplace_version_conflict")
        if existing["status"] == "retired":
            raise AccessError(409, "marketplace_account_unavailable")
        if (
            action in ("test", "sync", "activate")
            and not provider(existing["provider_code"])["adapter"]
        ):
            raise AccessError(409, "provider_adapter_unavailable")
        if (
            action in ("sync", "activate")
            and existing["verified_version"] != existing["credential_version"]
        ):
            raise AccessError(409, "marketplace_test_required")
        if action == "sync" and existing["status"] != "active":
            raise AccessError(409, "marketplace_account_not_active")
        parameters = {
            "org": current.org_id,
            "id": account_id,
            "version": existing["credential_version"],
            "action": action,
        }
        if action in ("test", "sync"):
            # A pending run already covers this request; repeated clicks must not hit the one-pending-run index.
            await connection.execute(
                text(
                    "INSERT INTO crm.marketplace_sync_runs(org_id,account_id,kind,credential_version) VALUES(:org,:id,:action,:version) "
                    "ON CONFLICT(org_id,account_id) WHERE state IN ('queued','running') DO NOTHING"
                ),
                parameters,
            )
        else:
            parameters["status"] = {
                "activate": "active",
                "pause": "paused",
                "retire": "retired",
            }[action]
            # Activation makes the first live sync due straight away.
            await connection.execute(
                text(
                    "UPDATE crm.marketplace_accounts SET status=:status,row_version=row_version+1,updated_at=now()"
                    + (",next_live_at=now()" if action == "activate" else "")
                    + " WHERE org_id=:org AND id=:id"
                ),
                parameters,
            )
            if action != "activate":
                await connection.execute(
                    text(
                        "UPDATE crm.marketplace_sync_runs SET state='cancelled',finished_at=now() WHERE org_id=:org AND account_id=:id AND state IN ('queued','running')"
                    ),
                    parameters,
                )
            if action == "retire":
                await cancel_backfills(
                    connection, current.org_id, account_id, "import_cancelled_connection_removed"
                )
        await audit(
            connection,
            current.org_id,
            current.member_id,
            f"marketplace.{action}",
            account_id,
        )
        return await presented(connection, current.org_id, account_id)


@router.get("/accounts/{account_id}/runs")
async def runs(account_id: UUID, request: Request, user: User):
    async with access(request, user, "marketplace.view") as (connection, current):
        await account(connection, current.org_id, account_id)
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT id,kind,state,fetched_count,accepted_count,safe_error_code,window_start,window_end,created_at,finished_at FROM crm.marketplace_sync_runs WHERE org_id=:org AND account_id=:id ORDER BY created_at DESC LIMIT 25"
                    ),
                    {"org": current.org_id, "id": account_id},
                )
            )
            .mappings()
            .all()
        )
        return {"data": [dict(row) for row in rows]}
