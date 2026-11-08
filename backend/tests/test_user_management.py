import asyncio
import os
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


@pytest.fixture
def owner():
    runtime = os.environ.get("TEST_RUNTIME_DATABASE_URL")
    identity = os.environ.get("TEST_AUTH_DATABASE_URL")
    if not runtime or not identity:
        pytest.skip("Requires the disposable PostgreSQL test runner")
    app = create_app(Settings(database_url=runtime, auth_database_url=identity, app_environment="test"))
    options = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    with TestClient(app, backend_options=options) as client:
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
