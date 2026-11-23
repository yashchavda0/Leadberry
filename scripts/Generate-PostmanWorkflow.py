from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "postman" / "CRM-All-APIs.postman_collection.json"
TARGET = ROOT / "postman" / "CRM-End-to-End-Workflow.postman_collection.json"
ENVIRONMENT = ROOT / "postman" / "CRM-Workflow.postman_environment.json"

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def operation_key(request: dict) -> str:
    path = "/" + "/".join(request["url"]["path"])
    path = re.sub(r"\{\{([^}]+)\}\}", r"{\1}", path)
    return f"{request['method']} {path}"


def test_event(lines: list[str]) -> dict:
    return {
        "listen": "test",
        "script": {"type": "text/javascript", "exec": lines},
    }


def prerequest_event(lines: list[str]) -> dict:
    return {
        "listen": "prerequest",
        "script": {"type": "text/javascript", "exec": lines},
    }


def ok_test(label: str, codes: list[int] | None = None) -> list[str]:
    values = codes or [200, 201, 204]
    return [
        f"pm.test('{label}', function () {{",
        f"  pm.expect([{', '.join(map(str, values))}]).to.include(pm.response.code);",
        "});",
    ]


def set_body(request_item: dict, body: dict) -> None:
    raw = json.dumps(body, indent=2)
    for numeric_variable in ("leadRowVersion", "accountRowVersion"):
        raw = raw.replace(
            f'"{{{{{numeric_variable}}}}}"', f"{{{{{numeric_variable}}}}}"
        )
    request_item["request"]["body"] = {
        "mode": "raw",
        "raw": raw,
        "options": {"raw": {"language": "json"}},
    }


def enable_csrf(request_item: dict) -> None:
    for header in request_item["request"].get("header", []):
        if header.get("key") == "X-CSRF-Token":
            header["disabled"] = False


def set_query(request_item: dict, **values: str) -> None:
    url = request_item["request"]["url"]
    query = url.get("query", [])
    for key, value in values.items():
        existing = next((item for item in query if item["key"] == key), None)
        if existing:
            existing.update(value=value, disabled=False)
        else:
            query.append({"key": key, "value": value, "disabled": False})
    url["query"] = query
    url["raw"] = url["raw"].split("?", 1)[0]
    if query:
        url["raw"] += "?" + "&".join(
            f"{item['key']}={item['value']}"
            for item in query
            if not item.get("disabled")
        )


