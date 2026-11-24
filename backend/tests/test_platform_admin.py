import asyncio
import itertools
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

PLATFORM_PASSWORD = "platform-integration-password"
OWNER_ADDRESSES = itertools.count(100)


@pytest.fixture
def owner():
    runtime = os.environ.get("TEST_RUNTIME_DATABASE_URL")
    identity = os.environ.get("TEST_AUTH_DATABASE_URL")
    if not runtime or not identity:
        pytest.skip("Requires the disposable PostgreSQL test runner")
    app = create_app(
        Settings(database_url=runtime, auth_database_url=identity, app_environment="test")
    )
    options = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    with TestClient(
        app,
        backend_options=options,
        client=(f"198.18.1.{next(OWNER_ADDRESSES)}", 50000),
    ) as client:
        response = client.post(
            "/api/v1/organizations/onboard",
            json={
                "organization_slug": f"platform-{uuid4()}",
                "organization_name": "Platform test",
                "full_name": "Platform owner",
                "email": f"{uuid4()}@example.com",
                "password": f"test-password-{uuid4()}",
            },
        )
        assert response.status_code == 201, response.text
        client.headers["X-CSRF-Token"] = client.cookies["crm_csrf"]
        yield client


def provision_test_operator(client, access_level="administrator"):
    identity = client.get("/api/v1/auth/me").json()
    profile = client.get("/api/v1/auth/profile").json()
    dsn = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "UPDATE crm.app_users SET password_hash=%s,password_change_required=false WHERE id=%s",
            (PasswordHasher().hash(PLATFORM_PASSWORD), identity["user_id"]),
        )
        connection.execute(
            "INSERT INTO crm.platform_operators(user_id,access_level) VALUES(%s,%s) "
            "ON CONFLICT(user_id) DO UPDATE SET access_level=EXCLUDED.access_level",
            (identity["user_id"], access_level),
        )
    return identity, profile


