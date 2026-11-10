import pytest
import asyncio
import itertools
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4
from fastapi.testclient import TestClient

from app.modules.identity.service import AccessError
from app.core.settings import Settings
from app.main import create_app
from app.modules.marketplace.catalog import PROVIDERS, provider, validate_configuration


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+919876543210", "9876543210"),
        ("+91-9876543210", "9876543210"),
        ("+91 98765 43210", "9876543210"),
        ("00919876543210", "9876543210"),
        ("919876543210", "9876543210"),
        ("9876543210", "9876543210"),
        ("98765-43210", "9876543210"),
        ("", ""),
        ("+1-202-555-0123", "+1-202-555-0123"),
        ("+91-9876543210 ext 12", "+91-9876543210 ext 12"),
        ("12345", "12345"),
    ],
)
def test_phone_normalization_for_imports_manual_entry_and_existing_leads(raw, expected):
    from app.core.phone import normalize_phone
    from app.modules.leads.queries import lead_payload
    from app.modules.leads.schemas import LeadInput

    assert normalize_phone(raw) == expected
    assert normalize_phone(expected) == expected
    assert LeadInput(name="Example", phone=raw).phone == expected
    assert lead_payload({"phone": raw})["phone"] == expected
    assert lead_payload({"phone": None, "pii_redacted": True})["phone"] is None


def test_indiamart_parser_preserves_source_identity_and_time():
    from app.modules.marketplace.indiamart import normalize_response

    payload = {
        "CODE": 200,
        "STATUS": "SUCCESS",
        "TOTAL_RECORDS": 1,
        "RESPONSE": [
            {
                "UNIQUE_QUERY_ID": "12345",
                "QUERY_TIME": "2026-11-06 10:30:00",
                "SENDER_NAME": "Test enquiry",
                "SENDER_MOBILE": "+91-9876543210",
                "QUERY_MESSAGE": "Request a quote",
            }
        ],
    }
    lead = normalize_response(payload)[0]
    assert lead["source_record_id"] == "12345"
    assert lead["phone"] == "9876543210"
    assert lead["source_time"] == "2026-11-06T10:30:00+05:30"
    assert lead["enquiry"] == "Request a quote"
    assert (
        normalize_response(
            {"CODE": 200, "STATUS": "SUCCESS", "TOTAL_RECORDS": 0, "RESPONSE": []}
        )
        == []
    )
    assert (
        normalize_response(
            {"CODE": 204, "STATUS": "SUCCESS", "TOTAL_RECORDS": 0, "RESPONSE": []}
        )
        == []
    )


@pytest.mark.asyncio
async def test_indiamart_request_uses_only_key_and_time_window():
    import httpx
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.indiamart import fetch_leads

    def respond(request):
        assert set(request.url.params) == {"glusr_crm_key", "start_time", "end_time"}
        assert request.url.params["glusr_crm_key"] == "fixture-api-key"
        assert request.url.params["start_time"] == "07-Nov-202610:30:00"
        return httpx.Response(
            200,
            json={"CODE": 204, "STATUS": "SUCCESS", "TOTAL_RECORDS": 0, "RESPONSE": []},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        start = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc)
        assert (
            await fetch_leads(
                client, "fixture-api-key", start, start + timedelta(minutes=5)
            )
            == []
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"CODE": 401, "STATUS": "FAILURE", "MESSAGE": "secret provider response"},
        {"CODE": 200, "STATUS": "SUCCESS", "TOTAL_RECORDS": 2, "RESPONSE": []},
        {"CODE": 200, "STATUS": "SUCCESS", "TOTAL_RECORDS": 1, "RESPONSE": [{}]},
    ],
)
def test_indiamart_parser_fails_closed_without_returning_provider_messages(payload):
    from app.modules.marketplace.indiamart import normalize_response

    with pytest.raises(AccessError) as failure:
        normalize_response(payload)
    assert "secret" not in failure.value.code


def test_tradeindia_parser_maps_inquiry_and_strips_html():
    from app.modules.marketplace.tradeindia import normalize_response

    payload = [
        {
            "rfi_id": 9001,
            "sender_name": "Asha",
            "sender_co": "Acme Traders  ",
            "sender_mobile": "9876543210",
            "sender_city": "Pune",
            "sender_state": "Maharashtra",
            "product_name": "Steel pipes",
            "subject": "Quote",
            "message": 'Call <a href="tel:9876543210">9876543210</a> &amp; quote',
            "generated": 1762410600,
            "att_data": [],
        }
    ]
    lead = normalize_response(payload)[0]
    assert lead["source_record_id"] == "9001"
    assert lead["company"] == "Acme Traders"
    assert lead["enquiry"] == "Call 9876543210 & quote"
    assert lead["source_time"] == "2025-11-06T06:30:00+00:00"
    assert normalize_response([]) == []


@pytest.mark.asyncio
async def test_tradeindia_pages_until_short_page_and_sends_only_documented_params():
    import httpx
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.tradeindia import PAGE_SIZE, fetch_leads

    seen = []

    def respond(request):
        params = dict(request.url.params)
        seen.append(params)
        assert set(params) == {
            "userid",
            "profile_id",
            "key",
            "from_date",
            "to_date",
            "limit",
            "page_no",
        }
        assert params["from_date"] == params["to_date"] == "2026-11-07"
        count = PAGE_SIZE if params["page_no"] == "1" else 3
        return httpx.Response(
            200,
            json=[
                {"rfi_id": f"{params['page_no']}-{i}", "generated": 1762410600}
                for i in range(count)
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        start = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc)
        leads = await fetch_leads(
            client,
            {"user_id": "1", "profile_id": "2"},
            "fixture-api-key",
            start,
            start + timedelta(minutes=5),
        )
    assert len(leads) == PAGE_SIZE + 3
    assert [item["page_no"] for item in seen] == ["1", "2"]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
@pytest.mark.asyncio
async def test_tradeindia_http_failures_fail_closed(status):
    import httpx
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.tradeindia import fetch_leads

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="fixture-api-key rejected")
        )
    ) as client:
        start = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc)
        with pytest.raises(AccessError) as failure:
            await fetch_leads(
                client,
                {"user_id": "1", "profile_id": "2"},
                "fixture-api-key",
                start,
                start + timedelta(minutes=5),
            )
    assert "fixture" not in failure.value.code


