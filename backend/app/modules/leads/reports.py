import asyncio
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.service import AccessError, audit
from .export import XLSX
from .queries import JOINS, access, visibility

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])
MAX_DAYS = 366
UNASSIGNED = "Unassigned"


def report_range(
    start: date | None = None, end: date | None = Query(None)
) -> tuple[date | None, date | None]:
    if start and end and (start > end or (end - start).days >= MAX_DAYS):
        raise AccessError(422, "invalid_date_range")
    return start, end


Range = Annotated[tuple[date | None, date | None], Depends(report_range)]


async def build_report(
    connection, current, requested: tuple[date | None, date | None]
) -> dict:
    zone_name = (
        await connection.scalar(
            text("SELECT timezone FROM crm.organizations WHERE id=:org"),
            {"org": current.org_id},
        )
        or "UTC"
    )
    try:
        today = datetime.now(ZoneInfo(zone_name)).date()
    except ZoneInfoNotFoundError:
        zone_name, today = "UTC", datetime.now(timezone.utc).date()
    end = requested[1] or today
    start = requested[0] or end - timedelta(days=6)
    if start > end or (end - start).days >= MAX_DAYS:
        raise AccessError(422, "invalid_date_range")
    parameters = {
        "org": current.org_id,
        "member": current.member_id,
        "zone": zone_name,
        "start": start,
        "end": end,
    }

    def within(column: str) -> str:
        return (
            f"{column}>=(CAST(:start AS date)::timestamp AT TIME ZONE :zone) "
            f"AND {column}<((CAST(:end AS date)+1)::timestamp AT TIME ZONE :zone)"
        )

    boundary = f"l.org_id=:org AND l.archived_at IS NULL AND {visibility(current)}"
    follow = (
        (
            await connection.execute(
                text(
                    "SELECT l.assigned_membership_id AS member_id,COALESCE(m.display_name,:none) AS name,"
                    "count(*) FILTER(WHERE l.next_follow_up_at<now()) AS missed,"
                    "count(*) FILTER(WHERE l.next_follow_up_at>=now()) AS upcoming "
                    f"{JOINS} WHERE {boundary} AND l.next_follow_up_at IS NOT NULL AND {within('l.next_follow_up_at')} "
                    "AND s.category NOT IN ('won','lost') GROUP BY l.assigned_membership_id,m.display_name"
                ),
                {**parameters, "none": UNASSIGNED},
            )
        )
        .mappings()
        .all()
    )
    done = (
        (
            await connection.execute(
                text(
                    "SELECT l.assigned_membership_id AS member_id,COALESCE(m.display_name,:none) AS name,count(*) AS completed "
                    "FROM crm.lead_status_history h JOIN crm.leads l ON l.org_id=h.org_id AND l.id=h.lead_id "
                    "LEFT JOIN crm.organization_memberships m ON m.org_id=l.org_id AND m.id=l.assigned_membership_id "
                    f"WHERE {boundary} AND {within('h.created_at')} GROUP BY l.assigned_membership_id,m.display_name"
                ),
                {**parameters, "none": UNASSIGNED},
            )
        )
        .mappings()
        .all()
    )
    people: dict = {}
    for row in follow:
        people[row["member_id"]] = {
            "member_id": row["member_id"],
            "name": row["name"],
            "missed": row["missed"],
            "completed": 0,
            "upcoming": row["upcoming"],
        }
    for row in done:
        entry = people.setdefault(
            row["member_id"],
            {
                "member_id": row["member_id"],
                "name": row["name"],
                "missed": 0,
                "completed": 0,
                "upcoming": 0,
            },
        )
        entry["completed"] = row["completed"]
    follow_up = sorted(
        people.values(),
        key=lambda item: (item["name"] == UNASSIGNED, item["name"].lower()),
    )

    statuses = [
        dict(row)
        for row in (
            await connection.execute(
                text(
                    "SELECT id,name,color,category AS type,is_active FROM crm.lead_statuses WHERE org_id=:org ORDER BY is_active DESC,position,name"
                ),
                {"org": current.org_id},
            )
        ).mappings()
    ]
    grouped = (
        (
            await connection.execute(
                text(
                    "SELECT l.assigned_membership_id AS member_id,COALESCE(m.display_name,:none) AS name,l.status_id,count(*) AS count "
                    f"{JOINS} WHERE {boundary} AND {within('l.received_at')} GROUP BY l.assigned_membership_id,m.display_name,l.status_id"
                ),
                {**parameters, "none": UNASSIGNED},
            )
        )
        .mappings()
        .all()
    )
    open_ids = {str(s["id"]) for s in statuses if s["type"] not in ("won", "lost")}
    users: dict = {}
    for row in grouped:
        entry = users.setdefault(
            row["member_id"],
            {
                "member_id": row["member_id"],
                "name": row["name"],
                "is_me": row["member_id"] == current.member_id,
                "total": 0,
                "open": 0,
                "counts": {},
            },
        )
        entry["counts"][str(row["status_id"])] = row["count"]
        entry["total"] += row["count"]
        if str(row["status_id"]) in open_ids:
            entry["open"] += row["count"]
    by_user = sorted(
        users.values(),
        key=lambda item: (
            item["name"] == UNASSIGNED,
            not item["is_me"],
            -item["total"],
            item["name"].lower(),
        ),
    )

    sourced = (
        (
            await connection.execute(
                text(
                    "SELECT l.source_provider AS name,l.status_id,count(*) AS count "
                    f"{JOINS} WHERE {boundary} AND {within('l.received_at')} GROUP BY l.source_provider,l.status_id"
                ),
                parameters,
            )
        )
        .mappings()
        .all()
    )
    sources: dict = {}
    for row in sourced:
        entry = sources.setdefault(
            row["name"], {"name": row["name"], "total": 0, "open": 0, "counts": {}}
        )
        entry["counts"][str(row["status_id"])] = row["count"]
        entry["total"] += row["count"]
        if str(row["status_id"]) in open_ids:
            entry["open"] += row["count"]
    by_source = sorted(
        sources.values(), key=lambda item: (-item["total"], item["name"])
    )
    return {
        "start": start,
        "end": end,
        "timezone": zone_name,
        "statuses": statuses,
        "follow_up": follow_up,
        "by_user": by_user,
        "by_source": by_source,
    }