def login_platform(client, email):
    response = client.post(
        "/api/v1/platform/login",
        json={"email": email, "password": PLATFORM_PASSWORD},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf
    return csrf


def test_platform_operator_manages_subscription_users_and_passwords(owner):
    identity, profile = provision_test_operator(owner)
    organization = owner.get("/api/v1/organizations/me").json()
    assert owner.get("/api/v1/platform/organizations").status_code == 401
    platform_csrf = login_platform(owner, profile["email"])

    page = owner.get("/api/v1/platform/organizations").json()
    assert any(row["id"] == identity["organization_id"] for row in page["data"])
    members = owner.get(
        f"/api/v1/platform/organizations/{identity['organization_id']}/users"
    ).json()["data"]
    member = next(row for row in members if row["id"] == identity["membership_id"])

    wrong_confirmation = owner.post(
        f"/api/v1/platform/organizations/{identity['organization_id']}/users/{member['id']}/generate-password",
        json={"confirm_email": "wrong@example.com"},
    )
    assert wrong_confirmation.status_code == 422
    assert wrong_confirmation.json()["code"] == "confirmation_email_mismatch"

    generated = owner.post(
        f"/api/v1/platform/organizations/{identity['organization_id']}/users/{member['id']}/generate-password",
        json={"confirm_email": profile["email"]},
    )
    assert generated.status_code == 200, generated.text
    temporary_password = generated.json()["temporary_password"]
    assert generated.json()["password_change_required"] is True
    assert owner.get("/api/v1/auth/me").status_code == 401

    customer_login = owner.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": organization["slug"],
            "email": profile["email"],
            "password": temporary_password,
        },
    )
    assert customer_login.status_code == 200, customer_login.text
    customer_csrf = customer_login.json()["csrf_token"]
    owner.headers["X-CSRF-Token"] = customer_csrf
    assert owner.get("/api/v1/auth/me").json()["password_change_required"] is True
    forced = owner.get("/api/v1/leads")
    assert forced.status_code == 403
    assert forced.json()["code"] == "password_change_required"
    change = owner.post(
        "/api/v1/auth/password",
        json={
            "current_password": temporary_password,
            "new_password": "replacement-account-password",
        },
    )
    assert change.status_code == 204, change.text
    assert owner.get("/api/v1/auth/me").json()["password_change_required"] is False

    owner.headers["X-CSRF-Token"] = platform_csrf
    active_plan = owner.put(
        f"/api/v1/platform/organizations/{identity['organization_id']}",
        json={
            "status": "active",
            "subscription_plan": "growth",
            "subscription_status": "active",
            "subscription_started_at": None,
            "subscription_ends_at": None,
            "export_access_until": None,
            "max_users": 1,
        },
    )
    assert active_plan.status_code == 200, active_plan.text
    owner.headers["X-CSRF-Token"] = customer_csrf
    over_limit = owner.post(
        "/api/v1/invitations",
        json={"email": "over-limit@example.com", "display_name": "Over limit"},
    )
    assert over_limit.status_code == 409
    assert over_limit.json()["code"] == "user_limit_reached"
    intake_key = owner.post("/api/v1/intake/keys", json={"name": "Website"}).json()

    owner.headers["X-CSRF-Token"] = platform_csrf
    export_until = datetime.now(timezone.utc) + timedelta(days=5)
    ended = owner.put(
        f"/api/v1/platform/organizations/{identity['organization_id']}",
        json={
            "status": "active",
            "subscription_plan": "growth",
            "subscription_status": "expired",
            "subscription_started_at": None,
            "subscription_ends_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "export_access_until": export_until.isoformat(),
            "max_users": 20,
        },
    )
    assert ended.status_code == 200, ended.text

    renewed = owner.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": organization["slug"],
            "email": profile["email"],
            "password": "replacement-account-password",
        },
    )
    assert renewed.status_code == 200, renewed.text
    customer_csrf = renewed.json()["csrf_token"]
    owner.headers["X-CSRF-Token"] = customer_csrf
    assert owner.get("/api/v1/auth/me").json()["access_mode"] == "export_only"
    assert owner.get("/api/v1/leads/export").status_code == 200
    intake = owner.post(
        "/api/v1/intake/leads",
        headers={
            "Authorization": f"Bearer {intake_key['token']}",
            "Idempotency-Key": "subscription-ended-001",
        },
        json={"name": "Should not be accepted"},
    )
    assert intake.status_code == 403
    assert intake.json()["code"] == "export_only_access"
    blocked_write = owner.post("/api/v1/leads", json={"name": "blocked"})
    assert blocked_write.status_code == 403
    assert blocked_write.json()["code"] == "export_only_access"

    owner.headers["X-CSRF-Token"] = platform_csrf
    suspended = owner.put(
        f"/api/v1/platform/organizations/{identity['organization_id']}",
        json={
            "status": "suspended",
            "subscription_plan": "growth",
            "subscription_status": "expired",
            "subscription_started_at": None,
            "subscription_ends_at": None,
            "export_access_until": export_until.isoformat(),
            "max_users": 20,
        },
    )
    assert suspended.status_code == 200, suspended.text
    owner.headers["X-CSRF-Token"] = customer_csrf
    assert owner.get("/api/v1/auth/me").status_code == 401
    owner.headers["X-CSRF-Token"] = platform_csrf
    audit = owner.get("/api/v1/platform/audit").json()["data"]
    assert any(row["action"] == "user.password_generated" for row in audit)


def test_support_operator_cannot_change_organization(owner):
    identity, profile = provision_test_operator(owner, "support")
    login_platform(owner, profile["email"])
    response = owner.put(
        f"/api/v1/platform/organizations/{identity['organization_id']}",
        json={
            "status": "suspended",
            "subscription_plan": "legacy",
            "subscription_status": "active",
            "subscription_started_at": None,
            "subscription_ends_at": None,
            "export_access_until": None,
            "max_users": 100,
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "platform_administrator_required"