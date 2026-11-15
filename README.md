# LeadBerry CRM

Multi-tenant CRM with one authenticated FastAPI/PostgreSQL backend on **port 8000**
and a Next.js frontend on **port 3000**. Docker runs PostgreSQL and Redis only.

## Start locally

From the project root in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Initialize-DockerSecrets.ps1
docker compose up -d --wait
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-LocalBackend.ps1 -Action Migrate
```

Then start the API with the uvicorn command in [local infrastructure setup](docs/DOCKER-SETUP.md) (step 3).

In a separate terminal:

```powershell
Set-Location .\frontend
npm.cmd run dev
```

- Create a workspace: http://localhost:3000/onboarding
- Sign in: http://localhost:3000/login
- API documentation: http://localhost:8000/api/v1/docs
- Database readiness: http://localhost:8000/api/v1/health/ready

See [infrastructure and dependency setup](docs/DOCKER-SETUP.md) for first-time installation.
The backend entrypoint is `app.main:create_app --factory`. All endpoints use `/api/v1`.
The frontend proxies those endpoints to `127.0.0.1:8000`; restart Next.js after
changing its proxy configuration. If using `CRM_BACKEND_URL`, set it to
`http://127.0.0.1:8000`.

## Implemented

- Organization onboarding, protected Owner, login/logout, sessions and invitations.
- Custom roles, page/action permissions, membership overrides and team management.
- Centralized User management with Users, Teams, Roles and Permissions tabs,
  automatic reporting levels, grouped Select all/Clear and per-user landing pages.
- Scoped PostgreSQL leads: creation/editing, tags, simple custom fields, contact
  redaction, indexed filters/search, cursor pagination, archive/restore and version conflicts.
- Single-page lead dashboard with outcomes, conversion rates, repeat enquiries,
  intake trends, follow-up priorities, and source/assignee performance within the caller's scope.
- Authenticated frontend for these features and organization profile settings.

The application uses PostgreSQL exclusively. Existing external data files are
not automatically imported. Do not delete Docker volumes to upgrade the application.

Marketplace now supports named accounts, encrypted write-only credentials,
IndiaMART pull-worker ingestion and TradeIndia draft setup. Other providers remain
gated pending verified adapters. See [marketplace setup and release boundaries](docs/MARKETPLACE-INTEGRATIONS.md).
Reports/downloads, email delivery/recovery, MFA and custom field definitions remain
future work. This is not a production-readiness or load-capacity claim.

## Documentation and validation

- [Backend pipeline and API guide](backend/README.md)
- [Database, backend and frontend architecture](docs/CRM-ARCHITECTURE.md)
- [PostgreSQL reference schema](docs/database-schema.sql)
- [Reference schema smoke checks](docs/database-smoke-test.sql)

Use Alembic migrations for the application database; do not apply the reference SQL
on top of it. To run backend tests without browser installation:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\Run-PostgresTests.py
```

The runner creates and removes only a uniquely named disposable test database.

### Lead Dashboard

Open the workspace home page with `dashboard.view`. Owners see organization-wide
data; other users retain their existing Own/Team/All visibility, including shared
unassigned leads. Lead drill-down links also require `leads.view`.

- All time is the default. Date ranges select leads by received date in the
   organization's timezone; archived leads are excluded. Custom ranges support
   up to 366 days. Outcomes and follow-ups reflect those leads' current state.
- Conversion rate is won leads divided by all selected leads. Closed-lead win
   rate is won divided by won plus lost. Lost / cancelled combines every status
   configured in the lost category, with individual statuses shown separately.
- Repeat enquiries count distinct visible lead records sharing a normalized
   phone or case-insensitive email with another selected lead. Shared contacts
   count phone/email keys, not unique people or verified repeat purchases.
- Intake shows daily leads received and Won/Lost status-change events for the
   latest 30 days ending at the selected end date, or today. Event counts include
   repeat transitions; the movement summary also shows distinct leads moved.
- Source and assignee tables show the top 20 by volume and disclose omitted
   lead totals. KPI totals always cover the entire accessible selection.
- Period performance compares received-lead cohorts with an equal-length
   immediately preceding period (the latest 30 days vs. the previous 30 by
   default). Cohort conversion uses each cohort's current status, so recent
   cohorts have had less time to mature.
- Pipeline aging buckets open leads by time since receipt; stalled leads have
   no status change in seven days. The handling-quality median is time to first
   recorded status-history update, not first customer response. Calls, emails,
   meetings, revenue, and structured lost reasons are not yet tracked.
- Pipeline movement counts distinct leads transitioned to Won/Lost and all
   transition events separately. Stage labels use current status names. Contact
   quality measures missing phone/email and missing city.

Dashboard regression checks: run the database runner with
`PYTEST_ADDOPTS="-k dashboard_analytics"`, and run the frontend Playwright suite
with `--grep "lead dashboard shows"`. The browser test uses deterministic API
fixtures and captures desktop, mobile, and tablet screenshots.

For manual UI testing: create an Owner, add a role, invite a user in a private
browser session, assign leads and verify scope/contact redaction, edit conflicts,
archive/restore, team revocation and cross-organization isolation.

### Test User management

Every user has a required login email, displayed in the Users list and read-only
in Edit access because it is shared across organizations. Add users through
**Invite user**; use **Edit access** to update their display name, roles, permissions,
visibility, landing page and status. **Delete** requires confirmation and soft-disables
the workspace membership, revoking sessions while preserving assigned leads,
teams, grants and history. Accepted users can be reactivated; an unaccepted deleted
invitation cannot be activated without completing a valid invitation flow.
The final active Owner cannot be deleted or disabled.

Lead assignment is controlled by **`leads.assign` (Assign / reassign leads)** in
the Leads permission group, including direct user overrides. It is not granted
automatically to every user. Creating/editing leads still requires the matching
action permissions, and assignment remains limited by Own/Team/All visibility.

After updating, run the migration command above and restart the backend.
Open **User management** in the sidebar:

1. In **Roles**, create Director without a reporting role, Manager reporting to
   Director, and Agent reporting to Manager. Verify Parent/Level 1, Child/Level 2
   and Child/Level 3. Clear Manager's reporting selection and save: Agent becomes
   Level 2. Reporting a role to its descendant is rejected.
2. In **Permissions**, edit a role. Each group has one button: **Select all**
   while any selectable permission remains, switching to **Clear** when all are selected;
   only permissions within your grant ceiling can be selected. Reporting hierarchy
   never grants additional permissions or lead visibility.
3. In **Users**, invite a colleague with an active role and a **Landing page**.
   A page without the necessary permission is rejected. Accept the invitation in
   a private browser and verify the destination. Edit access to change it, then
   sign out/in. If access is later revoked, login uses the first accessible page.
   Clearing direct permission overrides restores role defaults, not explicit denies.
4. In **Teams** (Owner-only), create/edit a team, select active users, save and
   reopen it to verify membership. Team lead visibility still uses explicit
   Own/Team/All scopes.

Automated backend and browser checks use a disposable PostgreSQL database:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\Run-PostgresTests.py --browser
```
