from datetime import timedelta

from fastapi import APIRouter, Request
from sqlalchemy import text

from ..identity.dependencies import User
from ..identity.service import AccessError
from .queries import JOINS, access, fields, lead_payload, visibility
from .reports import Range

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])


@router.get("/dashboard")
async def dashboard(request: Request, user: User, requested: Range):
    async with access(request, user, "dashboard.view") as (connection, current):
        zone = await connection.scalar(text("SELECT timezone FROM crm.organizations WHERE id=:org"), {"org": current.org_id})
        parameters = {"org": current.org_id, "member": current.member_id, "zone": zone or "UTC"}
        scope_boundary = f"l.org_id=:org AND l.archived_at IS NULL AND {visibility(current)}"
        boundary = scope_boundary
        for key, operator, offset in (("start", ">=", ""), ("end", "<", "+1")):
            value = requested[0 if key == "start" else 1]
            if value is not None:
                parameters[key] = value
                boundary += f" AND l.received_at{operator}((CAST(:{key} AS date){offset})::timestamp AT TIME ZONE :zone)"
        today = await connection.scalar(text("SELECT (now() AT TIME ZONE :zone)::date"), parameters)
        period_end = requested[1] or today
        period_start = requested[0] or period_end - timedelta(days=29)
        if period_start > period_end or (period_end - period_start).days >= 366:
            raise AccessError(422, "invalid_date_range")
        period_days = (period_end - period_start).days + 1
        prior_end = period_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=period_days - 1)
        parameters.update({"period_start": period_start, "period_end": period_end,
                           "prior_start": prior_start, "prior_end": prior_end})
        period_boundary = (
            f"{scope_boundary} AND l.received_at >= ((CAST(:period_start AS date)::timestamp) AT TIME ZONE :zone) "
            "AND l.received_at < (((CAST(:period_end AS date)+1)::timestamp) AT TIME ZONE :zone)"
        )
        totals = (await connection.execute(text(
            "SELECT count(*) AS total,"
            "count(*) FILTER(WHERE (l.received_at AT TIME ZONE :zone)::date=(now() AT TIME ZONE :zone)::date) AS today,"
            "count(*) FILTER(WHERE s.category='won') AS converted,"
            "count(*) FILTER(WHERE s.category='lost') AS lost,"
            "count(*) FILTER(WHERE s.category NOT IN ('won','lost')) AS open,"
            "count(*) FILTER(WHERE l.assigned_membership_id IS NULL) AS unassigned,"
            "count(*) FILTER(WHERE l.next_follow_up_at IS NULL AND s.category NOT IN ('won','lost')) AS unscheduled,"
            "count(*) FILTER(WHERE l.next_follow_up_at>=now() AND s.category NOT IN ('won','lost')) AS upcoming,"
            "count(*) FILTER(WHERE l.next_follow_up_at<now() AND s.category NOT IN ('won','lost')) AS overdue "
            f"{JOINS} WHERE {boundary}"
        ), parameters)).mappings().one()
        statuses = (await connection.execute(text(
            f"SELECT s.id,s.name,s.color,s.category,count(*) AS count {JOINS} WHERE {boundary} GROUP BY s.id,s.name,s.color,s.category ORDER BY count DESC,s.name"
        ), parameters)).mappings().all()
        sources = (await connection.execute(text(
            "SELECT l.source_provider AS name,count(*) AS count,"
            "count(*) FILTER(WHERE s.category='won') AS converted,"
            f"count(*) FILTER(WHERE s.category='lost') AS lost {JOINS} WHERE {boundary} "
            "GROUP BY l.source_provider ORDER BY count DESC,l.source_provider LIMIT 20"
        ), parameters)).mappings().all()
        people = (await connection.execute(text(
            "SELECT l.assigned_membership_id AS id,COALESCE(m.display_name,'Unassigned') AS name,count(*) AS total,"
            "count(*) FILTER(WHERE s.category='won') AS converted,"
            "count(*) FILTER(WHERE s.category='lost') AS lost,"
            "count(*) FILTER(WHERE s.category NOT IN ('won','lost')) AS open,"
            "count(*) FILTER(WHERE l.next_follow_up_at<now() AND s.category NOT IN ('won','lost')) AS overdue "
            f"{JOINS} WHERE {boundary} GROUP BY l.assigned_membership_id,m.display_name "
            "ORDER BY total DESC,name,l.assigned_membership_id LIMIT 20"
        ), parameters)).mappings().all()
        repeated = (await connection.execute(text(
            f"WITH visible AS (SELECT l.id,l.phone,l.email FROM crm.leads l WHERE {boundary}),"
            "contacts AS (SELECT id,'p:' || regexp_replace(phone,'[^0-9]','','g') AS contact FROM visible "
            "WHERE length(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'))>=7 UNION ALL "
            "SELECT id,'e:' || lower(btrim(email)) FROM visible WHERE NULLIF(btrim(email),'') IS NOT NULL),"
            "repeated AS (SELECT contact FROM contacts GROUP BY contact HAVING count(DISTINCT id)>1) "
            "SELECT count(DISTINCT contacts.id) AS leads,count(DISTINCT contacts.contact) AS contacts "
            "FROM contacts JOIN repeated USING(contact)"
        ), parameters)).mappings().one()
        aging = (await connection.execute(text(
            "SELECT count(*) FILTER(WHERE l.received_at>=now()-interval '3 days') AS days_0_3,"
            "count(*) FILTER(WHERE l.received_at<now()-interval '3 days' AND l.received_at>=now()-interval '7 days') AS days_4_7,"
            "count(*) FILTER(WHERE l.received_at<now()-interval '7 days' AND l.received_at>=now()-interval '14 days') AS days_8_14,"
            "count(*) FILTER(WHERE l.received_at<now()-interval '14 days' AND l.received_at>=now()-interval '30 days') AS days_15_30,"
            "count(*) FILTER(WHERE l.received_at<now()-interval '30 days') AS days_over_30,"
            "count(*) FILTER(WHERE l.status_changed_at<now()-interval '7 days') AS unchanged_7_days "
            f"{JOINS} WHERE {boundary} AND s.category NOT IN ('won','lost')"
        ), parameters)).mappings().one()
        quality = (await connection.execute(text(
            "SELECT count(*) FILTER(WHERE NULLIF(btrim(l.phone),'') IS NULL AND NULLIF(btrim(l.email),'') IS NULL) AS no_contact,"
            "count(*) FILTER(WHERE NULLIF(btrim(l.city),'') IS NULL) AS no_city "
            f"FROM crm.leads l WHERE {boundary}"
        ), parameters)).mappings().one()
        update_speed = (await connection.execute(text(
            "WITH first_updates AS (SELECT l.id,EXTRACT(EPOCH FROM (first_update.updated_at-l.received_at))/86400 AS days "
            "FROM crm.leads l JOIN LATERAL (SELECT min(h.created_at) AS updated_at FROM crm.lead_status_history h "
            "WHERE h.org_id=l.org_id AND h.lead_id=l.id AND h.created_at>=l.received_at) first_update ON first_update.updated_at IS NOT NULL "
            f"WHERE {period_boundary}) "
            "SELECT count(*) AS updated,round(avg(days)::numeric,1) AS average_days,"
            "round(percentile_cont(0.5) WITHIN GROUP (ORDER BY days)::numeric,1) AS median_days FROM first_updates"
        ), parameters)).mappings().one()
        period = (await connection.execute(text(
            "SELECT count(*) FILTER(WHERE l.received_at>=CAST(:period_start AS date)::timestamp AT TIME ZONE :zone "
            "AND l.received_at<(CAST(:period_end AS date)+1)::timestamp AT TIME ZONE :zone) AS received,"
            "count(*) FILTER(WHERE l.received_at>=CAST(:prior_start AS date)::timestamp AT TIME ZONE :zone "
            "AND l.received_at<(CAST(:prior_end AS date)+1)::timestamp AT TIME ZONE :zone) AS previous_received,"
            "count(*) FILTER(WHERE l.received_at>=CAST(:period_start AS date)::timestamp AT TIME ZONE :zone "
            "AND l.received_at<(CAST(:period_end AS date)+1)::timestamp AT TIME ZONE :zone AND s.category='won') AS converted,"
            "count(*) FILTER(WHERE l.received_at>=CAST(:prior_start AS date)::timestamp AT TIME ZONE :zone "
            "AND l.received_at<(CAST(:prior_end AS date)+1)::timestamp AT TIME ZONE :zone AND s.category='won') AS previous_converted,"
            "count(*) FILTER(WHERE l.received_at>=CAST(:period_start AS date)::timestamp AT TIME ZONE :zone "
            "AND l.received_at<(CAST(:period_end AS date)+1)::timestamp AT TIME ZONE :zone AND s.category='lost') AS lost,"
            "count(*) FILTER(WHERE l.received_at>=CAST(:prior_start AS date)::timestamp AT TIME ZONE :zone "
            "AND l.received_at<(CAST(:prior_end AS date)+1)::timestamp AT TIME ZONE :zone AND s.category='lost') AS previous_lost "
            f"{JOINS} WHERE {scope_boundary}"
        ), parameters)).mappings().one()
        period = {**dict(period), "start": period_start.isoformat(), "end": period_end.isoformat(),
                  "previous_start": prior_start.isoformat(), "previous_end": prior_end.isoformat()}
        movement = (await connection.execute(text(
            "SELECT h.to_status AS name,s.category,count(*) AS transitions,count(DISTINCT h.lead_id) AS leads "
            "FROM crm.lead_status_history h JOIN crm.leads l ON l.org_id=h.org_id AND l.id=h.lead_id "
            "JOIN crm.lead_statuses s ON s.org_id=h.org_id AND s.name=h.to_status "
            f"WHERE {scope_boundary} AND h.created_at>=(CAST(:period_start AS date)::timestamp AT TIME ZONE :zone) "
            "AND h.created_at<((CAST(:period_end AS date)+1)::timestamp AT TIME ZONE :zone) "
            "GROUP BY h.to_status,s.category ORDER BY transitions DESC,h.to_status"
        ), parameters)).mappings().all()
        outcome_events = {"conversion_events": 0, "converted_leads": 0, "loss_events": 0, "lost_leads": 0}
        stage_activity = []
        for row in movement:
            stage_activity.append({"name": row["name"], "transitions": row["transitions"], "leads": row["leads"]})
            if row["category"] == "won":
                outcome_events["conversion_events"] += row["transitions"]
                outcome_events["converted_leads"] += row["leads"]
            elif row["category"] == "lost":
                outcome_events["loss_events"] += row["transitions"]
                outcome_events["lost_leads"] += row["leads"]
        trend = (await connection.execute(text(
            "WITH days AS (SELECT generate_series("
            "COALESCE(CAST(:trend_end AS date),(now() AT TIME ZONE :zone)::date)-29,"
            "COALESCE(CAST(:trend_end AS date),(now() AT TIME ZONE :zone)::date),interval '1 day')::date AS day),"
            "counts AS (SELECT (l.received_at AT TIME ZONE :zone)::date AS day,count(*) AS received,"
            "count(*) FILTER(WHERE s.category='won') AS converted "
            f"{JOINS} WHERE {boundary} AND l.received_at>=((COALESCE(CAST(:trend_end AS date),"
            "(now() AT TIME ZONE :zone)::date)-29)::timestamp AT TIME ZONE :zone) "
            "GROUP BY (l.received_at AT TIME ZONE :zone)::date) "
            ", movement AS (SELECT (h.created_at AT TIME ZONE :zone)::date AS day,"
            "count(*) FILTER(WHERE s.category='won') AS won_events,count(*) FILTER(WHERE s.category='lost') AS lost_events "
            "FROM crm.lead_status_history h JOIN crm.leads l ON l.org_id=h.org_id AND l.id=h.lead_id "
            "JOIN crm.lead_statuses s ON s.org_id=h.org_id AND s.name=h.to_status "
            f"WHERE {scope_boundary} AND h.created_at>=((COALESCE(CAST(:trend_end AS date),"
            "(now() AT TIME ZONE :zone)::date)-29)::timestamp AT TIME ZONE :zone) "
            "AND h.created_at<((COALESCE(CAST(:trend_end AS date),(now() AT TIME ZONE :zone)::date)+1)::timestamp AT TIME ZONE :zone) "
            "GROUP BY (h.created_at AT TIME ZONE :zone)::date) "
            "SELECT days.day,COALESCE(counts.received,0) AS received,COALESCE(counts.converted,0) AS converted,"
            "COALESCE(movement.won_events,0) AS won_events,COALESCE(movement.lost_events,0) AS lost_events "
            "FROM days LEFT JOIN counts USING(day) LEFT JOIN movement USING(day) ORDER BY days.day"
        ), {**parameters, "trend_end": requested[1]})).mappings().all()
        recent = []
        if "leads.view" in current.permissions:
            recent = [lead_payload(row) for row in (await connection.execute(text(
                f"SELECT {fields(current)} {JOINS} WHERE {boundary} ORDER BY l.received_at DESC,l.id DESC LIMIT 5"
            ), parameters)).mappings()]
        return {**dict(totals), "timezone": parameters["zone"], "repeat_leads": repeated["leads"],
            "repeat_contacts": repeated["contacts"], "people": [dict(row) for row in people],
            "trend": [dict(row) for row in trend], "statuses": [dict(row) for row in statuses],
            "aging": dict(aging), "quality": dict(quality), "update_speed": dict(update_speed),
                "period": period, "outcomes": outcome_events, "stage_activity": stage_activity,
                "sources": [dict(row) for row in sources], "recent": recent}
