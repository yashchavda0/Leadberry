from types import SimpleNamespace
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from app.modules.identity.dependencies import principal
from app.modules.identity.schemas import OrganizationInput
from app.modules.identity.service import Principal
from app.modules.leads.queries import fields, visibility

GROUPS = {
    "Authentication": {
        "/auth/login": {"post"},
        "/auth/accept-invite": {"post"},
        "/auth/refresh": {"post"},
        "/auth/logout": {"post"},
        "/auth/me": {"get"},
    },
    "Organizations": {
        "/organizations/onboard": {"post"},
        "/organizations/me": {"get", "put"},
    },
    "Roles and permissions": {
        "/permissions": {"get"},
        "/roles": {"get", "post"},
        "/roles/{role_id}": {"put"},
    },
    "Members and invitations": {
        "/memberships": {"get"},
        "/memberships/{membership_id}": {"put", "delete"},
        "/invitations": {"post"},
    },
    "Leads": {
        "/leads": {"get", "post"},
        "/leads/export": {"get"},
        "/leads/options": {"get"},
        "/leads/assignees": {"get"},
        "/leads/{lead_id}": {"get", "put"},
        "/leads/{lead_id}/status-history": {"get"},
        "/leads/{lead_id}/status": {"post"},
        "/leads/{lead_id}/archive": {"post"},
        "/leads/{lead_id}/restore": {"post"},
    },
    "Lead configuration": {
        "/lead-statuses": {"get", "post"},
        "/lead-status-options": {"get"},
        "/lead-statuses/{status_id}": {"put"},
        "/lead-statuses/{status_id}/rules": {"put"},
        "/lead-custom-fields": {"get", "post"},
        "/lead-custom-fields/{field_key}": {"put"},
        "/lead-table-preferences": {"get", "put"},
    },
    "Teams": {
        "/teams": {"get", "post"},
        "/teams/{team_id}": {"put"},
    },
    "Dashboard": {"/dashboard": {"get"}},
    "Marketplace": {
        "/marketplace/providers": {"get"},
        "/marketplace/accounts": {"get", "post"},
        "/marketplace/accounts/{account_id}": {"put"},
        "/marketplace/accounts/{account_id}/{action}": {"post"},
        "/marketplace/accounts/{account_id}/runs": {"get"},
        "/marketplace/accounts/{account_id}/schedule": {"put"},
        "/marketplace/accounts/{account_id}/backfills": {"get", "post"},
        "/marketplace/accounts/{account_id}/backfills/{backfill_id}/windows": {"get"},
        "/marketplace/accounts/{account_id}/backfills/{backfill_id}/{action}": {"post"},
        "/marketplace/backfills": {"get"},
    },
    "Health": {"/health/live": {"get"}, "/health/ready": {"get"}},
}


@pytest.fixture
def app():
    return create_app(
        Settings(
            database_url="postgresql+psycopg://crm_api@localhost/route_tests",
            auth_database_url=None,
            app_environment="test",
            allowed_origins=["http://localhost:3000"],
        )
    )


def test_all_existing_paths_and_methods_have_exactly_one_group(app):
    paths = app.openapi()["paths"]
    expected_paths = {
        f"/api/v1{path}"
        for paths_in_group in GROUPS.values()
        for path in paths_in_group
    }
    assert paths.keys() == expected_paths
    for group, paths_in_group in GROUPS.items():
        for path, methods in paths_in_group.items():
            assert paths[f"/api/v1{path}"].keys() == methods
            for method in methods:
                assert paths[f"/api/v1{path}"][method]["tags"] == [group]


def test_create_and_logout_status_codes_are_preserved(app):
    paths = app.openapi()["paths"]
    for path in (
        "/organizations/onboard",
        "/roles",
        "/invitations",
        "/leads",
        "/teams",
    ):
        assert "201" in paths[f"/api/v1{path}"]["post"]["responses"]
    assert "204" in paths["/api/v1/auth/logout"]["post"]["responses"]


@pytest.mark.parametrize(
    "path",
    [
        "/auth/me",
        "/organizations/me",
        "/permissions",
        "/roles",
        "/memberships",
        "/leads",
        "/leads/options",
        "/leads/assignees",
        "/leads/00000000-0000-0000-0000-000000000001/status-history",
        "/teams",
        "/dashboard",
        "/marketplace/providers",
        "/marketplace/accounts",
    ],
)
def test_grouped_routes_still_require_authentication(app, path):
    response = TestClient(app).get(f"/api/v1{path}")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path,body",
    [
        ("/organizations/me", {"name": "Test", "timezone": "Asia/Kolkata"}),
        ("/roles", {"name": "Sales"}),
        ("/invitations", {"email": "invite@example.com", "display_name": "Invite"}),
        ("/leads", {"name": "Lead"}),
        (
            "/leads/00000000-0000-0000-0000-000000000001/status",
            {
                "status_id": "00000000-0000-0000-0000-000000000002",
                "note": "Qualified the lead",
                "row_version": 1,
            },
        ),
        ("/teams", {"name": "Team"}),
        ("/marketplace/accounts", {"provider_code": "indiamart", "name": "Account"}),
        ("/auth/logout", None),
    ],
)
def test_grouped_writes_still_require_csrf(app, path, body):
    client = TestClient(app)
    client.cookies.set("crm_session", "test-token")
    method = "put" if path == "/organizations/me" else "post"
    response = client.request(method, f"/api/v1{path}", json=body)
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_required"