def rename(item: dict, name: str) -> dict:
    clone = deepcopy(item)
    clone["name"] = name
    return clone


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    operations: dict[str, dict] = {}
    for folder in source["item"]:
        for item in folder["item"]:
            operations[operation_key(item["request"])] = item

    def op(
        key: str, name: str, body: dict | None = None, codes: list[int] | None = None
    ) -> dict:
        if key not in operations:
            raise RuntimeError(f"OpenAPI operation missing from API catalog: {key}")
        item = rename(operations[key], name)
        if body is not None:
            set_body(item, body)
        if item["request"]["method"] in MUTATING:
            enable_csrf(item)
        item["event"] = [test_event(ok_test(name, codes))]
        return item

    bootstrap = {
        "prerequest": [
            "const run = Date.now().toString(36);",
            "pm.collectionVariables.set('runKey', run);",
            "pm.environment.set('organizationSlug', 'workflow-' + run);",
            "pm.environment.set('organizationName', 'Workflow Organization ' + run);",
            "pm.environment.set('ownerEmail', 'owner.' + run + '@example.com');",
            "pm.environment.set('memberEmail', 'member.' + run + '@example.com');",
        ]
    }

    live = op("GET /api/v1/health/live", "00.01 Liveness")
    ready = op("GET /api/v1/health/ready", "00.02 Readiness")

    onboard = op(
        "POST /api/v1/organizations/onboard",
        "01.01 Create organization",
        {
            "organization_slug": "{{organizationSlug}}",
            "organization_name": "{{organizationName}}",
            "email": "{{ownerEmail}}",
            "password": "{{ownerPassword}}",
            "full_name": "Workflow Owner",
            "timezone": "Asia/Kolkata",
        },
    )
    for header in onboard["request"]["header"]:
        if header.get("key") == "X-CSRF-Token":
            header["disabled"] = True
    onboard["event"] = [
        test_event(
            [
                *ok_test("Organization created", [201]),
                "const body = pm.response.json();",
                "pm.environment.set('csrfToken', body.csrf_token);",
                "pm.environment.set('organizationId', body.organization_id);",
            ]
        )
    ]
    onboard["event"].insert(0, prerequest_event(bootstrap["prerequest"]))

    me = op("GET /api/v1/auth/me", "01.02 Owner identity")
    me["event"] = [
        test_event(
            [
                *ok_test("Owner identity loaded"),
                "const body = pm.response.json();",
                "pm.environment.set('ownerMembershipId', body.membership_id);",
                "pm.environment.set('organizationId', body.organization_id);",
            ]
        )
    ]
    org_get = op("GET /api/v1/organizations/me", "01.03 Read organization")
    org_put = op(
        "PUT /api/v1/organizations/me",
        "01.04 Update organization",
        {
            "name": "{{organizationName}} Updated",
            "timezone": "Asia/Kolkata",
            "website": "https://example.com",
            "business_email": "ops@example.com",
            "business_phone": "+919876543210",
            "address": "123 Workflow Road",
            "city": "Mumbai",
            "state": "Maharashtra",
            "postal_code": "400001",
            "country": "IN",
            "currency": "INR",
        },
    )
    profile_get = op("GET /api/v1/auth/profile", "01.05 Read owner profile")
    profile_put = op(
        "PUT /api/v1/auth/profile",
        "01.06 Update owner profile",
        {
            "display_name": "Workflow Owner Updated",
            "phone": "+919876543210",
            "job_title": "Administrator",
            "date_of_birth": "1990-01-01",
            "gender": "prefer_not_to_say",
            "address": "123 Workflow Road",
            "city": "Mumbai",
            "state": "Maharashtra",
        },
    )

    permissions = op("GET /api/v1/permissions", "02.01 List permissions")
    permissions["event"] = [
        test_event(
            [
                *ok_test("Permissions loaded"),
                "const body = pm.response.json();",
                "pm.environment.set('rolePermissions', JSON.stringify(body.data.map(x => x.code)));",
            ]
        )
    ]
    create_role = op(
        "POST /api/v1/roles",
        "02.02 Create manager role",
        {
            "name": "Workflow Manager",
            "description": "Generated by the Postman end-to-end workflow",
            "data_scope": "all",
            "permissions": [
                "dashboard.view",
                "leads.view",
                "leads.create",
                "leads.edit",
                "leads.assign",
                "leads.archive",
                "leads.restore",
                "leads.export",
                "leads.pii.view",
                "reports.view",
                "reports.export",
                "marketplace.view",
                "users.view",
                "roles.view",
                "settings.view",
            ],
            "is_active": True,
            "reports_to_role_id": None,
        },
        [201],
    )
    create_role["event"] = [
        test_event(
            [
                *ok_test("Manager role created", [201]),
                "pm.environment.set('roleId', pm.response.json().id);",
                "pm.environment.set('role_id', pm.response.json().id);",
            ]
        )
    ]
    update_role = op(
        "PUT /api/v1/roles/{role_id}",
        "02.03 Update manager role",
        {
            "name": "Workflow Manager Updated",
            "description": "Updated by the Postman end-to-end workflow",
            "data_scope": "all",
            "permissions": [
                "dashboard.view",
                "leads.view",
                "leads.create",
                "leads.edit",
                "leads.assign",
                "leads.archive",
                "leads.restore",
                "leads.export",
                "leads.pii.view",
                "reports.view",
                "reports.export",
                "marketplace.view",
                "users.view",
                "roles.view",
                "settings.view",
            ],
            "is_active": True,
            "reports_to_role_id": None,
        },
    )
    roles_get = op("GET /api/v1/roles", "02.04 Verify roles")

    invite = op(
        "POST /api/v1/invitations",
        "03.01 Invite workflow member",
        {
            "email": "{{memberEmail}}",
            "display_name": "Workflow Member",
            "role_ids": ["{{roleId}}"],
            "visibility_override": "all",
            "landing_page": "/leads",
        },
        [201],
    )
    invite["event"] = [
        test_event(
            [
                *ok_test("Invitation created", [201]),
                "const body = pm.response.json();",
                "pm.environment.set('invitedMembershipId', body.membership_id);",
                "pm.environment.set('membershipId', body.membership_id);",
                "pm.environment.set('membership_id', body.membership_id);",
                "pm.environment.set('invitationToken', body.invitation_token);",
            ]
        )
    ]
    recover_invite = op(
        "GET /api/v1/memberships/{membership_id}/invitation",
        "03.02 Recover invitation token",
    )
    recover_invite["event"] = [
        test_event(
            [
                *ok_test("Invitation recovered"),
                "pm.environment.set('invitationToken', pm.response.json().invitation_token);",
            ]
        )
    ]
    accept = op(
        "POST /api/v1/auth/accept-invite",
        "03.03 Accept invitation",
        {
            "invitation_token": "{{invitationToken}}",
            "password": "{{memberPassword}}",
        },
    )
    for header in accept["request"]["header"]:
        if header.get("key") == "X-CSRF-Token":
            header["disabled"] = True
    accept["event"] = [
        test_event(
            [
                *ok_test("Invitation accepted"),
                "const body = pm.response.json();",
                "pm.environment.set('memberCsrfToken', body.csrf_token);",
                "pm.environment.set('csrfToken', body.csrf_token);",
            ]
        )
    ]
    member_me = op("GET /api/v1/auth/me", "03.04 Invited member identity")
    member_me["event"] = [
        test_event(
            [
                *ok_test("Member session loaded"),
                "pm.environment.set('invitedMembershipId', pm.response.json().membership_id);",
            ]
        )
    ]
    member_profile = op(
        "PUT /api/v1/auth/profile",
        "03.05 Update invited member profile",
        {
            "display_name": "Workflow Member Updated",
            "phone": "+919812345678",
            "job_title": "Sales Manager",
            "date_of_birth": "1992-05-10",
            "gender": "prefer_not_to_say",
            "address": "456 Workflow Avenue",
            "city": "Pune",
            "state": "Maharashtra",
        },
    )

    owner_login = op(
        "POST /api/v1/auth/login",
        "04.01 Restore owner session",
        {
            "organization_slug": "{{organizationSlug}}",
            "email": "{{ownerEmail}}",
            "password": "{{ownerPassword}}",
        },
    )
    for header in owner_login["request"]["header"]:
        if header.get("key") == "X-CSRF-Token":
            header["disabled"] = True
    owner_login["event"] = [
        test_event(
            [
                *ok_test("Owner logged in"),
                "pm.environment.set('csrfToken', pm.response.json().csrf_token);",
            ]
        )
    ]
    memberships = op("GET /api/v1/memberships", "04.02 List members")
    update_member = op(
        "PUT /api/v1/memberships/{membership_id}",
        "04.03 Update member role and scope",
        {
            "status": "active",
            "role_ids": ["{{roleId}}"],
            "visibility_override": "all",
            "is_owner": False,
            "permission_overrides": {"leads.pii.view": True},
            "landing_page": "/leads",
            "display_name": "Workflow Member Updated",
        },
    )
    disable_member = op(
        "DELETE /api/v1/memberships/{membership_id}", "04.04 Disable member"
    )
    reactivate_member = rename(
        update_member, "04.05 Reactivate member for remaining workflow"
    )

    list_statuses = op("GET /api/v1/lead-statuses", "05.01 List lead statuses")
    list_statuses["event"] = [
        test_event(
            [
                *ok_test("Statuses loaded"),
                "const statuses = pm.response.json().data;",
                "const defaultStatus = statuses.find(x => x.is_default);",
                "pm.environment.set('defaultStatusId', defaultStatus.id);",
            ]
        )
    ]
    create_status = op(
        "POST /api/v1/lead-statuses",
        "05.02 Create workflow status",
        {
            "name": "Workflow Working",
            "category": "working",
            "color": "#2563EB",
            "position": 50,
            "is_active": True,
        },
        [201],
    )
    create_status["event"] = [
        test_event(
            [
                *ok_test("Workflow status created", [201]),
                "pm.environment.set('statusId', pm.response.json().id);",
                "pm.environment.set('status_id', pm.response.json().id);",
                "pm.environment.set('newStatusId', pm.response.json().id);",
            ]
        )
    ]
    status_options = op("GET /api/v1/lead-status-options", "05.03 Status options")
    update_status = op(
        "PUT /api/v1/lead-statuses/{status_id}",
        "05.04 Update workflow status",
        {
            "name": "Workflow Working Updated",
            "category": "working",
            "color": "#0F766E",
            "position": 51,
            "is_active": True,
        },
    )
    rules = op(
        "PUT /api/v1/lead-statuses/{status_id}/rules",
        "05.05 Configure status rules",
        {
            "tag_on_entry": "workflow",
            "auto_assign": False,
            "member_ids": [],
            "role_ids": ["{{roleId}}"],
            "required_fields": [],
        },
    )

    custom_list = op("GET /api/v1/lead-custom-fields", "06.01 List custom fields")
    custom_create = op(
        "POST /api/v1/lead-custom-fields",
        "06.02 Create custom field",
        {
            "field_key": "workflow_source",
            "label": "Workflow Source",
            "field_type": "select",
            "options": ["postman", "api"],
            "position": 10,
            "is_active": True,
        },
        [201],
    )
    custom_create["event"] = [
        test_event(
            [
                *ok_test("Custom field created", [201]),
                "pm.environment.set('customFieldKey', pm.response.json().field_key);",
            ]
        )
    ]
    custom_update = op(
        "PUT /api/v1/lead-custom-fields/{field_key}",
        "06.03 Update custom field",
        {
            "label": "Workflow Source Updated",
            "field_type": "select",
            "options": ["postman", "api", "manual"],
            "position": 11,
            "is_active": True,
        },
    )
    prefs_get = op("GET /api/v1/lead-table-preferences", "06.04 Read table preferences")
    prefs_put = op(
        "PUT /api/v1/lead-table-preferences",
        "06.05 Save table preferences",
        {"columns": ["name", "company", "phone", "status", "assignee", "received_at"]},
    )

    teams_get = op("GET /api/v1/teams", "07.01 List teams")
    team_create = op(
        "POST /api/v1/teams",
        "07.02 Create team",
        {
            "name": "Workflow Team",
            "is_active": True,
            "membership_ids": ["{{ownerMembershipId}}", "{{invitedMembershipId}}"],
        },
        [201],
    )
    team_create["event"] = [
        test_event(
            [
                *ok_test("Team created", [201]),
                "pm.environment.set('teamId', pm.response.json().id);",
                "pm.environment.set('team_id', pm.response.json().id);",
            ]
        )
    ]
    team_update = op(
        "PUT /api/v1/teams/{team_id}",
        "07.03 Update team",
        {
            "name": "Workflow Team Updated",
            "is_active": True,
            "membership_ids": ["{{ownerMembershipId}}", "{{invitedMembershipId}}"],
        },
    )

    lead_options = op("GET /api/v1/leads/options", "08.01 Lead options")
    assignees = op("GET /api/v1/leads/assignees", "08.02 Assignment options")
    lead_create = op(
        "POST /api/v1/leads",
        "08.03 Create lead",
        {
            "name": "Postman Workflow Lead",
            "company": "Workflow Company",
            "phone": "9876543210",
            "email": "lead@example.com",
            "city": "Mumbai",
            "state": "Maharashtra",
            "address": "789 Workflow Street",
            "product": "Enterprise CRM",
            "enquiry": "Created by the Postman end-to-end workflow",
            "source_provider": "manual",
            "status_id": "{{statusId}}",
            "assigned_membership_id": "{{ownerMembershipId}}",
            "team_id": "{{teamId}}",
            "tags": ["postman", "workflow"],
            "custom_fields": {"workflow_source": "postman"},
            "next_follow_up_at": "2026-11-30T10:00:00+05:30",
        },
        [201],
    )
    lead_create["event"] = [
        test_event(
            [
                *ok_test("Lead created", [201]),
                "const body = pm.response.json();",
                "pm.environment.set('leadId', body.id);",
                "pm.environment.set('lead_id', body.id);",
                "pm.environment.set('leadRowVersion', body.row_version);",
            ]
        )
    ]
    lead_list = op("GET /api/v1/leads", "08.04 List leads")
    lead_detail = op("GET /api/v1/leads/{lead_id}", "08.05 Read lead")
    lead_detail["event"] = [
        test_event(
            [
                *ok_test("Lead loaded"),
                "pm.environment.set('leadRowVersion', pm.response.json().row_version);",
            ]
        )
    ]
    lead_update = op(
        "PUT /api/v1/leads/{lead_id}",
        "08.06 Update lead",
        {
            "name": "Postman Workflow Lead Updated",
            "company": "Workflow Company",
            "phone": "9876543210",
            "email": "lead@example.com",
            "city": "Mumbai",
            "state": "Maharashtra",
            "address": "789 Workflow Street",
            "product": "Enterprise CRM Pro",
            "enquiry": "Updated by the Postman end-to-end workflow",
            "source_provider": "manual",
            "status_id": "{{statusId}}",
            "assigned_membership_id": "{{invitedMembershipId}}",
            "team_id": "{{teamId}}",
            "tags": ["postman", "workflow", "updated"],
            "custom_fields": {"workflow_source": "api"},
            "next_follow_up_at": "2026-12-01T10:00:00+05:30",
            "row_version": "{{leadRowVersion}}",
        },
    )
    lead_update["event"] = [
        test_event(
            [
                *ok_test("Lead updated"),
                "pm.environment.set('leadRowVersion', pm.response.json().row_version);",
            ]
        )
    ]
    status_change = op(
        "POST /api/v1/leads/{lead_id}/status",
        "08.07 Change lead status",
        {
            "status_id": "{{defaultStatusId}}",
            "note": "Changed during the Postman workflow",
            "next_follow_up_at": "2026-12-02T10:00:00+05:30",
            "row_version": "{{leadRowVersion}}",
        },
    )
    status_change["event"] = [
        test_event(
            [
                *ok_test("Lead status changed"),
                "pm.environment.set('leadRowVersion', pm.response.json().row_version);",
            ]
        )
    ]
    status_history = op(
        "GET /api/v1/leads/{lead_id}/status-history", "08.08 Status history"
    )
    archive = op(
        "POST /api/v1/leads/{lead_id}/archive",
        "08.09 Archive lead",
        {"row_version": "{{leadRowVersion}}"},
    )
    archive["event"] = [
        test_event(
            [
                *ok_test("Lead archived"),
                "pm.environment.set('leadRowVersion', pm.response.json().row_version);",
            ]
        )
    ]
    restore = op(
        "POST /api/v1/leads/{lead_id}/restore",
        "08.10 Restore lead",
        {"row_version": "{{leadRowVersion}}"},
    )
    restore["event"] = [
        test_event(
            [
                *ok_test("Lead restored"),
                "pm.environment.set('leadRowVersion', pm.response.json().row_version);",
            ]
        )
    ]

    dashboard = op("GET /api/v1/dashboard", "09.01 Dashboard")
    report = op("GET /api/v1/reports/leads", "09.02 Lead report")
    export_report = op(
        "GET /api/v1/reports/leads/export", "09.03 Export report", codes=[200]
    )
    export_leads = op("GET /api/v1/leads/export", "09.04 Export leads", codes=[200])

    providers = op("GET /api/v1/marketplace/providers", "10.01 Marketplace providers")
    accounts = op("GET /api/v1/marketplace/accounts", "10.02 List marketplace accounts")
    create_account = op(
        "POST /api/v1/marketplace/accounts",
        "10.03 Create draft marketplace account",
        {
            "provider_code": "indiamart",
            "name": "Postman Dummy Connector",
            "config": {},
            "credentials": {"crm_key": "dummy-crm-key-for-workflow"},
            "sync_interval_seconds": 900,
            "import_history": False,
            "row_version": None,
        },
        [201, 503],
    )
    create_account["event"] = [
        test_event(
            [
                "pm.test('Marketplace account endpoint reached', function () {",
                "  pm.expect([201, 503]).to.include(pm.response.code);",
                "});",
                "if (pm.response.code === 201) {",
                "  const body = pm.response.json();",
                "  pm.environment.set('accountId', body.id);",
                "  pm.environment.set('account_id', body.id);",
                "  pm.environment.set('accountRowVersion', body.row_version);",
                "} else {",
                "  pm.execution.setNextRequest('11.01 Refresh owner session');",
                "}",
            ]
        )
    ]
    update_account = op(
        "PUT /api/v1/marketplace/accounts/{account_id}",
        "10.04 Update marketplace account",
        {
            "provider_code": "indiamart",
            "name": "Postman Dummy Connector Updated",
            "config": {},
            "credentials": {},
            "row_version": "{{accountRowVersion}}",
        },
    )
    update_account["event"] = [
        test_event(
            [
                *ok_test("Marketplace account updated"),
                "const body = pm.response.json();",
                "pm.environment.set('accountRowVersion', body.row_version);",
            ]
        )
    ]
    schedule = op(
        "PUT /api/v1/marketplace/accounts/{account_id}/schedule",
        "10.05 Update marketplace schedule",
        {"sync_interval_seconds": 600},
    )
    schedule["event"] = [
        test_event(
            [
                *ok_test("Marketplace schedule updated"),
                "pm.environment.set('accountRowVersion', pm.response.json().row_version);",
            ]
        )
    ]
    create_backfill = op(
        "POST /api/v1/marketplace/accounts/{account_id}/backfills",
        "10.06 Create backfill request",
        {"from_date": "2026-11-18", "to_date": "2026-11-20"},
        [201, 200],
    )
    create_backfill["event"] = [
        test_event(
            [
                *ok_test("Backfill request created", [200, 201]),
                "const body = pm.response.json();",
                "const candidate = body.backfill_id || (body.backfill && body.backfill.id);",
                "if (candidate) {",
                "  pm.environment.set('backfillId', candidate);",
                "  pm.environment.set('backfill_id', candidate);",
                "}",
            ]
        )
    ]
    list_account_backfills = op(
        "GET /api/v1/marketplace/accounts/{account_id}/backfills",
        "10.07 List account backfills",
    )
    list_account_backfills["event"] = [
        test_event(
            [
                *ok_test("Account backfills loaded"),
                "const rows = pm.response.json().data || [];",
                "if (rows[0]) {",
                "  pm.environment.set('backfillId', rows[0].id);",
                "  pm.environment.set('backfill_id', rows[0].id);",
                "}",
            ]
        )
    ]
    list_all_backfills = op(
        "GET /api/v1/marketplace/backfills", "10.08 List all import requests"
    )
    list_windows = op(
        "GET /api/v1/marketplace/accounts/{account_id}/backfills/{backfill_id}/windows",
        "10.09 List backfill windows",
    )
    backfill_cancel = op(
        "POST /api/v1/marketplace/accounts/{account_id}/backfills/{backfill_id}/{action}",
        "10.10 Cancel backfill request",
    )
    backfill_cancel["event"].insert(
        0, prerequest_event(["pm.environment.set('action', 'cancel');"])
    )
    account_action = op(
        "POST /api/v1/marketplace/accounts/{account_id}/{action}",
        "10.11 Queue connector test",
        {"row_version": "{{accountRowVersion}}"},
        [200],
    )
    account_action["event"].insert(
        0, prerequest_event(["pm.environment.set('action', 'test');"])
    )
    account_runs = op(
        "GET /api/v1/marketplace/accounts/{account_id}/runs",
        "10.12 List connector runs",
    )

    refresh = op("POST /api/v1/auth/refresh", "11.01 Refresh owner session")
    refresh["event"] = [
        test_event(
            [
                *ok_test("Owner session refreshed"),
                "pm.environment.set('csrfToken', pm.response.json().csrf_token);",
            ]
        )
    ]
    logout = op("POST /api/v1/auth/logout", "11.02 Logout owner", codes=[204])

    sections = {
        "00 Health": [live, ready],
        "01 Organization and owner": [
            onboard,
            me,
            org_get,
            org_put,
            profile_get,
            profile_put,
        ],
        "02 Roles and permissions": [permissions, create_role, update_role, roles_get],
        "03 Invitation lifecycle": [
            invite,
            recover_invite,
            accept,
            member_me,
            member_profile,
            owner_login,
        ],
        "04 Membership management": [
            memberships,
            update_member,
            disable_member,
            reactivate_member,
        ],
        "05 Lead statuses": [
            list_statuses,
            create_status,
            status_options,
            update_status,
            rules,
        ],
        "06 Custom fields and table preferences": [
            custom_list,
            custom_create,
            custom_update,
            prefs_get,
            prefs_put,
        ],
        "07 Teams": [teams_get, team_create, team_update],
        "08 Lead lifecycle": [
            lead_options,
            assignees,
            lead_create,
            lead_list,
            lead_detail,
            lead_update,
            status_change,
            status_history,
            archive,
            restore,
        ],
        "09 Reports and exports": [dashboard, report, export_report, export_leads],
        "10 Marketplace flow": [
            providers,
            accounts,
            create_account,
            update_account,
            schedule,
            create_backfill,
            list_account_backfills,
            list_all_backfills,
            list_windows,
            backfill_cancel,
            account_action,
            account_runs,
        ],
        "11 Session lifecycle": [refresh, logout],
    }

    all_keys = {key for folder in sections.values() for key in folder if False}
    collection = {
        "info": {
            "_postman_id": str(uuid4()),
            "name": "CRM - End-to-End API Workflow",
            "description": (
                "Ordered, stateful workflow generated from every currently implemented backend API. "
                "Import CRM-Workflow.postman_environment.json and run the collection in saved order. "
                "It creates a unique organization, roles, invitation/member, lead configuration, team, "
                "lead lifecycle, reports, and a dummy marketplace account. Dummy marketplace credentials "
                "can create and queue connector work, but an external provider test may later fail as "
                "expected because no real IndiaMART key is used. API and local database flows otherwise use live IDs and tokens."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [],
        "item": [{"name": title, "item": items} for title, items in sections.items()],
        "auth": {"type": "noauth"},
    }
    TARGET.write_text(json.dumps(collection, indent=2), encoding="utf-8")

    environment = {
        "id": str(uuid4()),
        "name": "CRM Workflow - Local",
        "values": [
            {
                "key": "baseUrl",
                "value": "http://127.0.0.1:8000",
                "type": "default",
                "enabled": True,
            },
            {
                "key": "ownerPassword",
                "value": "WorkflowOwner123!",
                "type": "secret",
                "enabled": True,
            },
            {
                "key": "memberPassword",
                "value": "WorkflowMember123!",
                "type": "secret",
                "enabled": True,
            },
            {"key": "csrfToken", "value": "", "type": "secret", "enabled": True},
            {
                "key": "organizationSlug",
                "value": "",
                "type": "default",
                "enabled": True,
            },
            {
                "key": "organizationName",
                "value": "",
                "type": "default",
                "enabled": True,
            },
            {"key": "organizationId", "value": "", "type": "default", "enabled": True},
            {"key": "ownerEmail", "value": "", "type": "default", "enabled": True},
            {"key": "memberEmail", "value": "", "type": "default", "enabled": True},
            {"key": "invitationToken", "value": "", "type": "secret", "enabled": True},
            {"key": "roleId", "value": "", "type": "default", "enabled": True},
            {"key": "membershipId", "value": "", "type": "default", "enabled": True},
            {
                "key": "ownerMembershipId",
                "value": "",
                "type": "default",
                "enabled": True,
            },
            {
                "key": "invitedMembershipId",
                "value": "",
                "type": "default",
                "enabled": True,
            },
            {"key": "statusId", "value": "", "type": "default", "enabled": True},
            {"key": "defaultStatusId", "value": "", "type": "default", "enabled": True},
            {"key": "customFieldKey", "value": "", "type": "default", "enabled": True},
            {"key": "fieldKey", "value": "", "type": "default", "enabled": True},
            {
                "key": "field_key",
                "value": "workflow_source",
                "type": "default",
                "enabled": True,
            },
            {"key": "teamId", "value": "", "type": "default", "enabled": True},
            {"key": "leadId", "value": "", "type": "default", "enabled": True},
            {"key": "leadRowVersion", "value": "1", "type": "default", "enabled": True},
            {"key": "accountId", "value": "", "type": "default", "enabled": True},
            {
                "key": "accountRowVersion",
                "value": "1",
                "type": "default",
                "enabled": True,
            },
            {"key": "backfillId", "value": "", "type": "default", "enabled": True},
            {"key": "action", "value": "test", "type": "default", "enabled": True},
            {"key": "role_id", "value": "", "type": "default", "enabled": True},
            {"key": "membership_id", "value": "", "type": "default", "enabled": True},
            {"key": "status_id", "value": "", "type": "default", "enabled": True},
            {"key": "team_id", "value": "", "type": "default", "enabled": True},
            {"key": "lead_id", "value": "", "type": "default", "enabled": True},
            {"key": "account_id", "value": "", "type": "default", "enabled": True},
            {"key": "backfill_id", "value": "", "type": "default", "enabled": True},
        ],
        "_postman_variable_scope": "environment",
        "_postman_exported_using": "Generate-PostmanWorkflow.py",
    }
    ENVIRONMENT.write_text(json.dumps(environment, indent=2), encoding="utf-8")
    count = sum(len(items) for items in sections.values())
    print(f"Generated {count} workflow requests in {len(sections)} stages")


if __name__ == "__main__":
    main()
