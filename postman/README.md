# CRM Postman Collections

## All Backend APIs

- `CRM-All-APIs.postman_collection.json`: all 59 operations generated from the FastAPI OpenAPI schema.
- `CRM-Local.postman_environment.json`: local API URL, CSRF token, UUID placeholders and common values.

Import the collection and environment, select `CRM Local - All APIs`, then send requests individually. Start with `Authentication > POST /api/v1/auth/login` or onboarding. Postman keeps the `crm_session` cookie automatically, while the test script stores the returned `csrf_token` in the environment as `csrfToken`.

For protected write requests, enable the disabled `X-CSRF-Token` header. Replace the dummy UUID variables with IDs returned by your create/list requests. Dummy JSON bodies are examples and must be changed to valid tenant data before sending.

## End-to-End Workflow

- `CRM-End-to-End-Workflow.postman_collection.json`: ordered, stateful execution of all 60 backend operations.
- `CRM-Workflow.postman_environment.json`: generated credentials and placeholders populated by test scripts.

Import both workflow files, select `CRM Workflow - Local`, then run the collection once in saved order. The first request generates a unique organization slug and emails. Onboarding stores the owner session/CSRF token; invitation creation stores the invitation token; acceptance switches to the invited member session; the collection then logs the owner back in before protected configuration work.

The workflow automatically carries organization, membership, role, team, status, custom-field, lead, marketplace, and backfill IDs, plus optimistic lead/account row versions. It also reuses the same API operations where a lifecycle requires an additional action, such as member deactivation/reactivation and restoring the owner session after accepting an invite.

Marketplace account setup uses a valid encrypted-account request with an intentionally dummy IndiaMART key. The endpoint executes and queues work when local credential encryption is configured. If the provider key service is unavailable, the collection jumps to the session lifecycle stage with an expected `503`; real provider synchronization requires replacing the dummy key with an authorized key. External provider verification is never simulated as successful.

## Automated Security Tests

- `CRM-DDoS-Protection.postman_collection.json`: repeated flood, request-size and brute-force checks.

The security collection should be run with Collection Runner iterations set to 1 because its requests loop internally. Redis flood counters last 60 seconds and PostgreSQL login counters last 15 minutes.

## Regenerate

From the project root, export the current OpenAPI schema and regenerate the collection:

```powershell
& '.\backend\.venv\Scripts\python.exe' -c "import sys,json; sys.path.insert(0,'backend'); from app.main import create_app; open('postman/openapi.generated.json','w',encoding='utf-8').write(json.dumps(create_app().openapi(),indent=2))"
& '.\backend\.venv\Scripts\python.exe' scripts/Generate-PostmanCollection.py
```

Use only against local or explicitly authorized environments. Security tests intentionally generate repeated invalid requests.