def test_disallowed_origin_is_rejected_before_authentication(app):
    client = TestClient(app)
    client.cookies.set("crm_session", "test-token")
    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://untrusted.example",
            "X-CSRF-Token": "csrf-token",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


def test_login_keeps_session_cookies_and_throttling(app):
    service = SimpleNamespace(
        throttle=AsyncMock(),
        login=AsyncMock(return_value=("session-token", "csrf-token")),
    )
    app.state.identity_service = service
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "test-org",
            "email": "user@example.com",
            "password": "long-test-password",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "authenticated", "csrf_token": "csrf-token"}
    assert client.cookies["crm_session"] == "session-token"
    assert client.cookies["crm_csrf"] == "csrf-token"
    cookies = response.headers.get_list("set-cookie")
    assert "HttpOnly" in cookies[0]
    assert "HttpOnly" not in cookies[1]
    assert all("SameSite=strict" in cookie for cookie in cookies)
    assert service.throttle.await_count == 2
    service.login.assert_awaited_once()


def test_current_identity_uses_the_shared_principal_dependency(app, monkeypatch):
    from app.modules.identity import authentication

    @asynccontextmanager
    async def transaction(*args):
        yield SimpleNamespace(scalar=AsyncMock(return_value="/leads"))

    monkeypatch.setattr(authentication, "tenant_transaction", transaction)
    app.state.database_engine = object()
    user = Principal(
        uuid4(), uuid4(), uuid4(), uuid4(), False, frozenset({"leads.view"}), "own"
    )
    app.dependency_overrides[principal] = lambda: user
    response = TestClient(app).get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["membership_id"] == str(user.member_id)
    assert response.json()["permissions"] == ["leads.view"]
    assert response.json()["data_scope"] == "own"
    assert response.json()["landing_page"] == "/leads"


@pytest.mark.parametrize(
    "path,module", [("/leads/assignees", "routes"), ("/teams", "teams")]
)
def test_lead_assignment_search_is_bounded_and_parameterized(
    app, monkeypatch, path, module
):
    from importlib import import_module

    endpoint = import_module(f"app.modules.leads.{module}")
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
    connection = SimpleNamespace(
        execute=AsyncMock(return_value=result), scalar=AsyncMock(return_value=0)
    )
    user = Principal(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        False,
        frozenset({"leads.view", "leads.assign"}),
        "own",
    )

    @asynccontextmanager
    async def transaction(*args):
        yield connection, user

    monkeypatch.setattr(endpoint, "access", transaction)
    app.dependency_overrides[principal] = lambda: user
    client = TestClient(app)
    response = client.get(f"/api/v1{path}", params={"q": "  O'Brien%  ", "limit": 25})
    assert response.status_code == 200
    statement, parameters = connection.execute.await_args.args
    assert "strpos(lower(" in str(statement)
    assert "O'Brien" not in str(statement)
    assert parameters["q"] == "O'Brien%"
    assert parameters["org"] == user.org_id
    assert parameters["limit"] == 26
    assert client.get(f"/api/v1{path}", params={"q": "x" * 201}).status_code == 422
    assert client.get(f"/api/v1{path}", params={"limit": 101}).status_code == 422


def test_shared_lead_queries_preserve_scope_and_pii_redaction():
    user = Principal(
        uuid4(), uuid4(), uuid4(), uuid4(), False, frozenset({"leads.view"}), "own"
    )
    assert (
        "l.assigned_membership_id=:member OR l.assigned_membership_id IS NULL"
        in visibility(user)
    )
    assert "NULL::text AS phone" in fields(user)
    assert "true AS pii_redacted" in fields(user)
    team_user = Principal(
        user.org_id,
        user.member_id,
        user.session_id,
        user.user_id,
        False,
        user.permissions,
        "team",
    )
    assert "crm.team_memberships" in visibility(team_user)
    owner = Principal(
        user.org_id,
        user.member_id,
        user.session_id,
        user.user_id,
        True,
        frozenset({"leads.pii.view"}),
        "all",
    )
    assert visibility(owner) == "TRUE"
    assert "l.phone,l.email" in fields(owner)
    assert "false AS pii_redacted" in fields(owner)


def test_organization_schema_remains_strict():
    from pydantic import ValidationError

    assert (
        OrganizationInput(name="Test", timezone="Asia/Kolkata").timezone
        == "Asia/Kolkata"
    )
    with pytest.raises(ValidationError):
        OrganizationInput(name="Test", timezone="invalid/timezone")
    with pytest.raises(ValidationError):
        OrganizationInput.model_validate(
            {"name": "Test", "timezone": "Asia/Kolkata", "unexpected": True}
        )
