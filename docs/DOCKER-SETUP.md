# Local setup

Docker runs **PostgreSQL and Redis only**. The backend and frontend run on the host from source.

## Tech stack

| Part             | Technology                                 | Location                                                          |
| ---------------- | ------------------------------------------ | ----------------------------------------------------------------- |
| Backend API      | FastAPI, SQLAlchemy, Alembic (Python 3.13) | [backend/](../backend/)                                           |
| Frontend         | Next.js (npm)                              | [frontend/](../frontend/)                                         |
| Database         | PostgreSQL 17                              | [compose.yaml](../compose.yaml)                                   |
| Cache / queue    | Redis 7 (provisioned, not used yet)        | [compose.yaml](../compose.yaml)                                   |
| Infra            | Docker Desktop (Linux containers)          | [compose.yaml](../compose.yaml)                                   |
| Initial DB setup | Role init script                           | [docker/postgres/initialize.sh](../docker/postgres/initialize.sh) |

## Ports and connections

| Service     | Address                 | Database / user                                                                 | Password                                                  |
| ----------- | ----------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------- |
| PostgreSQL  | `127.0.0.1:55432`       | database `leadberry`; users `crm_migrator`, `crm_api`, `crm_auth`, `crm_worker`, `crm_platform_provisioner` | `.docker-secrets/postgres_password` (local development only) |
| Redis       | `127.0.0.1:6379`        | no username                                                                     | `.docker-secrets/redis_password`                          |
| Backend API | `http://localhost:8000` | docs at `/api/v1/docs`                                                          | none                                                      |
| Frontend    | `http://localhost:3000` |                                                                                 | none                                                      |

`crm_migrator` runs migrations only. The API uses `crm_api`.

## Where the dependencies are

- Infra definitions: [compose.yaml](../compose.yaml)
- Generated secrets (git-ignored): `.docker-secrets/` (`postgres_password`, `redis_password`)
- Backend Python packages: [backend/requirements-dev.txt](../backend/requirements-dev.txt), virtualenv at `backend/.venv`
- Frontend packages: [frontend/package.json](../frontend/package.json), lock file `frontend/package-lock.json`
- Backend settings are built by [scripts/Invoke-LocalBackend.ps1](../scripts/Invoke-LocalBackend.ps1); do not put DB URLs in `backend/.env`

## One-time setup

Run from the project root in PowerShell.

```powershell
# Create secrets (skips existing values)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Initialize-DockerSecrets.ps1

# Backend dependencies
Set-Location .\backend
python -m venv .venv                      # skip if .venv exists
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location ..

# Frontend dependencies
Set-Location .\frontend
npm.cmd ci
Set-Location ..

# Marketplace credential keys (once; refuses to overwrite existing keys)
backend\.venv\Scripts\python.exe scripts\Invoke-LocalBackend.py keys
```

## Start everything (end to end)

Run each block in a separate terminal from the project root.

```powershell
# 1. Infrastructure (Docker Desktop must be running)
docker compose up -d --wait

# 2. Migrations (once after setup and after pulling new migrations)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-LocalBackend.ps1 -Action Migrate

# 3. Backend API on http://localhost:8000 (run from the backend folder)
#    No env vars needed: the app reads .docker-secrets/postgres_password itself.
Set-Location .\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --loop app.core.event_loop:selector_event_loop --reload
Set-Location ..

# 4. Marketplace connector worker (keep it running; serves every organization)
#    Tests and lead syncs stay "queued" until this is running.
backend\.venv\Scripts\python.exe scripts\Invoke-LocalBackend.py worker
#    PowerShell alternative:
#    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-LocalBackend.ps1 -Action Worker
#    Optional: --organization <uuid> (or -OrganizationId) limits it to one organization; --once runs a single pass.

# 5. Frontend on http://localhost:3000
Set-Location .\frontend
npm.cmd run dev
```

