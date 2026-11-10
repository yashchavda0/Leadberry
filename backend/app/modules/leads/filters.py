from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import Query

from ..identity.service import AccessError, Principal
from .queries import visibility


@dataclass(frozen=True)
class LeadFilters:
    q: str
    status_id: UUID | None
    source: str
    integration_id: UUID | None
    backfill_id: UUID | None
    source_record_id: str
    tag: str
    assignee: UUID | None
    start: date | None
    end: date | None
    archived: bool
    status_start: date | None
    status_end: date | None


def lead_filters(
    q: str = Query("", max_length=200),
    status_id: UUID | None = None,
    source: str = Query("", max_length=100),
    integration_id: UUID | None = None,
    backfill_id: UUID | None = None,
    source_record_id: str = Query("", max_length=200),
    tag: str = Query("", max_length=50),
    assignee: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    archived: bool = False,
    status_start: date | None = None,
    status_end: date | None = None,
) -> LeadFilters:
    if (start and end and start > end) or (
        status_start and status_end and status_start > status_end
    ):
        raise AccessError(422, "invalid_date_range")
    return LeadFilters(
        q.strip(),
        status_id,
        source,
        integration_id,
        backfill_id,
        source_record_id,
        tag,
        assignee,
        start,
        end,
        archived,
        status_start,
        status_end,
    )


def filter_conditions(current: Principal, filters: LeadFilters) -> tuple[list[str], dict]:
    """Shared by the list and the export so both always return the same leads."""
    if (
        filters.archived
        and "leads.archive" not in current.permissions
        and "leads.restore" not in current.permissions
    ):
        raise AccessError(403, "permission_denied")
    conditions = [
        "l.org_id=:org",
        visibility(current),
        "l.archived_at IS NOT NULL" if filters.archived else "l.archived_at IS NULL",
    ]
    parameters: dict = {"org": current.org_id, "member": current.member_id}
    for enabled, condition, key, value in (
        (bool(filters.q), "l.search_document @@ plainto_tsquery('simple',:q)", "q", filters.q),
        (filters.status_id is not None, "l.status_id=:status", "status", filters.status_id),
        (bool(filters.source), "l.source_provider=:source", "source", filters.source),
        (
            filters.integration_id is not None,
            "l.integration_id=:integration",
            "integration",
            filters.integration_id,
        ),
        (
            filters.backfill_id is not None,
            "l.backfill_id=:backfill",
            "backfill",
            filters.backfill_id,
        ),
        (
            bool(filters.source_record_id),
            "l.source_record_id=:source_record_id",
            "source_record_id",
            filters.source_record_id,
        ),
        (bool(filters.tag), "l.tags @> ARRAY[CAST(:tag AS text)]", "tag", filters.tag),
        (
            filters.assignee is not None,
            "l.assigned_membership_id=:assignee",
            "assignee",
            filters.assignee,
        ),
        (filters.start is not None, "l.received_at>=CAST(:start AS date)", "start", filters.start),
        (
            filters.end is not None,
            "l.received_at<CAST(:end AS date)+interval '1 day'",
            "end",
            filters.end,
        ),
        (
            filters.status_start is not None,
            "l.status_changed_at>=CAST(:status_start AS date)",
            "status_start",
            filters.status_start,
        ),
        (
            filters.status_end is not None,
            "l.status_changed_at<CAST(:status_end AS date)+interval '1 day'",
            "status_end",
            filters.status_end,
        ),
    ):
        if enabled:
            conditions.append(condition)
            parameters[key] = value
    return conditions, parameters
