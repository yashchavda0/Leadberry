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

- Separate Platform Admin console for organization subscriptions, user limits,
  access suspension, export-only periods, confirmed password resets and audit history.
- Organization onboarding, protected Owner, login/logout, sessions and invitations.
- Custom roles, page/action permissions, membership overrides and team management.
- Centralized User management with Users, Teams, Roles and Permissions tabs,
  automatic reporting levels, grouped Select all/Clear and per-user landing pages.
- Scoped PostgreSQL leads: creation/editing, tags, simple custom fields, contact
  redaction, indexed filters/search, cursor pagination, archive/restore and version conflicts.
- Follow-up workspace with a scoped queue, completion, rescheduling and per-lead history.
- Server-to-server website lead intake with revocable keys, idempotent submissions
  and optional source-to-team round-robin assignment.
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
Run only platform-administration integration and route-contract tests with:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\Run-PostgresTests.py --platform
```

Platform operators sign in at `/platform/login`; provisioning is an explicit
database operation documented in [local setup](docs/DOCKER-SETUP.md). There is no
operator signup or customer-navigation link.

### Follow-ups

After upgrading the database to the latest Alembic revision, open **Follow-ups**
from the sidebar. Existing scheduled dates on active leads become open tasks;
archived leads are excluded until restored. Scheduling through lead creation,
editing or status changes remains supported. A lead has at most one open task.
Completing or cancelling a task clears its next follow-up date without changing
its lead status; rescheduling changes that date. Archiving cancels the open task,
and restoring a lead with a retained follow-up date creates a new task.

The queue uses existing lead visibility and permissions. Date filters use the
organization timezone; the reschedule input uses the browser's local timezone.
Task notes require contact-data permission. Completed counts in reports use
recorded task completions by the task's assignee and are available only from this
feature's introduction; earlier status changes are not treated as completions.
No email, SMS or push reminders are sent.

### Response Activity And Manager Reports

On a lead's **Timeline** tab, users with `leads.edit` can record a call, email,
meeting or other activity with an outcome. Activities use server log time and
are attributed to the acting member. The `connected` outcome is self-reported;
it does not verify that a call connected or an email was delivered. Optional notes
are visible only with `leads.pii.view`. Activities are separate from status changes
and follow-up completions.

The dashboard and **Lead reports** distinguish logged activities and connected
outcomes from status transitions. First-activity and first-connected times are
measured from lead receipt for the selected cohort; historical records before
this feature are not backfilled. Source conversion uses leads received in the
range and their current status, so recent cohorts may not have matured. Excel
reports include separate **Activities by user** and **Source conversion** sheets.

### Website Intake And Assignment

Open **Lead intake** to issue or revoke website API keys and configure assignment
for Website API, IndiaMART or TradeIndia. A key is displayed only once; store it
in the website's server-side secret manager, never in browser code or a URL.
Managing keys requires `api_keys.manage`, `leads.create`, `leads.pii.view` and
organization-wide visibility. A key stops working if its issuer is disabled or
loses any of those permissions or organization-wide visibility.

Send an HTTPS `POST /api/v1/intake/leads` from a trusted server with
`Authorization: Bearer <key>`, a stable `Idempotency-Key` (1-128 letters,
digits, `.`, `_`, `:` or `-`), and a JSON object with `name` and optional
`company`, `phone`, `email`, `city`, `state`, `product` and `enquiry` fields.
The endpoint rejects requests carrying an `Origin` header. Apply your own form
validation and abuse controls on the website; a browser cannot safely hold the key.
The key is limited to 60 successful requests per minute in addition to the API's
IP limits. A new enquiry returns 201 and its lead ID; retrying the same key and
payload returns 200 with the same ID. Reusing an idempotency key with different
content returns 409. Default-status required fields still apply. The intake
request does not establish marketing consent.

Assignment rules require `assignment_rules.manage` and organization-wide
visibility. Preview shows the next eligible active team member without consuming
their turn. A new lead is assigned round-robin only to an active member with
`leads.view`; if the team is inactive or nobody is eligible, it is unassigned.
Rules apply to new website and marketplace leads, including history imports;
existing leads and provider retries are not reassigned. Manual assignment remains
available. Website intake applies default-status validation and tags, while source
assignment takes precedence over status-based auto-assignment. Marketplace worker
processes must be restarted after updating their code.

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
  no status change in seven days. The handling-quality panel reports status
  update time separately from explicitly logged activities. Activity response
  metrics begin with the activity feature launch and are not inferred from old
  status history. "Connected" is the actor-recorded outcome, not provider-verified
  delivery. Source conversion is current Won leads divided by leads received in
  the selected cohort, not recognized revenue. Calls, emails and meetings remain
  manual activity records; revenue and structured loss reasons are not tracked.
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
