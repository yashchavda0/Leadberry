from fastapi import APIRouter, Request
from sqlalchemy import text

from ..identity.dependencies import User
from .queries import JOINS, access, fields, visibility

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])


@router.get("/dashboard")
async def dashboard(request: Request, user: User):
    async with access(request, user, "dashboard.view") as (connection, current):
        zone = await connection.scalar(text("SELECT timezone FROM crm.organizations WHERE id=:org"), {"org": current.org_id})
        parameters = {"org": current.org_id, "member": current.member_id, "zone": zone}
        boundary = f"l.org_id=:org AND l.archived_at IS NULL AND {visibility(current)}"
        totals = (await connection.execute(text(
            "SELECT count(*) AS total,"
            "count(*) FILTER(WHERE (l.received_at AT TIME ZONE :zone)::date=(now() AT TIME ZONE :zone)::date) AS today,"
            "count(*) FILTER(WHERE s.category='won') AS converted,"
            "count(*) FILTER(WHERE l.next_follow_up_at<now() AND s.category NOT IN ('won','lost')) AS overdue "
            f"{JOINS} WHERE {boundary}"
        ), parameters)).mappings().one()
        statuses = (await connection.execute(text(
            f"SELECT s.name,s.color,count(*) AS count {JOINS} WHERE {boundary} GROUP BY s.name,s.color ORDER BY count DESC,s.name"
        ), parameters)).mappings().all()
        sources = (await connection.execute(text(
            f"SELECT l.source_provider AS name,count(*) AS count FROM crm.leads l WHERE {boundary} "
            "GROUP BY l.source_provider ORDER BY count DESC,l.source_provider LIMIT 20"
        ), parameters)).mappings().all()
        recent = []
        if "leads.view" in current.permissions:
            recent = [dict(row) for row in (await connection.execute(text(
                f"SELECT {fields(current)} {JOINS} WHERE {boundary} ORDER BY l.received_at DESC,l.id DESC LIMIT 5"
            ), parameters)).mappings()]
        return {**dict(totals), "statuses": [dict(row) for row in statuses],
                "sources": [dict(row) for row in sources], "recent": recent}