@pytest.mark.asyncio
async def test_tradeindia_rate_limit_403_is_not_a_rejected_key():
    import httpx
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.tradeindia import fetch_leads

    body = {
        "status": "error",
        "message": "Rate limit exceed. Try After 15 minutes : A maximum of 5 requests is allowed every 5 minutes.",
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403, json=body))
    ) as client:
        start = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc)
        with pytest.raises(AccessError) as failure:
            await fetch_leads(
                client,
                {"user_id": "1", "profile_id": "2"},
                "fixture-api-key",
                start,
                start + timedelta(minutes=5),
            )
    assert failure.value.code == "provider_rate_limited"


def test_encryption_is_bound_to_account_and_version(tmp_path):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import serialization
    from app.core.settings import Settings
    from app.modules.marketplace.crypto import (
        generate_keys,
        encrypt_credentials,
        decrypt_credentials,
    )

    generate_keys(tmp_path)
    settings = Settings(
        database_url="postgresql+psycopg://crm_api@localhost/test",
        app_environment="test",
        marketplace_public_key_file=tmp_path / "marketplace-public.pem",
    )
    private = serialization.load_pem_private_key(
        (tmp_path / "marketplace-private.pem").read_bytes(), password=None
    )
    envelope = encrypt_credentials(
        settings, {"crm_key": "never-return-this"}, "org", "account", 1
    )
    assert "never-return-this" not in str(envelope)
    assert decrypt_credentials(private, envelope, "org", "account", 1) == {
        "crm_key": "never-return-this"
    }
    with pytest.raises(InvalidTag):
        decrypt_credentials(private, envelope, "org", "other-account", 1)
    with pytest.raises(InvalidTag):
        decrypt_credentials(private, envelope, "org", "account", 2)


def test_account_input_masks_secrets_and_rejects_extra_fields():
    from pydantic import ValidationError
    from app.modules.marketplace.routes import AccountInput

    body = AccountInput(
        provider_code="indiamart",
        name="Sales",
        config={"mobile": "123"},
        credentials={"crm_key": "not-in-repr"},
    )
    assert "not-in-repr" not in repr(body)
    assert "not-in-repr" not in body.model_dump_json()
    with pytest.raises(ValidationError):
        AccountInput(provider_code="indiamart", name=" ", org_id="untrusted")


def test_unconfigured_or_production_keys_fail_closed(tmp_path):
    from app.modules.marketplace.crypto import load_public_key

    configuration = Settings(
        database_url="postgresql+psycopg://crm_api@localhost/test",
        app_environment="test",
        marketplace_public_key_file=tmp_path / "missing.pem",
    )
    with pytest.raises(AccessError) as error:
        load_public_key(configuration)
    assert error.value.code == "marketplace_key_unavailable"
    with pytest.raises(AccessError) as error:
        load_public_key(
            configuration.model_copy(update={"app_environment": "production"})
        )
    assert error.value.code == "marketplace_managed_keys_required"


def test_marketplace_catalog_is_unique_and_capability_gated():
    assert [value["key"] for value in provider("indiamart")["fields"]] == ["crm_key"]
    assert len({item["code"] for item in PROVIDERS}) == len(PROVIDERS) == 12
    assert [item["code"] for item in PROVIDERS if item["adapter"]] == [
        "indiamart",
        "tradeindia",
    ]
    assert provider("tradeindia")["multiple_accounts"] is None
    assert not provider("shopify")["setup"]


def test_credentials_are_provider_specific():
    validate_configuration("indiamart", {}, {"crm_key": "test-secret"})
    validate_configuration(
        "indiamart", {"mobile": "9876543210"}, {"crm_key": "test-secret"}
    )
    validate_configuration(
        "tradeindia", {"user_id": "1", "profile_id": "2"}, {"api_key": "test-secret"}
    )
    with pytest.raises(AccessError):
        validate_configuration(
            "tradeindia", {"mobile": "9876543210"}, {"crm_key": "test-secret"}
        )
    with pytest.raises(AccessError):
        validate_configuration("facebook", {}, {"api_key": "test-secret"})
    with pytest.raises(AccessError):
        validate_configuration("indiamart", {"mobile": "9876543210"}, {})


def test_credential_rotation_can_preserve_but_not_partially_replace_secrets():
    validate_configuration("indiamart", {}, {}, replacing=True)
    validate_configuration("indiamart", {"mobile": "9876543210"}, {}, replacing=True)
    with pytest.raises(AccessError):
        validate_configuration(
            "indiamart", {"mobile": "9876543210"}, {"crm_key": ""}, replacing=True
        )


# Onboarding is rate limited per client address, so each owner fixture gets its own.
OWNER_ADDRESSES = itertools.count(20)


@pytest.fixture
def marketplace_owner():
    runtime, identity = os.environ.get("TEST_RUNTIME_DATABASE_URL"), os.environ.get(
        "TEST_AUTH_DATABASE_URL"
    )
    if not runtime or not identity:
        pytest.skip("Requires the disposable PostgreSQL test runner")
    options = (
        {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    )
    with TestClient(
        create_app(
            Settings(
                database_url=runtime, auth_database_url=identity, app_environment="test"
            )
        ),
        backend_options=options,
        client=(f"198.51.100.{next(OWNER_ADDRESSES)}", 50000),
    ) as client:
        response = client.post(
            "/api/v1/organizations/onboard",
            json={
                "organization_slug": f"marketplace-{uuid4()}",
                "organization_name": "Marketplace test",
                "full_name": "Owner",
                "email": f"{uuid4()}@example.com",
                "password": f"test-password-{uuid4()}",
            },
        )
        assert response.status_code == 201, response.text
        client.headers["X-CSRF-Token"] = client.cookies["crm_csrf"]
        yield client


def add_account(client, name, key, code="indiamart"):
    response = client.post(
        "/api/v1/marketplace/accounts",
        json={
            "provider_code": code,
            "name": name,
            "config": (
                {} if code == "indiamart" else {"user_id": "1", "profile_id": "2"}
            ),
            "credentials": {"crm_key" if code == "indiamart" else "api_key": key},
        },
    )
    assert response.status_code == 201, response.text
    assert key not in response.text
    assert "credential_envelope" not in response.json()
    return response.json()


def test_database_accounts_rotation_cardinality_and_tenant_isolation(marketplace_owner):
    client = marketplace_owner
    first = add_account(client, "North sales", f"fixture-{uuid4()}")
    second = add_account(client, "South sales", f"fixture-{uuid4()}")
    assert first["id"] != second["id"]
    assert len(client.get("/api/v1/marketplace/accounts").json()["data"]) == 2
    assert (
        client.post(
            f"/api/v1/marketplace/accounts/{first['id']}/activate",
            json={"row_version": 1},
        ).json()["code"]
        == "marketplace_test_required"
    )
    rotated = client.put(
        f"/api/v1/marketplace/accounts/{first['id']}",
        json={
            "provider_code": "indiamart",
            "name": "North sales",
            "config": {"mobile": "9876543210"},
            "credentials": {"crm_key": "rotated-test-key"},
            "row_version": first["row_version"],
        },
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["credential_version"] == 2
    assert "rotated-test-key" not in rotated.text
    assert (
        client.put(
            f"/api/v1/marketplace/accounts/{first['id']}",
            json={
                "provider_code": "indiamart",
                "name": "Stale edit",
                "config": {"mobile": "9876543210"},
                "row_version": 1,
            },
        ).json()["code"]
        == "marketplace_version_conflict"
    )
    duplicate = client.post(
        "/api/v1/marketplace/accounts",
        json={
            "provider_code": "indiamart",
            "name": "Duplicate",
            "config": {"mobile": "9876543210"},
            "credentials": {"crm_key": "rotated-test-key"},
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "marketplace_credentials_in_use"
    trade = add_account(client, "Trade account", "trade-test-key", "tradeindia")
    tested = client.post(
        f"/api/v1/marketplace/accounts/{trade['id']}/test", json={"row_version": 1}
    )
    assert tested.status_code == 200, tested.text
    assert (
        client.post(
            "/api/v1/marketplace/accounts",
            json={
                "provider_code": "tradeindia",
                "name": "Second trade",
                "config": {"user_id": "3", "profile_id": "4"},
                "credentials": {"api_key": "another-trade-key"},
            },
        ).json()["code"]
        == "provider_account_limit_unverified"
    )
    options = (
        {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    )
    with TestClient(
        create_app(client.app.state.configuration),
        backend_options=options,
        client=("198.51.100.12", 50000),
    ) as other:
        assert (
            other.post(
                "/api/v1/organizations/onboard",
                json={
                    "organization_slug": f"other-{uuid4()}",
                    "organization_name": "Other",
                    "full_name": "Other",
                    "email": f"{uuid4()}@example.com",
                    "password": f"password-{uuid4()}",
                },
            ).status_code
            == 201
        )
        other.headers["X-CSRF-Token"] = other.cookies["crm_csrf"]
        assert other.get("/api/v1/marketplace/accounts").json()["data"] == []
        assert (
            other.get(f"/api/v1/marketplace/accounts/{first['id']}/runs").status_code
            == 404
        )
        assert (
            other.post(
                f"/api/v1/marketplace/accounts/{first['id']}/pause",
                json={"row_version": 2},
            ).status_code
            == 404
        )


def test_database_repeated_test_is_idempotent_and_key_is_masked(marketplace_owner):
    client = marketplace_owner
    created = add_account(client, "Masked account", "abcdefghijklmnop-1234")
    assert created["credential_hint"] == {"crm_key": "•" * 8 + "1234"}
    assert "default_assignee_membership_id" not in created
    for _ in range(2):
        response = client.post(
            f"/api/v1/marketplace/accounts/{created['id']}/test",
            json={"row_version": created["row_version"]},
        )
        assert response.status_code == 200, response.text
    runs = client.get(f"/api/v1/marketplace/accounts/{created['id']}/runs").json()[
        "data"
    ]
    assert [run["state"] for run in runs] == ["queued"]
    clash = client.post(
        "/api/v1/marketplace/accounts",
        json={
            "provider_code": "indiamart",
            "name": "masked ACCOUNT",
            "config": {},
            "credentials": {"crm_key": f"fixture-{uuid4()}"},
        },
    )
    assert (
        clash.status_code == 409 and clash.json()["code"] == "marketplace_name_in_use"
    )
    assert (
        client.post(
            "/api/v1/marketplace/accounts",
            json={
                "provider_code": "indiamart",
                "name": "Assigned",
                "config": {},
                "credentials": {"crm_key": f"fixture-{uuid4()}"},
                "default_assignee_membership_id": str(uuid4()),
            },
        ).status_code
        == 422
    )
    providers = client.get("/api/v1/marketplace/providers").json()
    assert providers["worker_online"] in (True, False)


def test_lead_status_custom_fields_round_robin_and_table_preferences(marketplace_owner):
    client = marketplace_owner
    member_id = client.get("/api/v1/auth/me").json()["membership_id"]
    default_assigned = client.post("/api/v1/leads", json={"name": "Creator assigned"})
    assert default_assigned.status_code == 201, default_assigned.text
    assert default_assigned.json()["assigned_membership_id"] == member_id
    unassigned = client.post(
        "/api/v1/leads",
        json={"name": "Explicitly unassigned", "assigned_membership_id": None},
    )
    assert unassigned.status_code == 201, unassigned.text
    assert unassigned.json()["assigned_membership_id"] is None
    field = client.post(
        "/api/v1/lead-custom-fields",
        json={
            "field_key": "budget",
            "label": "Budget",
            "field_type": "number",
            "options": [],
            "position": 0,
            "is_active": True,
        },
    )
    assert field.status_code == 201, field.text
    status = client.post(
        "/api/v1/lead-statuses",
        json={
            "name": "Qualified prospect",
            "category": "working",
            "color": "#147d64",
            "position": 20,
            "is_active": True,
        },
    )
    assert status.status_code == 201, status.text
    status_id = status.json()["id"]
    rules = client.put(
        f"/api/v1/lead-statuses/{status_id}/rules",
        json={
            "tag_on_entry": "qualified",
            "auto_assign": True,
            "member_ids": [member_id],
            "role_ids": [],
            "required_fields": ["budget"],
        },
    )
    assert rules.status_code == 200, rules.text
    missing = client.post(
        "/api/v1/leads", json={"name": "Missing budget", "status_id": status_id}
    )
    assert missing.status_code == 422
    assert missing.json()["code"] == "lead_required_fields_missing"
    invalid = client.post(
        "/api/v1/leads",
        json={
            "name": "Invalid budget",
            "status_id": status_id,
            "custom_fields": {"budget": "large"},
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_custom_field_value"
    created = client.post(
        "/api/v1/leads",
        json={
            "name": "Qualified lead",
            "status_id": status_id,
            "custom_fields": {"budget": 45000},
        },
    )
    assert created.status_code == 201, created.text
    lead = created.json()
    assert lead["assigned_membership_id"] == member_id
    assert "qualified" in lead["tags"]
    assert lead["status_changed_at"]
    assert lead["source_record_id"] is None
    saved = client.put(
        "/api/v1/lead-table-preferences",
        json={"columns": ["name", "status", "source_record_id"]},
    )
    assert saved.status_code == 200
    assert client.get("/api/v1/lead-table-preferences").json()["columns"] == [
        "name",
        "status",
        "source_record_id",
    ]
    separate_columns = [
        "company",
        "email",
        "phone",
        "city",
        "state",
        "address",
        "product",
        "enquiry",
        "status_changed_at",
        "status",
        "source_name",
        "source_provider",
        "source_record_id",
        "received_at",
        "assignee",
        "team_name",
        "tags",
        "next_follow_up_at",
        "updated_at",
        "archived_at",
        "custom:budget",
    ]
    saved = client.put(
        "/api/v1/lead-table-preferences", json={"columns": separate_columns}
    )
    assert saved.status_code == 200, saved.text
    assert (
        client.get("/api/v1/lead-table-preferences").json()["columns"]
        == separate_columns
    )
    assert (
        client.put(
            "/api/v1/lead-table-preferences", json={"columns": ["status"]}
        ).status_code
        == 200
    )
    for invalid_columns in (["status", "status"], ["custom:missing"], ["unknown"]):
        response = client.put(
            "/api/v1/lead-table-preferences", json={"columns": invalid_columns}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_lead_table_columns"
    assert (
        client.put("/api/v1/lead-table-preferences", json={"columns": []}).status_code
        == 422
    )
    statuses = client.get("/api/v1/lead-statuses").json()["data"]
    assert next(item for item in statuses if item["id"] == status_id)[
        "required_fields"
    ] == ["budget"]
    default = next(item for item in statuses if item["is_default"])
    protected = client.put(
        f"/api/v1/lead-statuses/{default['id']}",
        json={
            "name": "Renamed system stage",
            "category": default["type"],
            "color": default["color"],
            "position": default["position"],
            "is_active": True,
        },
    )
    assert protected.status_code == 409
    assert protected.json()["code"] == "system_status_protected"


def test_database_api_role_cannot_read_encrypted_credentials(marketplace_owner):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.core.database import tenant_transaction

    identity = marketplace_owner.get("/api/v1/auth/me").json()

    async def verify():
        with pytest.raises(DBAPIError):
            async with tenant_transaction(
                marketplace_owner.app.state.database_engine,
                UUID(identity["organization_id"]),
            ) as connection:
                await connection.execute(
                    text("SELECT credential_envelope FROM crm.marketplace_accounts")
                )

    marketplace_owner.portal.call(verify)


def test_database_marketplace_view_does_not_grant_management(marketplace_owner):
    owner = marketplace_owner
    account = add_account(owner, "Read-only account", f"reader-fixture-{uuid4()}")
    role = owner.post(
        "/api/v1/roles",
        json={"name": "Marketplace reader", "permissions": ["marketplace.view"]},
    )
    assert role.status_code == 201, role.text
    invite = owner.post(
        "/api/v1/invitations",
        json={
            "email": f"{uuid4()}@example.com",
            "display_name": "Reader",
            "role_ids": [role.json()["id"]],
        },
    )
    assert invite.status_code == 201, invite.text
    options = (
        {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}
    )
    with TestClient(
        create_app(owner.app.state.configuration),
        backend_options=options,
        client=("198.51.100.13", 50000),
    ) as reader:
        response = reader.post(
            "/api/v1/auth/accept-invite",
            json={
                "invitation_token": invite.json()["invitation_token"],
                "password": f"reader-password-{uuid4()}",
            },
        )
        assert response.status_code == 200, response.text
        reader.headers["X-CSRF-Token"] = reader.cookies["crm_csrf"]
        assert reader.get("/api/v1/marketplace/providers").status_code == 200
        assert (
            reader.get("/api/v1/marketplace/accounts").json()["data"][0]["id"]
            == account["id"]
        )
        assert (
            reader.post(
                f"/api/v1/marketplace/accounts/{account['id']}/test",
                json={"row_version": 1},
            ).status_code
            == 403
        )
        assert (
            reader.post(
                "/api/v1/marketplace/accounts",
                json={
                    "provider_code": "indiamart",
                    "name": "Denied",
                    "config": {"mobile": "9876543210"},
                    "credentials": {"crm_key": "denied-test-key"},
                },
            ).status_code
            == 403
        )


def test_database_worker_ingests_idempotently_and_preserves_manual_edits(
    marketplace_owner,
):
    import httpx
    from cryptography.hazmat.primitives import serialization
    from sqlalchemy import text
    from app.core.database import create_database_engine, tenant_transaction
    from app.modules.marketplace.worker import heartbeat, organizations, process_once

    worker_url = os.environ.get("TEST_WORKER_DATABASE_URL")
    if not worker_url:
        pytest.skip("Requires provisioned crm_worker role")
    client = marketplace_owner
    account = add_account(client, "Worker account", "worker-fixture-key")
    identity = client.get("/api/v1/auth/me").json()
    org = UUID(identity["organization_id"])
    private = serialization.load_pem_private_key(
        Path(os.environ["TEST_MARKETPLACE_PRIVATE_KEY_FILE"]).read_bytes(),
        password=None,
    )
    payload = {
        "CODE": 200,
        "STATUS": "SUCCESS",
        "TOTAL_RECORDS": 1,
        "RESPONSE": [
            {
                "UNIQUE_QUERY_ID": "same-source-id",
                "QUERY_TIME": "2026-11-06 10:30:00",
                "SENDER_NAME": "Provider name",
                "SENDER_MOBILE": "9876543210",
            }
        ],
    }

    async def work():
        engine = create_database_engine(
            Settings(database_url=worker_url, app_environment="test")
        )
        try:
            await heartbeat(engine)
            assert org in await organizations(engine)
            async with tenant_transaction(engine, org) as connection:
                await connection.execute(
                    text(
                        "UPDATE crm.marketplace_accounts SET next_allowed_at=now()-interval '1 minute',"
                        "next_live_at=now()-interval '1 minute' WHERE org_id=:org"
                    ),
                    {"org": org},
                )
                await connection.execute(
                    text(
                        "UPDATE crm.marketplace_rate_limits SET next_allowed_at=now()-interval '1 minute'"
                    )
                )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=payload)
                )
            ) as transport:
                return await process_once(engine, org, private, transport)
        finally:
            await engine.dispose()

    assert (
        client.post(
            f"/api/v1/marketplace/accounts/{account['id']}/test",
            json={"row_version": 1},
        ).status_code
        == 200
    )
    assert client.portal.call(work)
    assert client.get("/api/v1/marketplace/providers").json()["worker_online"] is True
    assert client.get("/api/v1/leads").json()["data"] == []
    account = client.get("/api/v1/marketplace/accounts").json()["data"][0]
    activated = client.post(
        f"/api/v1/marketplace/accounts/{account['id']}/activate",
        json={"row_version": account["row_version"]},
    )
    assert activated.status_code == 200, activated.text
    assert client.portal.call(work)
    leads = client.get("/api/v1/leads").json()["data"]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["integration_id"] == account["id"]
    assert lead["source_account_name"] == "Worker account"
    assert (
        client.put(
            f"/api/v1/leads/{lead['id']}",
            json={
                "name": "Manual name",
                "source_provider": "indiamart",
                "row_version": lead["row_version"],
            },
        ).status_code
        == 200
    )
    assert client.portal.call(work)
    leads = client.get("/api/v1/leads").json()["data"]
    assert len(leads) == 1
    assert leads[0]["name"] == "Manual name"
    latest = client.get(f"/api/v1/marketplace/accounts/{account['id']}/runs").json()[
        "data"
    ][0]
    assert latest["state"] == "completed" and latest["accepted_count"] == 0
    assert (
        client.post("/api/v1/leads", json={"name": "Unrelated manual lead"}).status_code
        == 201
    )
    filtered = client.get(f"/api/v1/leads?integration_id={account['id']}").json()[
        "data"
    ]
    assert len(filtered) == 1 and filtered[0]["id"] == lead["id"]
    assert client.get(f"/api/v1/leads?integration_id={uuid4()}").json()["data"] == []


def test_indiamart_204_variants_and_documented_errors():
    from datetime import datetime, timezone
    from app.modules.marketplace.indiamart import HistoryNotReady, normalize_response

    assert (
        normalize_response(
            {
                "CODE": 204,
                "STATUS": "FAILURE",
                "MESSAGE": "There are no leads in the given time duration.",
                "TOTAL_RECORDS": 0,
                "RESPONSE": [],
            }
        )
        == []
    )
    with pytest.raises(HistoryNotReady) as pending:
        normalize_response(
            {
                "CODE": 204,
                "STATUS": "FAILURE",
                "MESSAGE": "Leads before 25-02-2022 12:57:54 will be available after 24 hours from the Pull API Key generation time.",
            }
        )
    assert pending.value.code == "provider_history_not_ready"
    assert pending.value.until == datetime(2022, 2, 26, 7, 27, 54, tzinfo=timezone.utc)
    for payload, code in [
        (
            {
                "CODE": 400,
                "STATUS": "FAILURE",
                "MESSAGE": "You can fetch the data for the last 365 days only.",
            },
            "provider_history_expired",
        ),
        (
            {"CODE": 500, "STATUS": "FAILURE", "MESSAGE": "Some Error Occured"},
            "provider_unavailable",
        ),
        (
            {"CODE": 429, "STATUS": "FAILURE", "MESSAGE": "Too Many Requests"},
            "provider_rate_limited",
        ),
        (
            {"CODE": 400, "STATUS": "FAILURE", "MESSAGE": "Please enter both dates"},
            "provider_response_rejected",
        ),
    ]:
        with pytest.raises(AccessError) as failure:
            normalize_response(payload)
        assert failure.value.code == code
    with pytest.raises(AccessError) as failure:
        normalize_response(
            {
                "CODE": 200,
                "STATUS": "SUCCESS",
                "TOTAL_RECORDS": 10001,
                "RESPONSE": [{}] * 10001,
            }
        )
    assert failure.value.code == "provider_payload_too_large"


def test_history_windows_cover_range_newest_first_within_provider_limits():
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.schedule import (
        IST,
        history_floor,
        plan_windows,
        split_window,
    )

    now = datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc)
    windows = plan_windows("indiamart", history_floor("indiamart", now), now)
    assert len(windows) == 53
    assert windows[0][1] == now and windows[-1][0] == history_floor("indiamart", now)
    assert all(end - start <= timedelta(days=7) for start, end in windows)
    assert all(windows[i][0] == windows[i + 1][1] for i in range(len(windows) - 1))
    trade = plan_windows("tradeindia", history_floor("tradeindia", now), now)
    assert len(trade) == 365
    for start, end in trade:
        assert (
            start.astimezone(IST).time()
            == end.astimezone(IST).time()
            == datetime.min.time()
        )
        assert end - start == timedelta(days=1)
    assert trade[-1][0] >= history_floor("tradeindia", now)
    halves = split_window("indiamart", *windows[0])
    assert halves and halves[0][1] == windows[0][1] and halves[1][0] == windows[0][0]
    assert halves[0][0] == halves[1][1]
    assert split_window("indiamart", now - timedelta(minutes=90), now) is None
    day_halves = split_window("tradeindia", trade[3][0], trade[0][1])
    assert day_halves and day_halves[0][0] == trade[1][0]
    assert split_window("tradeindia", *trade[0]) is None


def test_live_window_hands_long_gaps_to_history_and_never_crosses_midnight_for_tradeindia():
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.schedule import ist_midnight, live_window

    now = datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc)
    recent = now - timedelta(minutes=15)
    assert live_window("indiamart", recent, now) == (
        recent - timedelta(minutes=5),
        now,
        None,
    )
    old = now - timedelta(days=20)
    start, end, gap = live_window("indiamart", old, now)
    assert (start, end) == (now - timedelta(days=7), now)
    assert gap == (
        old - timedelta(minutes=5),
        now - timedelta(days=7) + timedelta(minutes=5),
    )
    today = ist_midnight(datetime(2026, 11, 8).date())
    assert live_window("tradeindia", recent, now) == (today, now, None)
    yesterday_tail = today - timedelta(minutes=3)
    assert live_window("tradeindia", yesterday_tail, now) == (
        today - timedelta(days=1),
        today,
        None,
    )
    assert live_window("tradeindia", today, now) == (today, now, None)
    start, end, gap = live_window("tradeindia", old, now)
    assert (start, end) == (today, now) and gap == (
        ist_midnight(datetime(2026, 10, 19).date()),
        today,
    )


@pytest.mark.parametrize(
    "interval,slots", [(300, 0), (600, 1), (900, 2), (1200, 3), (1800, 5), (3600, 10)]
)
def test_import_slots_fit_between_live_syncs(interval, slots):
    from app.modules.marketplace.schedule import backfill_slots_per_cycle

    assert backfill_slots_per_cycle("indiamart", interval) == slots


def test_schedule_status_explains_every_hold():
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.schedule import history_status, live_status

    now = datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc)
    base = {
        "provider_code": "indiamart",
        "status": "active",
        "next_allowed_at": now - timedelta(minutes=1),
        "next_live_at": now + timedelta(minutes=10),
        "hold_reason": None,
        "hold_until": None,
        "last_request_at": now - timedelta(minutes=5),
        "last_run_state": "completed",
        "sync_interval_seconds": 900,
        "verified_version": 1,
        "credential_version": 1,
    }
    assert live_status(base, None, True, now)["state"] == "scheduled"
    assert live_status(base, None, False, now)["reason"] == "worker_offline"
    held = {
        **base,
        "hold_reason": "provider_cooldown",
        "hold_until": now + timedelta(minutes=15),
    }
    assert live_status(held, None, True, now)["reason"] == "provider_cooldown"
    due = {**base, "next_live_at": now, "next_allowed_at": now + timedelta(minutes=3)}
    assert live_status(due, None, True, now)["reason"] == "waiting_key_slot"
    assert (
        live_status(base, now + timedelta(minutes=4), True, now)["reason"]
        == "shared_key_slot"
    )
    paused = {**base, "status": "paused", "last_request_at": now - timedelta(days=6)}
    expiry = live_status(paused, None, True, now)
    assert expiry["reason"] == "key_expiry_risk"
    assert expiry["until"] == now + timedelta(days=1)
    backfill = {
        "id": uuid4(),
        "kind": "import",
        "state": "active",
        "range_start": now - timedelta(days=365),
        "range_end": now,
        "hold_reason": "history_not_ready",
        "hold_until": now + timedelta(hours=20),
        "fetched_count": 0,
        "accepted_count": 0,
        "created_at": now,
        "finished_at": None,
        "windows_total": 53,
        "windows_done": 0,
        "windows_failed": 0,
        "windows_pending": 53,
        "windows_running": 0,
    }
    history = history_status(base, backfill, True, now)
    assert (
        history["reason"] == "history_not_ready" and history["eta"] > history["until"]
    )
    assert (
        history_status({**base, "sync_interval_seconds": 300}, backfill, True, now)[
            "reason"
        ]
        == "import_paused_interval_5min"
    )
    assert (
        history_status({**base, "status": "paused"}, backfill, True, now)["reason"]
        == "import_paused_account_paused"
    )
    assert (
        history_status({**base, "verified_version": None}, backfill, True, now)[
            "reason"
        ]
        == "import_paused_needs_test"
    )
    gap = {**backfill, "kind": "gap", "hold_reason": None, "hold_until": None}
    assert history_status(base, gap, True, now)["reason"] == "gap_recovery"


@pytest.mark.asyncio
async def test_tradeindia_history_window_continues_on_next_slot():
    import httpx
    from datetime import datetime, timedelta, timezone
    from app.modules.marketplace.tradeindia import MAX_PAGES, PAGE_SIZE, fetch_pages

    pages = []

    def respond(request):
        page = int(request.url.params["page_no"])
        pages.append(page)
        assert request.url.params["from_date"] == "2026-11-01"
        assert request.url.params["to_date"] == "2026-11-01"
        count = PAGE_SIZE if page <= MAX_PAGES + 1 else 4
        return httpx.Response(
            200,
            json=[
                {"rfi_id": f"{page}-{i}", "generated": 1762410600} for i in range(count)
            ],
        )

    start = datetime(2026, 10, 31, 18, 30, tzinfo=timezone.utc)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        leads, more = await fetch_pages(
            client,
            {"user_id": "1", "profile_id": "2"},
            "key",
            start,
            start + timedelta(days=1),
        )
        assert len(leads) == PAGE_SIZE * MAX_PAGES and more == MAX_PAGES + 1
        leads, more = await fetch_pages(
            client,
            {"user_id": "1", "profile_id": "2"},
            "key",
            start,
            start + timedelta(days=1),
            more,
        )
    assert more is None and len(leads) == PAGE_SIZE + 4
    assert pages == list(range(1, MAX_PAGES + 3))
    with pytest.raises(AccessError) as failure:
        await fetch_pages(
            None,
            {"user_id": "1", "profile_id": "2"},
            "key",
            start,
            start + timedelta(days=2),
        )
    assert failure.value.code == "provider_window_invalid"


def run_worker(client, org: UUID, respond, prepare: str | None = None) -> bool:
    import httpx
    from cryptography.hazmat.primitives import serialization
    from sqlalchemy import text
    from app.core.database import create_database_engine, tenant_transaction
    from app.modules.marketplace.worker import heartbeat, process_once

    private = serialization.load_pem_private_key(
        Path(os.environ["TEST_MARKETPLACE_PRIVATE_KEY_FILE"]).read_bytes(),
        password=None,
    )

    async def work():
        engine = create_database_engine(
            Settings(
                database_url=os.environ["TEST_WORKER_DATABASE_URL"],
                app_environment="test",
            )
        )
        try:
            await heartbeat(engine)
            async with tenant_transaction(engine, org) as connection:
                if prepare:
                    await connection.execute(text(prepare), {"org": org})
                await connection.execute(
                    text(
                        "UPDATE crm.marketplace_rate_limits SET next_allowed_at=now()-interval '1 minute'"
                    )
                )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(respond)
            ) as transport:
                return await process_once(engine, org, private, transport)
        finally:
            await engine.dispose()

    return client.portal.call(work)


def test_database_history_import_uses_free_slots_and_keeps_enquiry_time(
    marketplace_owner,
):
    import httpx
    from datetime import datetime, timezone

    if not os.environ.get("TEST_WORKER_DATABASE_URL"):
        pytest.skip("Requires provisioned crm_worker role")
    client = marketplace_owner
    org = UUID(client.get("/api/v1/auth/me").json()["organization_id"])
    created = client.post(
        "/api/v1/marketplace/accounts",
        json={
            "provider_code": "indiamart",
            "name": "History account",
            "config": {},
            "credentials": {"crm_key": f"history-{uuid4()}"},
            "sync_interval_seconds": 1200,
            "import_history": True,
        },
    )
    assert created.status_code == 201, created.text
    account = created.json()
    assert account["sync_interval_seconds"] == 1200
    history = account["schedule_status"]["history"]
    assert history["state"] == "active" and history["windows_total"] == 53
    assert history["reason"] in ("import_paused_needs_test", "worker_offline")
    path = f"/api/v1/marketplace/accounts/{account['id']}"
    assert (
        client.post(f"{path}/backfills", json={}).json()["code"]
        == "marketplace_backfill_active"
    )
    assert (
        client.put(f"{path}/schedule", json={"sync_interval_seconds": 120}).status_code
        == 422
    )
    imported = {
        "CODE": 200,
        "STATUS": "SUCCESS",
        "TOTAL_RECORDS": 1,
        "RESPONSE": [
            {
                "UNIQUE_QUERY_ID": "history-lead",
                "QUERY_TIME": "2026-03-01 09:15:00",
                "SENDER_NAME": "Old enquiry",
                "SENDER_MOBILE": "9876543210",
            }
        ],
    }
    empty = {
        "CODE": 204,
        "STATUS": "FAILURE",
        "MESSAGE": "There are no leads in the given time duration.",
    }
    due = "UPDATE crm.marketplace_accounts SET next_allowed_at=now()-interval '1 minute',next_live_at=now()-interval '1 minute' WHERE org_id=:org"
    assert (
        client.post(
            f"{path}/test", json={"row_version": account["row_version"]}
        ).status_code
        == 200
    )
    assert run_worker(client, org, lambda request: httpx.Response(200, json=empty), due)
    account = client.get("/api/v1/marketplace/accounts").json()["data"][0]
    assert account["verified_version"] == account["credential_version"]
    assert (
        client.post(
            f"{path}/activate", json={"row_version": account["row_version"]}
        ).status_code
        == 200
    )
    assert run_worker(client, org, lambda request: httpx.Response(200, json=empty), due)
    runs = client.get(f"{path}/runs").json()["data"]
    assert runs[0]["kind"] == "sync" and runs[0]["state"] == "completed"
    # Live sync is not due before the next slot, so the free slot goes to history.
    free_slot = "UPDATE crm.marketplace_accounts SET next_allowed_at=now()-interval '1 minute',next_live_at=now()+interval '15 minutes' WHERE org_id=:org"
    assert run_worker(
        client, org, lambda request: httpx.Response(200, json=imported), free_slot
    )
    run = client.get(f"{path}/runs").json()["data"][0]
    assert run["kind"] == "backfill" and run["state"] == "completed", run
    assert run["accepted_count"] == 1 and run["window_end"]
    lead = client.get(f"/api/v1/leads?integration_id={account['id']}").json()["data"][0]
    received = datetime.fromisoformat(lead["received_at"].replace("Z", "+00:00"))
    assert received == datetime(2026, 3, 1, 3, 45, tzinfo=timezone.utc)
    live_soon = "UPDATE crm.marketplace_accounts SET next_allowed_at=now()-interval '1 minute',next_live_at=now()+interval '1 minute' WHERE org_id=:org"
    assert not run_worker(
        client, org, lambda request: httpx.Response(200, json=imported), live_soon
    )
    status = client.get("/api/v1/marketplace/accounts").json()["data"][0][
        "schedule_status"
    ]
    assert (
        status["history"]["windows_done"] == 1
        and status["history"]["windows_pending"] == 52
    )
    assert status["history"]["eta"]
    backfill = status["history"]["id"]
    windows = client.get(f"{path}/backfills/{backfill}/windows?limit=10").json()
    assert windows["data"][0]["state"] == "completed" and windows["next_cursor"]
    following = client.get(
        f"{path}/backfills/{backfill}/windows?limit=10&after={windows['next_cursor']}"
    ).json()
    assert following["data"][0]["window_end"] == windows["data"][-1]["window_start"]
    assert len(client.get(f"{path}/backfills").json()["data"]) == 1
    scheduled = client.put(f"{path}/schedule", json={"sync_interval_seconds": 300})
    assert scheduled.status_code == 200, scheduled.text
    body = scheduled.json()
    assert (
        body["row_version"]
        == client.get("/api/v1/marketplace/accounts").json()["data"][0]["row_version"]
    )
    assert (
        body["verified_version"] == body["credential_version"]
        and body["status"] == "active"
    )
    assert body["schedule_status"]["history"]["reason"] in (
        "import_paused_interval_5min",
        "worker_offline",
    )
    assert (
        client.post(f"{path}/backfills/{backfill}/retry").json()["code"]
        == "marketplace_backfill_nothing_to_retry"
    )
    cancelled = client.post(f"{path}/backfills/{backfill}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    history = cancelled.json()["schedule_status"]["history"]
    assert (
        history["state"] == "cancelled"
        and history["reason"] == "import_cancelled_by_user"
    )
    requests = client.get("/api/v1/marketplace/backfills").json()
    assert [item["id"] for item in requests["data"]] == [backfill]
    assert requests["data"][0]["account_name"] == "History account"
    assert (
        requests["data"][0]["requested_by"] and requests["data"][0]["kind"] == "import"
    )
    assert client.get("/api/v1/marketplace/backfills?state=active").json()["data"] == []
    assert client.post("/api/v1/leads", json={"name": "Manual lead"}).status_code == 201
    imported_leads = client.get(f"/api/v1/leads?backfill_id={backfill}").json()["data"]
    assert [item["name"] for item in imported_leads] == ["Old enquiry"]
    assert imported_leads[0]["backfill_id"] == backfill


def test_database_lead_export_is_excel_scoped_and_formula_safe(marketplace_owner):
    from io import BytesIO
    from openpyxl import load_workbook

    client = marketplace_owner
    for name in ('=HYPERLINK("http://example.com","x")', "Plain lead"):
        assert (
            client.post(
                "/api/v1/leads", json={"name": name, "phone": "+911234"}
            ).status_code
            == 201
        )
    response = client.get("/api/v1/leads/export?q=Plain")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert 'filename="leads-' in response.headers["content-disposition"]
    sheet = load_workbook(BytesIO(response.content)).active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][:4] == ("Name", "Company", "Phone", "Email")
    assert [row[0] for row in rows[1:]] == ["Plain lead"]
    everything = load_workbook(
        BytesIO(client.get("/api/v1/leads/export").content)
    ).active
    formula = next(
        row
        for row in everything.iter_rows()
        if str(row[0].value).startswith("=HYPERLINK")
    )
    assert formula[0].data_type == "s"
    assert formula[2].value == "+911234" and formula[2].data_type == "s"
    assert (
        client.get("/api/v1/leads/export?start=2026-02-01&end=2026-01-01").status_code
        == 422
    )


def test_database_long_pause_moves_missed_range_to_history(marketplace_owner):
    import httpx
    from datetime import datetime, timedelta
    from app.modules.marketplace.schedule import IST

    if not os.environ.get("TEST_WORKER_DATABASE_URL"):
        pytest.skip("Requires provisioned crm_worker role")
    client = marketplace_owner
    org = UUID(client.get("/api/v1/auth/me").json()["organization_id"])
    account = add_account(client, "Gap account", f"gap-{uuid4()}")
    path = f"/api/v1/marketplace/accounts/{account['id']}"
    empty = {
        "CODE": 204,
        "STATUS": "FAILURE",
        "MESSAGE": "There are no leads in the given time duration.",
    }
    seen = []

    def respond(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=empty)

    due = "UPDATE crm.marketplace_accounts SET next_allowed_at=now()-interval '1 minute',next_live_at=now()-interval '1 minute' WHERE org_id=:org"
    assert client.post(f"{path}/test", json={"row_version": 1}).status_code == 200
    assert run_worker(client, org, respond, due)
    account = client.get("/api/v1/marketplace/accounts").json()["data"][0]
    assert (
        client.post(
            f"{path}/activate", json={"row_version": account["row_version"]}
        ).status_code
        == 200
    )
    paused = due.replace(" WHERE", ",watermark=now()-interval '20 days' WHERE")
    assert run_worker(client, org, respond, paused)
    started = datetime.strptime(seen[-1]["start_time"], "%d-%b-%Y%H:%M:%S").replace(
        tzinfo=IST
    )
    assert abs(datetime.now(IST) - timedelta(days=7) - started) < timedelta(minutes=10)
    history = client.get("/api/v1/marketplace/accounts").json()["data"][0][
        "schedule_status"
    ]["history"]
    assert history["kind"] == "gap" and history["windows_total"] == 2
    assert history["reason"] == "gap_recovery"
    assert run_worker(client, org, respond, due)
    started = datetime.strptime(seen[-1]["start_time"], "%d-%b-%Y%H:%M:%S").replace(
        tzinfo=IST
    )
    assert datetime.now(IST) - started < timedelta(minutes=15)
    history = client.get("/api/v1/marketplace/accounts").json()["data"][0][
        "schedule_status"
    ]["history"]
    assert history["windows_total"] == 2
