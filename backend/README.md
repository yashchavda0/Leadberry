# CRM backend: one PostgreSQL application

The only backend is **`app.main:create_app --factory` on port 8000**.
The core application pipeline lives in `app/main.py`. All runtime storage uses
PostgreSQL and all HTTP endpoints use `/api/v1`.

Docker runs PostgreSQL/Redis; Python and Next.js run locally from source.
See [local infrastructure setup](../docs/DOCKER-SETUP.md).

## Start and migrate

From the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-LocalBackend.ps1 -Action Migrate
```

Start the API with uvicorn directly. The DB URLs are set in the terminal from the
ignored secret file, so passwords are never printed or saved to `.env`. The full
commands are in [local infrastructure setup](../docs/DOCKER-SETUP.md) (step 3).
For a manually configured environment, from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --loop app.core.event_loop:selector_event_loop --reload
```

Set `DATABASE_URL` to the restricted business role (`crm_api`) and
`AUTH_DATABASE_URL` to the restricted identity role (`crm_auth`). Both must target
the same PostgreSQL database/host/port with different users. Never run the API as
`postgres`, the schema owner or an identity inheriting schema ownership.
See [.env.example](.env.example) for supported settings.

On Windows, Psycopg async needs the selector event loop. Uvicorn otherwise uses
`ProactorEventLoop` when not reloading, which makes every DB call fail with a 503.
Always pass `--loop app.core.event_loop:selector_event_loop`, with or without `--reload`. Production
requires HTTPS origins and PostgreSQL `sslmode=verify-full`.

## Core request pipeline

1. `app/main.py` creates bounded business/identity database pools on startup.
2. Shared middleware disables response caching and sanitizes validation/database errors.
3. Identity routes authenticate the opaque HttpOnly session cookie, active membership
   and organization, session expiry and current effective permissions.
4. Authenticated writes validate browser Origin and `X-CSRF-Token`.
5. Business requests set transaction-local organization/membership context. Tenant
   RLS and composite foreign keys isolate organizations.
6. Lead requests re-check effective access under a shared organization lock;
   administrative access mutations use the exclusive lock. The same lead scope
   predicate is used for lists, detail, edits, archive/restore and dashboard counts.
7. Audit records and optimistic row versions make changes traceable and prevent
   stale edits overwriting newer data.

## Modules and migrations

| Location | Responsibility |
|---|---|
| `app/main.py` | Single app factory, lifecycle, middleware, errors, routers and health |
| `app/core/settings.py` | Validated settings, connection URLs and browser origins |
| `app/core/database.py` | Bounded engines, tenant transactions and role/schema readiness |
| `app/modules/identity/` | Passwords, sessions, onboarding, invitations, roles and membership access |
| `app/modules/leads/` | Scoped lead CRUD, filters, teams and dashboard |
| `migrations/versions/0001_foundation.py` | Organizations, users, memberships, settings/statuses and tenant invariants |
| `migrations/versions/0002_identity.py` | Permissions, roles, overrides, sessions/invitations, audit and throttling |
| `migrations/versions/0003_leads.py` | PostgreSQL leads, teams, indexes and tenant policies |
| `migrations/versions/0004_role_hierarchy.py` | Tenant-bound reporting roles and membership landing preferences |
| `migrations/versions/0005_marketplace.py` | Encrypted marketplace accounts, sync runs and rate limits |
| `migrations/versions/0006_database_grants.py` | Least-privilege table grants for `crm_api`, `crm_auth` and `crm_worker` |
| `app/modules/marketplace/` | Provider catalog, encrypted account setup, lifecycle APIs and IndiaMART worker |

Readiness expects `0006_database_grants` and checks both configured roles. Migrations do not
run during API startup. Use the migration helper rather than applying the full
[reference design SQL](../docs/database-schema.sql) on an Alembic-managed database.

## API endpoints

Development API docs: http://localhost:8000/api/v1/docs.
All paths below are relative to `/api/v1`.

Routes are grouped by business responsibility in both source code and Swagger.
Different methods for the same resource stay in the same router; they invoke the
existing business services rather than duplicating authentication or access logic.

| Swagger group | Route file | Use case |
|---|---|---|
| Authentication | `app/modules/identity/authentication.py` | Login, invitation acceptance, current identity, session refresh/logout |
| Organizations | `app/modules/identity/organizations.py` | Onboarding and GET/PUT organization profile |
| Roles and permissions | `app/modules/identity/role_routes.py` | Permission catalog and GET/POST/PUT role administration |
| Members and invitations | `app/modules/identity/memberships.py` | Membership access updates and invitation issuance |
| Leads | `app/modules/leads/routes.py` | Lead lists/options, creation, detail/update and archive/restore |
| Teams | `app/modules/leads/teams.py` | GET/POST/PUT team management |
| Dashboard | `app/modules/leads/dashboard.py` | Scoped dashboard statistics and recent leads |
| Marketplace | `app/modules/marketplace/routes.py` | Catalog/accounts, credential replacement, test/sync, activation/pause/retirement and history |
| Health | `app/main.py` | Liveness and readiness probes |

`app/modules/identity/routes.py` only assembles identity routers under `/api/v1`.
`app/modules/identity/dependencies.py` shares the authenticated principal,
Origin/CSRF checks, session cookies and public throttling.
`app/modules/leads/queries.py` shares tenant access locking, visibility predicates
and PII-safe projections between leads, teams and dashboard.
Organization profile validation now belongs to `app/modules/identity/schemas.py`.
Future email verification, password recovery and MFA routes belong alongside
authentication; they are not implemented or exposed as placeholders.