@router.get("/leads")
async def lead_report(request: Request, user: User, requested: Range):
    async with access(request, user, "reports.view") as (connection, current):
        return await build_report(connection, current, requested)


def sheet_rows(sheet, headers: list[str], rows: list[list]) -> None:
    bold = Font(bold=True)
    for column, header in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=column, value=header)
        cell.font = bold
        sheet.column_dimensions[get_column_letter(column)].width = (
            22 if column > 1 else 30
        )
    for r, values in enumerate(rows, 2):
        for column, value in enumerate(values, 1):
            cell = sheet.cell(
                row=r,
                column=column,
                value=(
                    ILLEGAL_CHARACTERS_RE.sub("", value)
                    if isinstance(value, str)
                    else value
                ),
            )
            if isinstance(value, str):
                cell.data_type = "s"  # never evaluate user-supplied text as a formula
    sheet.freeze_panes = "A2"


def build_report_workbook(report: dict) -> bytes:
    workbook = Workbook()
    follow = workbook.active
    follow.title = "Follow-ups"
    sheet_rows(
        follow,
        ["User", "Missed", "Completed", "Upcoming"],
        [
            [r["name"], r["missed"], r["completed"], r["upcoming"]]
            for r in report["follow_up"]
        ],
    )
    leads = workbook.create_sheet("Leads by user")
    statuses = report["statuses"]
    sheet_rows(
        leads,
        ["User", "Total", "Open"] + [s["name"] for s in statuses],
        [
            [r["name"], r["total"], r["open"]]
            + [r["counts"].get(str(s["id"]), 0) for s in statuses]
            for r in report["by_user"]
        ],
    )
    sources = workbook.create_sheet("By source")
    sheet_rows(
        sources,
        ["Source", "Total", "Open"] + [s["name"] for s in statuses],
        [
            [r["name"], r["total"], r["open"]]
            + [r["counts"].get(str(s["id"]), 0) for s in statuses]
            for r in report["by_source"]
        ],
    )
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@router.get("/leads/export")
async def export_report(request: Request, user: User, requested: Range):
    resources = request.app.state.process_resources
    await resources.acquire_export()
    try:
        return await _build_report_export(request, user, requested, resources)
    finally:
        resources.release_export()


async def _build_report_export(request, user, requested, resources):
    async with access(request, user, "reports.export") as (connection, current):
        report = await build_report(connection, current, requested)
        await audit(
            connection,
            current.org_id,
            current.member_id,
            "reports.exported",
            current.org_id,
        )
    content = await resources.run_export(build_report_workbook, report)
    name = f"lead-report-{report['start']}-to-{report['end']}.xlsx"
    return Response(
        content,
        media_type=XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )
