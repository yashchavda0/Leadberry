import asyncio
import itertools
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

OWNER_ADDRESSES = itertools.count(1)


@pytest.fixture
def owner():
    runtime = os.environ.get("TEST_RUNTIME_DATABASE_URL")
    identity = os.environ.get("TEST_AUTH_DATABASE_URL")
    if not runtime or not identity:
        pytest.skip("Requires the disposable PostgreSQL test runner")
    app = create_app(Settings(database_url=runtime, auth_database_url=identity, app_environment="test"))
    options = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    with TestClient(app, backend_options=options, client=(f"198.18.0.{next(OWNER_ADDRESSES)}", 50000)) as client:
        response = client.post("/api/v1/organizations/onboard", json={
            "organization_slug": f"management-{uuid4()}",
            "organization_name": "Management test",
            "full_name": "Owner",
            "email": f"{uuid4()}@example.com",
            "password": f"test-password-{uuid4()}",
        })
        assert response.status_code == 201, response.text
        client.headers["X-CSRF-Token"] = client.cookies["crm_csrf"]
        yield client


def create_role(client, name, parent=None, permissions=None):
    response = client.post("/api/v1/roles", json={
        "name": name, "reports_to_role_id": parent, "permissions": permissions or [],
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_hierarchy_levels_reparenting_cycles_and_tenant_boundary(owner):
    director = create_role(owner, "Director", permissions=["dashboard.view"])
    manager = create_role(owner, "Manager", director)
    agent = create_role(owner, "Agent", manager, ["leads.view"])
    rows = {row["id"]: row for row in owner.get("/api/v1/roles").json()["data"]}
    assert [rows[role]["level"] for role in (director, manager, agent)] == [1, 2, 3]
    assert rows[director]["role_type"] == "Parent"
    assert rows[agent]["role_type"] == "Child"
    assert rows[agent]["reports_to_name"] == "Manager"
    assert rows[manager]["permissions"] == []
    for parent in (director, agent):
        response = owner.put(f"/api/v1/roles/{director}", json={"name": "Director", "reports_to_role_id": parent})
        assert response.status_code == 422
        assert response.json()["code"] == "role_hierarchy_cycle"
    with TestClient(create_app(owner.app.state.configuration), backend_options={"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}) as other:
        other.post("/api/v1/organizations/onboard", json={
            "organization_slug": f"other-{uuid4()}", "organization_name": "Other",
            "full_name": "Other Owner", "email": f"{uuid4()}@example.com",
            "password": f"test-password-{uuid4()}",
        })
        other.headers["X-CSRF-Token"] = other.cookies["crm_csrf"]
        foreign = create_role(other, "Foreign")
        foreign_member = other.get("/api/v1/auth/me").json()["membership_id"]
        foreign_email = other.get("/api/v1/memberships").json()["data"][0]["email"]
        assert foreign_email not in {row["email"] for row in owner.get("/api/v1/memberships").json()["data"]}
    assert owner.delete(f"/api/v1/memberships/{foreign_member}").status_code == 404
    response = owner.put(f"/api/v1/roles/{manager}", json={"name": "Manager", "reports_to_role_id": foreign})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_reporting_role"
    response = owner.put(f"/api/v1/roles/{manager}", json={"name": "Manager"})
    assert response.status_code == 200
    rows = {row["id"]: row for row in owner.get("/api/v1/roles").json()["data"]}
    assert rows[manager]["level"] == 1
    assert rows[agent]["level"] == 2
    assert rows[agent]["reports_to_role_id"] == manager
    assert rows[agent]["permissions"] == ["leads.view"]
    assert owner.get("/api/v1/health/ready").status_code == 200


def test_landing_page_invite_membership_overrides_and_owner(owner):
    role = create_role(owner, "Agent", permissions=["leads.view"])
    body = {"display_name": "Agent", "email": f"{uuid4()}@example.com",
            "role_ids": [role], "landing_page": "/"}
    response = owner.post("/api/v1/invitations", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "landing_page_not_allowed"
    body["landing_page"] = "/leads"
    response = owner.post("/api/v1/invitations", json=body)
    assert response.status_code == 201, response.text
    invited = response.json()
    member = invited["membership_id"]
    options = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    with TestClient(create_app(owner.app.state.configuration), backend_options=options) as agent:
        response = agent.post("/api/v1/auth/accept-invite", json={
            "invitation_token": invited["invitation_token"], "password": f"test-password-{uuid4()}",
        })
        assert response.status_code == 200, response.text
        me = agent.get("/api/v1/auth/me").json()
        assert me["landing_page"] == "/leads"
        assert me["permissions"] == ["leads.view"]
        assert me["data_scope"] == "own"
        agent.headers["X-CSRF-Token"] = agent.cookies["crm_csrf"]
        assert agent.delete(f"/api/v1/memberships/{member}").status_code == 403
        update = {"status": "active", "role_ids": [role], "landing_page": "/",
                  "permission_overrides": {"dashboard.view": True}}
        response = owner.put(f"/api/v1/memberships/{member}", json=update)
        assert response.status_code == 200, response.text
        assert agent.get("/api/v1/auth/me").json()["landing_page"] == "/"
        update["permission_overrides"] = {"dashboard.view": False}
        response = owner.put(f"/api/v1/memberships/{member}", json=update)
        assert response.status_code == 422
        assert response.json()["code"] == "landing_page_not_allowed"
        update["landing_page"] = "/account"
        assert owner.put(f"/api/v1/memberships/{member}", json=update).status_code == 200
        assert agent.get("/api/v1/auth/me").json()["landing_page"] == "/account"
        update["display_name"] = "Updated Agent"
        assert owner.put(f"/api/v1/memberships/{member}", json=update).status_code == 200
        assert owner.put(f"/api/v1/memberships/{member}", json={**update, "email": "changed@example.com"}).status_code == 422
        assert agent.get("/api/v1/leads/assignees").status_code == 403
        update["permission_overrides"] = {"leads.assign": True}
        assert owner.put(f"/api/v1/memberships/{member}", json=update).status_code == 200
        assert agent.get("/api/v1/leads/assignees").status_code == 200
        lead = owner.post("/api/v1/leads", json={"name": "Preserved lead", "assigned_membership_id": member}).json()["id"]
        assert owner.delete(f"/api/v1/memberships/{uuid4()}").status_code == 404
        assert owner.delete(f"/api/v1/memberships/{member}").status_code == 200
        assert agent.get("/api/v1/auth/me").status_code == 401
        assert owner.get(f"/api/v1/leads/{lead}").json()["assigned_membership_id"] == member
        rows = {row["id"]: row for row in owner.get("/api/v1/memberships").json()["data"]}
        assert rows[member]["email"] == body["email"]
        assert rows[member]["display_name"] == "Updated Agent"
        assert rows[member]["status"] == "disabled"
        assert rows[member]["role_ids"] == [role]
        assert rows[member]["permission_overrides"] == {"leads.assign": True}
        assert owner.put(f"/api/v1/memberships/{member}", json=update).status_code == 200
    rows = {row["id"]: row for row in owner.get("/api/v1/memberships").json()["data"]}
    assert rows[member]["landing_page"] == "/account"
    own = owner.get("/api/v1/auth/me").json()["membership_id"]
    assert owner.put(f"/api/v1/memberships/{own}", json={
        "status": "active", "role_ids": [], "landing_page": "/users",
    }).status_code == 200
    assert owner.get("/api/v1/auth/me").json()["landing_page"] == "/users"


def test_invitation_recovery_and_personal_profiles(owner):
    assert owner.get("/api/v1/auth/me").json()["display_name"] == "Owner"
    assert owner.put("/api/v1/auth/profile", json={"display_name": "Workspace Owner"}).status_code == 204
    assert owner.get("/api/v1/auth/me").json()["display_name"] == "Workspace Owner"

    body = {"display_name": "Invited Agent", "email": f"{uuid4()}@example.com"}
    original_response = owner.post("/api/v1/invitations", json=body)
    assert original_response.status_code == 201, original_response.text
    original = original_response.json()
    path = f"/api/v1/memberships/{original['membership_id']}/invitation"
    recovered = owner.get(path)
    assert recovered.status_code == 200, recovered.text
    assert recovered.headers["Cache-Control"] == "no-store"
    assert recovered.json()["invitation_token"] == original["invitation_token"]
    assert "invitation_token" not in owner.get("/api/v1/memberships").text

    reissued = owner.post("/api/v1/invitations", json=body).json()
    assert owner.get(path).json()["invitation_token"] == reissued["invitation_token"]
    assert reissued["invitation_token"] != original["invitation_token"]
    options = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    with TestClient(create_app(owner.app.state.configuration), backend_options=options) as agent:
        password = f"test-password-{uuid4()}"
        accept_path = "/api/v1/auth/accept-invite"
        assert agent.post(accept_path, json={"invitation_token": original["invitation_token"], "password": password}).status_code == 401
        accepted = agent.post(accept_path, json={"invitation_token": reissued["invitation_token"], "password": password})
        assert accepted.status_code == 200, accepted.text
        assert owner.get(path).status_code == 404
        pending = owner.post("/api/v1/invitations", json={**body, "email": f"{uuid4()}@example.com"}).json()
        assert agent.get(f"/api/v1/memberships/{pending['membership_id']}/invitation").status_code == 403
        assert agent.get("/api/v1/auth/me").json()["display_name"] == body["display_name"]
        profile_path = "/api/v1/auth/profile"
        assert agent.get(profile_path).json() == {**body, "phone": None, "job_title": None}
        updated = {"display_name": "Renamed Agent", "phone": "+1 202 555 0110", "job_title": "Sales specialist"}
        assert agent.put(profile_path, json=updated).status_code == 403
        agent.headers["X-CSRF-Token"] = agent.cookies["crm_csrf"]
        assert agent.put(profile_path, json={"display_name": "  "}).status_code == 422
        assert agent.put(profile_path, json=updated).status_code == 204
        assert agent.get(profile_path).json() == {**updated, "email": body["email"]}
        assert agent.get("/api/v1/auth/me").json()["display_name"] == updated["display_name"]
        assert owner.get("/api/v1/auth/me").json()["display_name"] == "Workspace Owner"


def test_invitation_recovery_stops_at_expiry(owner):
    from sqlalchemy import text
    from app.core.database import tenant_transaction

    invitation = owner.post("/api/v1/invitations", json={"display_name": "Pending", "email": f"{uuid4()}@example.com"}).json()
    org_id = UUID(owner.get("/api/v1/auth/me").json()["organization_id"])

    async def expire():
        async with tenant_transaction(owner.app.state.identity_service.engine, org_id) as connection:
            await connection.execute(
                text("UPDATE crm.organization_invitations SET expires_at=now()-interval '1 second' "
                     "WHERE org_id=:org AND membership_id=:member"),
                {"org": org_id, "member": UUID(invitation["membership_id"])},
            )

    owner.portal.call(expire)
    assert owner.get(f"/api/v1/memberships/{invitation['membership_id']}/invitation").status_code == 404
    assert owner.delete(f"/api/v1/memberships/{own}").status_code == 409
    assert owner.get("/api/v1/auth/me").status_code == 200
    pending = owner.post("/api/v1/invitations", json={
        "display_name": "Pending", "email": f"{uuid4()}@example.com",
    }).json()
    assert owner.delete(f"/api/v1/memberships/{pending['membership_id']}").status_code == 200
    assert owner.put(f"/api/v1/memberships/{pending['membership_id']}", json={"status": "active"}).status_code == 409
    with TestClient(create_app(owner.app.state.configuration), backend_options=options) as pending_client:
        assert pending_client.post("/api/v1/auth/accept-invite", json={
            "invitation_token": pending["invitation_token"], "password": f"test-password-{uuid4()}",
        }).status_code == 401


def test_lead_sort_is_global_across_cursor_pages(owner):
    import base64
    import json

    companies = ["Zulu", "Alpha", "Echo", "Alpha", "Delta", "Bravo"]
    for index, company in enumerate(companies):
        response = owner.post("/api/v1/leads", json={"name": f"Sortbatch {index}", "company": company})
        assert response.status_code == 201, response.text
    for direction in ("asc", "desc"):
        cursor = None
        results = []
        while True:
            params = {"q": "Sortbatch", "limit": 2, "sort_by": "company", "sort_dir": direction}
            if cursor:
                params["after"] = cursor
            response = owner.get("/api/v1/leads", params=params)
            assert response.status_code == 200, response.text
            body = response.json()
            results.extend(body["data"])
            cursor = body["next_cursor"]
            if not cursor:
                break
        assert [lead["company"] for lead in results] == sorted(companies, reverse=direction == "desc")
        assert len({lead["id"] for lead in results}) == len(companies)
    response = owner.get("/api/v1/leads", params={"q": "Sortbatch", "limit": 2, "sort_by": "company", "sort_dir": "asc"})
    cursor = response.json()["next_cursor"]
    assert owner.get("/api/v1/leads", params={"after": cursor, "sort_by": "company", "sort_dir": "desc"}).status_code == 422
    altered = json.loads(base64.urlsafe_b64decode(cursor))
    altered["id"] = 123
    malformed = base64.urlsafe_b64encode(json.dumps(altered).encode()).decode()
    assert owner.get("/api/v1/leads", params={"after": malformed, "sort_by": "company", "sort_dir": "asc"}).status_code == 422
    assert owner.get("/api/v1/leads", params={"sort_by": "name; DROP TABLE crm.leads"}).status_code == 422
    assert owner.get("/api/v1/leads", params={"limit": 101}).status_code == 422
    for sort_by in ("name", "company", "email", "phone", "city", "state", "address", "product", "enquiry", "status_changed_at", "status", "source_name", "source_provider", "source_record_id", "received_at", "assignee", "team_name", "tags", "next_follow_up_at", "updated_at", "archived_at"):
        response = owner.get("/api/v1/leads", params={"q": "Sortbatch", "limit": 2, "sort_by": sort_by})
        assert response.status_code == 200, (sort_by, response.text)
        next_page = owner.get("/api/v1/leads", params={"q": "Sortbatch", "limit": 2, "sort_by": sort_by, "after": response.json()["next_cursor"]})
        assert next_page.status_code == 200, (sort_by, next_page.text)
        assert not {lead["id"] for lead in response.json()["data"]} & {lead["id"] for lead in next_page.json()["data"]}


def test_lead_sort_custom_numbers_and_nulls(owner):
    field = owner.post("/api/v1/lead-custom-fields", json={"field_key": "budget", "label": "Budget", "field_type": "number", "options": [], "position": 0, "is_active": True})
    assert field.status_code == 201, field.text
    field = owner.post("/api/v1/lead-custom-fields", json={"field_key": "consent", "label": "Consent", "field_type": "boolean", "options": [], "position": 1, "is_active": True})
    assert field.status_code == 201, field.text
    for index, value in enumerate([10, None, 2, 1, None]):
        custom = {} if value is None else {"budget": value, "consent": value != 2}
        response = owner.post("/api/v1/leads", json={"name": f"Budgetbatch {index}", "custom_fields": custom})
        assert response.status_code == 201, response.text
    for sort_by, direction, expected in (("budget", "asc", [1, 2, 10, None, None]), ("budget", "desc", [10, 2, 1, None, None]), ("consent", "asc", [False, True, True, None, None]), ("consent", "desc", [True, True, False, None, None])):
        cursor = None
        results = []
        while True:
            params = {"q": "Budgetbatch", "limit": 2, "sort_by": f"custom:{sort_by}", "sort_dir": direction}
            if cursor:
                params["after"] = cursor
            response = owner.get("/api/v1/leads", params=params)
            assert response.status_code == 200, response.text
            body = response.json()
            results.extend(body["data"])
            cursor = body["next_cursor"]
            if not cursor:
                break
        assert [lead["custom_fields"].get(sort_by) for lead in results] == expected
        assert len({lead["id"] for lead in results}) == 5


def test_repeat_customer_requires_an_earlier_conversion(owner):
    from sqlalchemy import text
    from app.core.database import tenant_transaction

    statuses = owner.get("/api/v1/lead-statuses").json()["data"]
    won = next(status["id"] for status in statuses if status["type"] == "won")
    email = f"returning-{uuid4()}@example.com"
    first = owner.post("/api/v1/leads", json={"name": "First enquiry", "email": email, "phone": "+919876543210"}).json()
    before_conversion = owner.post("/api/v1/leads", json={"name": "Earlier enquiry", "email": email.upper()}).json()
    assert before_conversion["is_repeat_customer"] is False
    changed = owner.post(f"/api/v1/leads/{first['id']}/status", json={"status_id": won, "note": "Order received", "row_version": first["row_version"]})
    assert changed.status_code == 200, changed.text
    org = UUID(owner.get("/api/v1/auth/me").json()["organization_id"])
    async def set_legacy_phone():
        async with tenant_transaction(owner.app.state.database_engine, org) as connection:
            await connection.execute(text("UPDATE crm.leads SET phone='+91 98765 43210' WHERE org_id=:org AND id=:id"), {"org": org, "id": UUID(first["id"])})
            assert await connection.scalar(text("SELECT crm.repeat_phone_key('9876543210 ext 1')")) is None
    owner.portal.call(set_legacy_phone)
    after_conversion = owner.post("/api/v1/leads", json={"name": "Returning enquiry", "phone": "9876543210"}).json()
    assert after_conversion["is_repeat_customer"] is True
    assert owner.get(f"/api/v1/leads/{before_conversion['id']}").json()["is_repeat_customer"] is False
    assert owner.get(f"/api/v1/leads/{after_conversion['id']}").json()["is_repeat_customer"] is True
    lost = next(status["id"] for status in statuses if status["type"] == "lost")
    changed_again = owner.post(f"/api/v1/leads/{first['id']}/status", json={"status_id": lost, "note": "Order closed", "row_version": changed.json()["row_version"]})
    assert changed_again.status_code == 200, changed_again.text
    email_repeat = owner.post("/api/v1/leads", json={"name": "Email enquiry", "email": email.upper()}).json()
    assert email_repeat["is_repeat_customer"] is True
    won_email = f"won-on-create-{uuid4()}@example.com"
    assert owner.post("/api/v1/leads", json={"name": "Won directly", "email": won_email, "status_id": won}).status_code == 201
    assert owner.post("/api/v1/leads", json={"name": "Direct won repeat", "email": won_email}).json()["is_repeat_customer"] is True
    edit_email = f"won-on-edit-{uuid4()}@example.com"
    editable = owner.post("/api/v1/leads", json={"name": "Edit conversion", "email": edit_email}).json()
    updated = owner.put(f"/api/v1/leads/{editable['id']}", json={"name": "Edit conversion", "email": edit_email, "status_id": won, "assigned_membership_id": editable["assigned_membership_id"], "row_version": editable["row_version"]})
    assert updated.status_code == 200, updated.text
    assert owner.post("/api/v1/leads", json={"name": "Edit won repeat", "email": edit_email}).json()["is_repeat_customer"] is True


def test_repeat_customer_respects_scope_and_contact_permission(owner):
    role = create_role(owner, "Scoped lead reader", permissions=["leads.view", "leads.pii.view"])
    invite = owner.post("/api/v1/invitations", json={"display_name": "Scoped agent", "email": f"{uuid4()}@example.com", "role_ids": [role], "landing_page": "/leads"}).json()
    options = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    with TestClient(create_app(owner.app.state.configuration), backend_options=options) as agent:
        accepted = agent.post("/api/v1/auth/accept-invite", json={"invitation_token": invite["invitation_token"], "password": f"test-password-{uuid4()}"})
        assert accepted.status_code == 200, accepted.text
        statuses = owner.get("/api/v1/lead-statuses").json()["data"]
        won = next(status["id"] for status in statuses if status["type"] == "won")
        email = f"scoped-{uuid4()}@example.com"
        prior = owner.post("/api/v1/leads", json={"name": "Owner conversion", "email": email, "status_id": won})
        assert prior.status_code == 201, prior.text
        later = owner.post("/api/v1/leads", json={"name": "Agent enquiry", "email": email, "assigned_membership_id": invite["membership_id"]}).json()
        assert later["is_repeat_customer"] is True
        assert agent.get(f"/api/v1/leads/{later['id']}").json()["is_repeat_customer"] is False
        assert next(row for row in agent.get("/api/v1/leads").json()["data"] if row["id"] == later["id"])["is_repeat_customer"] is False
        update = {"status": "active", "role_ids": [role], "landing_page": "/leads", "permission_overrides": {"leads.pii.view": False}}
        assert owner.put(f"/api/v1/memberships/{invite['membership_id']}", json=update).status_code == 200
        assert agent.get(f"/api/v1/leads/{later['id']}").json()["is_repeat_customer"] is None
        assert agent.get("/api/v1/leads", params={"sort_by": "phone"}).status_code == 403
        assert agent.get("/api/v1/leads", params={"sort_by": "custom:budget"}).status_code == 403


def test_dashboard_analytics_outcomes_dates_repeats_and_visibility(owner):
    statuses = {row["type"]: row["id"] for row in owner.get("/api/v1/lead-statuses").json()["data"]}
    owner_id = owner.get("/api/v1/auth/me").json()["membership_id"]
    role = create_role(owner, "Dashboard analyst", permissions=["dashboard.view"])
    invite = owner.post("/api/v1/invitations", json={
        "display_name": "Analyst", "email": f"{uuid4()}@example.com", "role_ids": [role],
    }).json()
    options = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    with TestClient(create_app(owner.app.state.configuration), backend_options=options) as accepting:
        accepted = accepting.post("/api/v1/auth/accept-invite", json={
            "invitation_token": invite["invitation_token"], "password": f"test-password-{uuid4()}",
        })
        assert accepted.status_code == 200, accepted.text
        analyst_cookies = dict(accepting.cookies)
    now = datetime.now(timezone.utc)
    contact = f"repeat-{uuid4()}@example.com"
    payloads = [
        {"name": "Won", "status_id": statuses["won"], "phone": "+919876543210", "email": contact},
        {"name": "Cancelled", "status_id": statuses["lost"], "phone": "+91 98765 43210", "email": contact.upper()},
        {"name": "Overdue", "next_follow_up_at": (now - timedelta(days=1)).isoformat()},
        {"name": "Upcoming", "assigned_membership_id": None, "next_follow_up_at": (now + timedelta(days=1)).isoformat()},
        {"name": "Analyst lead", "assigned_membership_id": invite["membership_id"], "email": contact},
        {"name": "Archived", "phone": "+919876543210"},
    ]
    created = []
    for payload in payloads:
        response = owner.post("/api/v1/leads", json={"assigned_membership_id": owner_id, **payload})
        assert response.status_code == 201, response.text
        created.append(response.json())
    changed = owner.post(f"/api/v1/leads/{created[4]['id']}/status", json={
        "status_id": statuses["won"], "note": "Converted during dashboard test", "row_version": created[4]["row_version"],
    })
    assert changed.status_code == 200, changed.text
    assert owner.post(f"/api/v1/leads/{created[-1]['id']}/archive", json={"row_version": created[-1]["row_version"]}).status_code == 200
    response = owner.get("/api/v1/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert {key: data[key] for key in ("total", "converted", "lost", "open", "overdue", "upcoming", "unscheduled", "unassigned", "repeat_leads", "repeat_contacts")} == {
        "total": 5, "converted": 2, "lost": 1, "open": 2, "overdue": 1, "upcoming": 1,
        "unscheduled": 0, "unassigned": 1, "repeat_leads": 3, "repeat_contacts": 2,
    }
    assert sum(row["count"] for row in data["statuses"]) == data["total"]
    assert sum(row["count"] for row in data["sources"]) == data["total"]
    assert sum(row["total"] for row in data["people"]) == data["total"]
    assert len(data["trend"]) == 30
    assert sum(row["received"] for row in data["trend"]) == 5
    assert sum(row["converted"] for row in data["trend"]) == 2
    assert sum(row["won_events"] for row in data["trend"]) == 1
    assert sum(row["lost_events"] for row in data["trend"]) == 0
    assert all(row["converted"] <= row["received"] for row in data["trend"])
    assert data["period"]["received"] == 5
    assert data["period"]["converted"] == 2
    assert data["period"]["previous_received"] == 0
    assert data["aging"]["days_0_3"] == 2
    assert data["quality"]["no_contact"] == 2
    assert data["update_speed"]["updated"] == 1
    assert data["outcomes"]["converted_leads"] == 1
    assert data["outcomes"]["conversion_events"] == 1
    assert data["stage_activity"] == [{"name": "Converted", "leads": 1, "transitions": 1}]
    assert owner.get("/api/v1/dashboard?start=2025-02-02&end=2025-02-01").status_code == 422
    assert owner.get("/api/v1/dashboard?start=2020-01-01&end=2025-01-01").status_code == 422
    empty = owner.get("/api/v1/dashboard?start=2000-01-01&end=2000-01-31").json()
    assert empty["total"] == empty["repeat_leads"] == 0
    assert len(empty["trend"]) == 30
    assert not any(row["received"] for row in empty["trend"])
    with TestClient(create_app(owner.app.state.configuration), backend_options=options) as analyst:
        analyst.cookies.update(analyst_cookies)
        scoped = analyst.get("/api/v1/dashboard").json()
        assert scoped["total"] == 2
        assert scoped["open"] == scoped["converted"] == 1
        assert scoped["repeat_leads"] == scoped["repeat_contacts"] == 0
        assert scoped["recent"] == []
        assert {row["id"] for row in scoped["people"]} == {None, invite["membership_id"]}
    with TestClient(create_app(owner.app.state.configuration), backend_options=options) as other:
        response = other.post("/api/v1/organizations/onboard", json={
            "organization_slug": f"dashboard-{uuid4()}", "organization_name": "Other dashboard",
            "full_name": "Other", "email": f"{uuid4()}@example.com", "password": f"test-password-{uuid4()}",
        })
        assert response.status_code == 201, response.text
        isolated = other.get("/api/v1/dashboard").json()
        assert isolated["total"] == isolated["repeat_leads"] == 0
