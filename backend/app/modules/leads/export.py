import asyncio
from datetime import datetime, timezone
from io import BytesIO
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, Cell
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.service import AccessError, audit
from .filters import LeadFilters, filter_conditions, lead_filters
from .queries import JOINS, access, fields, lead_payload

router = APIRouter(prefix="/api/v1", tags=["Leads"])
EXPORT_LIMIT = 50_000
BATCH_SIZE = 2_000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DATE_FORMAT = "yyyy-mm-dd hh:mm"
# (key, header, width, contact data hidden without leads.pii.view)
COLUMNS = (
    ("name", "Name", 28, False),
    ("company", "Company", 28, False),
    ("phone", "Phone", 18, True),
    ("email", "Email", 28, True),
    ("city", "City", 16, False),
    ("state", "State", 16, False),
    ("address", "Address", 36, True),
    ("product", "Product", 28, False),
    ("enquiry", "Enquiry", 48, True),
    ("status", "Status", 16, False),
    ("assignee", "Assignee", 20, False),
    ("source_provider", "Source", 14, False),
    ("source_account_name", "Connection", 22, False),
    ("source_record_id", "Source record ID", 22, False),
    ("tags", "Tags", 22, False),
    ("received_at", "Received", 18, False),
    ("created_at", "Added to CRM", 18, False),
    ("status_changed_at", "Status changed", 18, False),
    ("next_follow_up_at", "Next follow-up", 18, False),
)


def text_cell(sheet, value: str) -> Cell:
    cell = WriteOnlyCell(sheet, value=ILLEGAL_CHARACTERS_RE.sub("", value))
    # Provider-supplied text such as "=HYPERLINK(...)" must never be evaluated as a formula.
    cell.data_type = "s"
    return cell


def value_cell(sheet, value, zone: ZoneInfo) -> Cell | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        cell = WriteOnlyCell(sheet, value=value.astimezone(zone).replace(tzinfo=None))
        cell.number_format = DATE_FORMAT
        return cell
    if isinstance(value, bool):
        return text_cell(sheet, "Yes" if value else "No")
    if isinstance(value, (int, float)):
        return WriteOnlyCell(sheet, value=value)
    if isinstance(value, (list, tuple)):
        return text_cell(sheet, ", ".join(str(item) for item in value))
    return text_cell(sheet, str(value))


@router.get("/leads/export")
async def export_leads(
    request: Request,
    user: User,
    filters: Annotated[LeadFilters, Depends(lead_filters)],
):
    async with access(request, user, "leads.export") as (connection, current):
        if "leads.view" not in current.permissions:
            raise AccessError(403, "permission_denied")
        conditions, parameters = filter_conditions(current, filters)
        try:
            zone = ZoneInfo(
                await connection.scalar(
                    text("SELECT timezone FROM crm.organizations WHERE id=:org"),
                    {"org": current.org_id},
                )
                or "UTC"
            )
        except (ZoneInfoNotFoundError, ValueError):
            zone = ZoneInfo("UTC")
        pii = "leads.pii.view" in current.permissions
        columns = [column for column in COLUMNS if pii or not column[3]]
        custom = (
            (
                await connection.execute(
                    text(
                        "SELECT field_key,label FROM crm.lead_custom_fields WHERE org_id=:org AND is_active "
                        "ORDER BY position,label"
                    ),
                    {"org": current.org_id},
                )
            )
            .mappings()
            .all()
            if pii
            else []
        )
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("Leads")
        sheet.freeze_panes = "A2"
        headers = [column[1] for column in columns] + [field["label"] for field in custom]
        for index, width in enumerate([column[2] for column in columns] + [20] * len(custom), 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        bold = Font(bold=True)
        header_cells = [text_cell(sheet, header) for header in headers]
        for cell in header_cells:
            cell.font = bold
        sheet.append(header_cells)
        count, cursor = 0, None
        while True:
            batch = list(conditions)
            if cursor:
                batch.append("(l.received_at,l.id)<(:moment,:last)")
            rows = (
                (
                    await connection.execute(
                        text(
                            f"SELECT {fields(current)},l.created_at {JOINS} WHERE {' AND '.join(batch)} "
                            "ORDER BY l.received_at DESC,l.id DESC LIMIT :limit"
                        ),
                        {
                            **parameters,
                            "limit": BATCH_SIZE,
                            **({"moment": cursor[0], "last": cursor[1]} if cursor else {}),
                        },
                    )
                )
                .mappings()
                .all()
            )
            count += len(rows)
            if count > EXPORT_LIMIT:
                raise AccessError(422, "lead_export_too_large")
            for row in rows:
                row = lead_payload(row)
                values = [row[column[0]] for column in columns] + [
                    (row["custom_fields"] or {}).get(field["field_key"]) for field in custom
                ]
                sheet.append([value_cell(sheet, value, zone) for value in values])
            if len(rows) < BATCH_SIZE:
                break
            cursor = (rows[-1]["received_at"], rows[-1]["id"])
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{count + 1}"
        await audit(
            connection, current.org_id, current.member_id, "leads.exported", filters.backfill_id
        )
    buffer = BytesIO()
    await asyncio.to_thread(workbook.save, buffer)
    stamp = datetime.now(timezone.utc).astimezone(zone).strftime("%Y%m%d-%H%M")
    name = f"{'imported-leads' if filters.backfill_id else 'leads'}-{stamp}.xlsx"
    return Response(
        buffer.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )
