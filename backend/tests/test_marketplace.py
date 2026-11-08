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
                "SENDER_MOBILE": "9876543210",
                "QUERY_MESSAGE": "Request a quote",
            }
        ],
    }
    lead = normalize_response(payload)[0]
    assert lead["source_record_id"] == "12345"
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

    body = {"status": "error", "message": "Rate limit exceed. Try After 15 minutes : A maximum of 5 requests is allowed every 5 minutes."}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403, json=body))
    ) as client:
        start = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc)
        with pytest.raises(AccessError) as failure:
            await fetch_leads(client, {"user_id": "1", "profile_id": "2"}, "fixture-api-key", start, start + timedelta(minutes=5))
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
    assert (
        client.put(
            "/api/v1/lead-table-preferences", json={"columns": ["status"]}
        ).json()["code"]
        == "invalid_lead_table_columns"
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
                        "UPDATE crm.marketplace_accounts SET next_allowed_at=now()-interval '1 minute' WHERE org_id=:org"
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
