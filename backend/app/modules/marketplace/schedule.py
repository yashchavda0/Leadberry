from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .catalog import provider

IST = ZoneInfo("Asia/Kolkata")
# Live sync may start this much late so imports can still use the slots before it.
LIVE_SLIP_SECONDS = 90
HISTORY_MARGIN = timedelta(minutes=10)
MAX_WINDOW_ATTEMPTS = 5
MIN_SPLIT_SECONDS = 3600
KEY_EXPIRY_DAYS = 7
KEY_EXPIRY_WARNING_DAYS = 5

HOLD_REASONS = frozenset(
    {
        "waiting_key_slot",
        "shared_key_slot",
        "provider_cooldown",
        "provider_unavailable_retry",
        "provider_timeout_retry",
        "provider_error_retry",
        "history_not_ready",
        "history_expired",
        "window_split_large",
        "window_continues_next_slot",
        "import_paused_interval_5min",
        "import_paused_account_paused",
        "import_paused_needs_test",
        "import_cancelled_credentials_changed",
        "import_cancelled_connection_removed",
        "import_cancelled_by_user",
        "import_cancelled_actor_inactive",
        "import_stopped_no_older_data",
        "import_completed_with_failures",
        "key_expiry_risk",
        "worker_offline",
        "gap_recovery",
    }
)


def slot_seconds(code: str) -> int:
    item = provider(code)
    return item["min_interval_seconds"] + item["slot_guard_seconds"]


def backfill_slots_per_cycle(code: str, interval: int) -> int:
    slot = slot_seconds(code)
    return max(0, (interval - slot + LIVE_SLIP_SECONDS) // slot)


def windows_per_hour(code: str, interval: int) -> float:
    return backfill_slots_per_cycle(code, interval) * 3600 / interval


def history_floor(code: str, now: datetime) -> datetime:
    return now - timedelta(days=provider(code)["history_days"]) + HISTORY_MARGIN


def ist_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), IST).astimezone(timezone.utc)


def align(code: str, start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if provider(code)["window_unit"] != "day":
        return start, end
    # Day-based providers take whole IST calendar days, so widen to midnight boundaries.
    first = start.astimezone(IST).date()
    if ist_midnight(first) < start:
        first += timedelta(days=1)
    last = (end - timedelta(microseconds=1)).astimezone(IST).date()
    return ist_midnight(first), ist_midnight(last + timedelta(days=1))


def live_window(
    code: str, watermark: datetime, now: datetime
) -> tuple[datetime, datetime, tuple[datetime, datetime] | None]:
    """Returns the live request window and the older missed range to hand to the history ledger, if any."""
    item = provider(code)
    size = timedelta(seconds=item["max_window_seconds"])
    if item["window_unit"] == "day":
        # Whole IST days are fetched, so the overlap is the day containing the watermark.
        start = ist_midnight(watermark.astimezone(IST).date())
        today = ist_midnight(now.astimezone(IST).date())
        if start < today - size:
            return today, now, (start, today)
        return start, min(now, start + timedelta(days=1)), None
    start = watermark - timedelta(minutes=5)
    if now - start > size:
        return now - size, now, (start, now - size + timedelta(minutes=5))
    return start, now, None


def plan_windows(
    code: str, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    start, end = align(code, start, end)
    size = timedelta(seconds=provider(code)["max_window_seconds"])
    windows, cursor = [], end
    while cursor > start:
        begin = max(start, cursor - size)
        windows.append((begin, cursor))
        cursor = begin
    return windows


def split_window(
    code: str, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]] | None:
    if provider(code)["window_unit"] == "day":
        days = round((end - start) / timedelta(days=1))
        if days < 2:
            return None
        middle = start + timedelta(days=days // 2)
    else:
        if (end - start).total_seconds() < 2 * MIN_SPLIT_SECONDS:
            return None
        middle = (start + (end - start) / 2).replace(microsecond=0)
    return [(middle, end), (start, middle)]


def backoff(attempts: int) -> timedelta:
    return min(timedelta(minutes=5) * 2 ** max(attempts - 1, 0), timedelta(hours=2))


def _later(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def live_status(
    account: dict, key_available_at: datetime | None, worker_online: bool, now: datetime
) -> dict:
    next_request = _later(account.get("next_allowed_at"), key_available_at, now)
    status = {
        "state": "off",
        "reason": None,
        "until": None,
        "next_request_at": next_request,
    }
    last_request = account.get("last_request_at")
    if account["status"] != "active":
        if (
            account["provider_code"] == "indiamart"
            and last_request is not None
            and now - last_request >= timedelta(days=KEY_EXPIRY_WARNING_DAYS)
        ):
            status.update(
                reason="key_expiry_risk",
                until=last_request + timedelta(days=KEY_EXPIRY_DAYS),
            )
        return status
    hold, until = account.get("hold_reason"), account.get("hold_until")
    if not worker_online:
        return {**status, "state": "held", "reason": "worker_offline"}
    if account.get("last_run_state") == "running":
        return {**status, "state": "running"}
    if hold and until and until > now:
        return {**status, "state": "held", "reason": hold, "until": until}
    if (
        key_available_at
        and key_available_at > now
        and key_available_at > (account.get("next_allowed_at") or now)
    ):
        return {
            **status,
            "state": "waiting",
            "reason": "shared_key_slot",
            "until": key_available_at,
        }
    if account["next_live_at"] <= now and next_request > now:
        return {
            **status,
            "state": "waiting",
            "reason": "waiting_key_slot",
            "until": next_request,
        }
    return {
        **status,
        "state": "scheduled",
        "until": _later(account["next_live_at"], next_request),
    }


def history_status(
    account: dict, backfill: dict | None, worker_online: bool, now: datetime
) -> dict | None:
    if not backfill:
        return None
    pending = backfill["windows_pending"] + backfill["windows_running"]
    status = {
        key: backfill[key]
        for key in (
            "id",
            "kind",
            "state",
            "range_start",
            "range_end",
            "windows_total",
            "windows_done",
            "windows_failed",
            "windows_pending",
            "fetched_count",
            "accepted_count",
            "created_at",
            "finished_at",
        )
    }
    status.update(reason=backfill["hold_reason"], until=None, eta=None)
    if backfill["state"] != "active":
        return status
    rate = windows_per_hour(account["provider_code"], account["sync_interval_seconds"])
    verified = account["verified_version"] == account["credential_version"]
    if not worker_online:
        status["reason"] = "worker_offline"
    elif account["status"] == "paused":
        status["reason"] = "import_paused_account_paused"
    elif account["status"] != "active" or not verified:
        status["reason"] = "import_paused_needs_test"
    elif not rate:
        status["reason"] = "import_paused_interval_5min"
    else:
        held = backfill["hold_until"] and backfill["hold_until"] > now
        status.update(
            reason=backfill["hold_reason"] if held else "gap_recovery" if backfill["kind"] == "gap" else None,
            until=backfill["hold_until"] if held else None,
            eta=_later(now, backfill["hold_until"]) + timedelta(hours=pending / rate),
        )
    return status