Then open http://localhost:3000/onboarding to create a workspace, or
http://localhost:3000/login to sign in.

## Platform operator bootstrap

After upgrading to the latest Alembic revision, create the restricted local
provisioning role. This works with existing Docker volumes and does not delete
database data:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\Initialize-PlatformProvisioner.py
```

Provision a dedicated operator identity. The command prompts for a strong
password if the account does not already have one; existing customer identities
cannot be promoted as platform operators.

```powershell
$secret = (Get-Content .\.docker-secrets\postgres_password -Raw).Trim()
$encoded = [uri]::EscapeDataString($secret)
$env:PLATFORM_PROVISION_DATABASE_URL = "postgresql+psycopg://crm_platform_provisioner:$encoded@127.0.0.1:55432/leadberry"
$env:APP_ENVIRONMENT = 'development'
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.modules.identity.provision_operator --email platform-admin@example.com --name "Platform Admin" --access-level administrator
Set-Location ..
Remove-Item Env:PLATFORM_PROVISION_DATABASE_URL
Remove-Item Env:APP_ENVIRONMENT
```

Then sign in at http://localhost:3000/platform/login. Production deployments
must create the same least-privilege database role through their DB provisioning
process, set `PLATFORM_PROVISION_DATABASE_URL` only for the one-time bootstrap,
and remove it afterward. The application does not expose a public operator
signup page.

Health checks:

- http://localhost:8000/api/v1/health/live (should return 200)
- http://localhost:8000/api/v1/health/ready (returns 200 when migrations match the code)

## Stop everything

```powershell
# Stop the backend and frontend terminals with Ctrl+C
docker compose down          # keeps data
```

Use `docker compose down -v` only when you want to delete all local data.

## Troubleshooting

- **503 with `database_operation_unavailable sqlstate=None` on API calls:** the backend could not connect as `crm_api`/`crm_auth`. Check that `.docker-secrets/postgres_password` exists and that `docker compose ps` shows postgres healthy. Keep `--reload` on the command.
- **Backend returns 503 on `/health/ready`:** run the Migrate step. The code expects the head revision in `SCHEMA_REVISION` in [backend/app/core/database.py](../backend/app/core/database.py).
- **Port 8000 or 3000 already in use:** stop the process holding the port, or restart Windows. Check with `netstat -ano | Select-String ':8000 '`.
- **Role or password errors on a fresh start:** the roles are created only when the PostgreSQL volume is first initialized. If the volume predates the current secrets, run `docker compose down -v` and start again. This deletes local data.
- **Backend logs:** printed in the terminal running uvicorn. Every request shows as `INFO: ... "METHOD /path" status`. App events also show with a timestamp:
  - `audit action=... org_id=... actor=... entity_id=...` for every write (for example `organization.created`, `session.created`)
  - `access_rejected code=...` for failed logins and other denied access (401/403)
  - `request_validation_rejected [(loc, type)]` for bad request bodies (422), with field names and error types only, never values
- **Audit trail (database):** `docker compose exec postgres psql -U postgres -d leadberry -c "SELECT action, entity_type, occurred_at FROM crm.audit_logs ORDER BY occurred_at DESC LIMIT 20;"`
- **Infra logs:** `docker compose logs --tail 100 postgres redis`
- **Database shell:** `docker compose exec postgres psql -U postgres -d leadberry`
- **Marketplace test/sync stays `queued`:** start the worker (step 4). The Marketplace page shows **Connector running/offline**. If you pass `--organization`, it must be the organization that owns the connection. IndiaMART also allows one request per key every 5 minutes, so a sync right after a test waits up to 5 minutes. Check jobs with `docker compose exec postgres psql -U postgres -d leadberry -c "SELECT kind, state, fetched_count, accepted_count, safe_error_code, created_at FROM crm.marketplace_sync_runs ORDER BY created_at DESC LIMIT 10;"`
- **Tests:** `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-LocalBackend.ps1 -Action Test`