### Authentication

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login`, `/auth/accept-invite` | Establish a membership-bound session |
| GET | `/auth/me` | Effective identity, permissions and lead scope |
| POST | `/auth/refresh`, `/auth/logout` | Rotate token or revoke session |

### Organizations

| Method | Path | Purpose |
|---|---|---|
| POST | `/organizations/onboard` | Create organization and protected Owner |
| GET, PUT | `/organizations/me` | Read/update organization profile |

### Roles and permissions

| Method | Path | Purpose |
|---|---|---|
| GET | `/permissions` | Permission catalog |
| GET, POST | `/roles` | List/create custom roles |
| PUT | `/roles/{role_id}` | Replace role permissions/scope |

### Members and invitations

| Method | Path | Purpose |
|---|---|---|
| GET | `/memberships` | List organization members with login emails, roles and direct overrides |
| PUT | `/memberships/{membership_id}` | Update display name, roles, overrides, visibility, landing page, status or Owner flag |
| DELETE | `/memberships/{membership_id}` | Soft-disable membership and revoke sessions, preserving grants and history |
| POST | `/invitations` | Issue/reissue a 48-hour invitation |

Login emails remain read-only shared identities. Membership listing uses the
restricted identity pool to join emails only to tenant-filtered memberships;
the business pool gains no access to global identities. All membership writes
require `users.manage`, enforce the grant ceiling and protect the final active Owner.
Lead assignment requires `leads.assign` alongside applicable create/edit permissions
and existing visibility constraints.

### Leads

| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/leads` | Filter/list or create scoped leads |
| GET | `/leads/options`, `/leads/assignees` | Statuses and assignment choices |
| GET, PUT | `/leads/{lead_id}` | Detail or versioned replacement |
| POST | `/leads/{lead_id}/archive`, `/leads/{lead_id}/restore` | Versioned lifecycle actions |

### Teams

| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/teams` | List teams or Owner-only creation |
| PUT | `/teams/{team_id}` | Owner-only team/membership replacement |

### Dashboard and health

| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard` | Scoped counts, status/source breakdowns and recent leads |
| GET | `/health/live`, `/health/ready` | Liveness and schema/role/database readiness |

### Shared request contracts

List APIs use keyset pagination: `limit` is bounded to 100 and
`after=<next_cursor>` retrieves the next page. Lead lists accept `sort_by` and
`sort_dir=asc|desc` (default: `received_at` descending). Sorting applies to the
entire filtered result, uses the lead ID as a tie-breaker, and puts empty values
last. Active custom fields use `sort_by=custom:<field_key>`; contact and custom
fields require `leads.pii.view`. Cursors are tied to the selected sort and must
be restarted when it changes. Concurrent edits can move records between pages.
Lead filters include `q`, `status_id`, `source`, `tag`, `assignee`, `start`, `end`
and `archived`. Search uses indexed whole words in name/company/product/city,
not contact fields. Date filters use UTC and the end date is inclusive.
Dashboard "today" uses the organization's IANA timezone.

Lead edits and archive/restore require the current `row_version`; stale writes
return 409. Updates are full replacement of editable fields. Contact fields are
preserved for callers lacking `leads.pii.view` and are not returned to them.
Enquiry/custom fields are also redacted because they can contain contact data.

## Identity and scope rules

- Owners always receive all permissions and all-organization scope. An active
  organization cannot lose its final active Owner.
- Non-Owner permissions combine active roles; direct deny wins over role grants.
  Membership visibility overrides replace role scope.
- Own scope includes assigned leads and caller-created unassigned leads.
  Team scope also includes leads explicitly assigned to the caller's active teams.
  All scope includes the organization's leads. Explicit individual sharing is pending.
- Delegated administrators cannot grant beyond their own access or modify Owners.
  Disabling a membership revokes its sessions; other organization memberships remain independent.
- Login/onboarding/invitation acceptance set `crm_session` (HttpOnly) and `crm_csrf`.
  Preserve cookies and send `X-CSRF-Token` on protected writes, including logout/refresh.
  Default origins allow localhost/127.0.0.1 on ports 3000 and 8000.
- Sessions expire after a fixed 12 hours by default (`SESSION_HOURS`, 1-24). Refresh
  rotates the token without extending expiry; replay revokes the session.
- Invitations return a private token once for manual delivery. Existing users
  must verify their current password. Invited memberships cannot be manually activated.
- Passwords use Argon2id and bounded hashing concurrency. Database-backed throttling
  limits onboarding/authentication/login attempts; socket IPs are used, not forwarded headers.

## Validation and remaining work

`httpx` is a development-only API test dependency. `python-dotenv` is supplied
transitively by `pydantic-settings` and `uvicorn[standard]` for supported configuration
loading; it is not a separately declared application dependency.

```powershell
# From project root: real PostgreSQL tests, no browser installation
.\backend\.venv\Scripts\python.exe .\scripts\Run-PostgresTests.py

# From backend: unit tests plus opt-in PostgreSQL tests
.\.venv\Scripts\python.exe -m pytest -q
```

The isolated runner uses local infrastructure secrets, creates a uniquely named
test database and removes only that database afterward. Do not set test URLs to
your working `leadberry` database. No automated browser installation is required.

Email verification/recovery/delivery, MFA, provider workers/encrypted credentials,
reports/exports, custom field definitions and measured large-data load capacity
are not implemented. Enabling `require_mfa` fails closed on authentication and
invitation acceptance; it does not provide an MFA flow. Validate backup/restore,
deployment security and realistic concurrent load before production.
