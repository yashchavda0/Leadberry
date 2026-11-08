# Marketplace integration release

Contract research: 6 November 2026. This is a phased development release, not a
claim that every catalog entry can ingest leads or that production deployment is ready.

## Implemented

- Provider catalog with separate configuration and adapter availability.
- Organization-scoped named accounts, cursor pagination, optimistic edits,
  credential replacement, connection tests, activation, pause and retirement.
- IndiaMART CRM-key pull adapter and an explicit-organization background worker.
- TradeIndia inquiry pull adapter (User ID, Profile ID, API key) using the
  documented `my_inquiry.html` endpoint. A second account is blocked until
  upstream multi-account constraints are verified.
- Write-only credentials, tenant/account/version-bound AES-256-GCM encryption
  with a random data key wrapped using RSA-OAEP-SHA256. The API holds only the
  public wrapping key; the worker alone has the private key. API database grants
  prohibit selecting the encrypted credential column or key fingerprint.
- Durable sync runs, shared upstream-key rate reservations, expiring/fenced worker
  leases, transactional lead insertion and checkpoint commit, source-ID dedupe,
  safe history/errors, and cancellation after account edits/pause/retirement.

IndiaMART supports multiple distinct seller accounts. An identical key cannot be
connected twice in one organization. The shared high-entropy key fingerprint rate
bucket also prevents parallel organizations/workers exceeding the same key's limit.
Separate subscriptions and provider entitlements remain the account owner's responsibility.

## Provider Contracts

| Provider                      | Authentication / delivery                                                                                      | Current gate                                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| IndiaMART                     | API key and a CRM-local Form name; key in server-only pull query                                               | Development adapter; validate entitlement and sanitized real success/error fixtures before production                    |
| TradeIndia                    | User ID, Profile ID, API key; GET `my_inquiry.html` with `from_date`/`to_date` (IST dates), `limit`, `page_no` | Pull adapter; keep the key server-only and rotate any key shared in chat or screenshots. Test connection before Activate |
| Meta Lead Ads                 | Page OAuth permissions; signed leadgen event followed by lead retrieval                                        | OAuth, app review and webhook implementation pending; no generic API-key field                                           |
| Shopify                       | Store OAuth, scoped GraphQL retrieval and raw-body HMAC webhooks                                               | App/permissions and adapter pending; customers and orders must become separate leads                                     |
| Google Forms                  | Authorized installable Apps Script submission bridge                                                           | Scoped intake token and stable response-ID implementation pending                                                        |
| Website/API                   | Our versioned scoped machine-key API                                                                           | Intake/key-issue/revocation implementation pending                                                                       |
| Custom forms                  | Authenticated server intake; consent and abuse controls                                                        | Intake implementation pending; no public-browser machine keys                                                            |
| JustDial                      | Provider-configured posting URL described by Cronberry                                                         | Payload, sender authentication, stable IDs and ACK/retry contract required                                               |
| Sulekha, 99acres, MagicBricks | Not verified                                                                                                   | Provider documentation, permitted access and fixtures required                                                           |
| IVR / MyTelly                 | Vendor-specific call events; MyTelly describes JSON posting                                                    | Vendor identity, source call IDs, authentication and ACK/retry contract required                                         |

Unsupported providers/actions are not enabled by marketing descriptions. No OAuth
provider passwords, Cronberry login credentials, Firebase settings, or static
Basic-auth example credentials are collected/copied.

### IndiaMART

Endpoint: `https://mapi.indiamart.com/wservce/crm/crmListing/v2/`.
GET query: `glusr_crm_key`, explicit `start_time` and `end_time` formatted in IST.
Setup requires only **API key** and **Form name**. The registered mobile number is
used by IndiaMART's seller-account/key-generation workflow, not by the pull request,
and is not collected by the CRM. Older saved mobile metadata remains compatible.
Form name is stored as the connection's name, shown alongside its leads, and used
by the connection's **View leads** link. Provider identity remains `indiamart` so
renaming a form does not break deduplication or provider-level reports.

The parser expects `CODE=200`, `STATUS=SUCCESS`, `TOTAL_RECORDS`, and the `RESPONSE`
list. Empty successful responses are accepted. Lead identity is `UNIQUE_QUERY_ID`,
scoped by organization and integration. `QUERY_TIME` is interpreted in IST and
retained as `source_query_time`; CRM `received_at` remains our intake timestamp.
Error messages/raw payloads and credential-bearing request URLs are never logged.
Malformed/incomplete responses fail the whole run without advancing its checkpoint.

Minimum spacing is five minutes per key. Each window is at most seven days, with
a five-minute overlap. A new account starts from the preceding day; a successful
test does not ingest or advance that watermark. Larger catch-up proceeds in
seven-day windows, never silently skipping backlog. Data older than 365 days
requires an explicit recovery decision. Provider documentation states keys expire
after seven unused days or regeneration; reconnect/rotate then test again.

Leads are attributed to the configuring member and arrive unassigned in the default
lead status, visible to every user with lead access. Connections no longer have a
default assignee; saving a connection clears any legacy assignee.
Retries preserve manually edited lead fields rather than overwriting them.
The creator must remain active and retain `marketplace.manage`; otherwise work
is cancelled/not claimed. Custom mapping/assignment editors, arbitrary historical
backfill controls and replay are not part of this slice.

Provider failures stop automatic sync and require a successful test and activation.
Expired leases recover queued work; transient provider failures are visible and
manually recoverable, not silently retried without an operator-visible error.
Request timeout is 20 seconds, body limit 4 MiB, redirects/environment proxies
disabled, and the outbound URL is fixed. Push is not enabled because its real
wire payload and acceptable sender-authentication scheme need verification.

## Local Setup

Use the existing PostgreSQL Compose services. Install updated backend requirements
and frontend dependencies first. From the workspace root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
npm.cmd --prefix .\frontend install
.\backend\.venv\Scripts\python.exe .\scripts\Invoke-LocalBackend.py migrate
.\backend\.venv\Scripts\python.exe .\scripts\Invoke-LocalBackend.py keys
.\backend\.venv\Scripts\python.exe .\scripts\Invoke-LocalBackend.py run
```

The native Python launcher is available when PowerShell script execution is
disabled. Existing PowerShell launch actions also include `MarketplaceKeys`
`--organization` is the `organization_id` from authenticated `GET /api/v1/auth/me`.
Migration creates no marketplace secrets: the worker uses the shared local database
password and its `crm_worker` role, which migration `0006_database_grants` restricts.
Files are under `.docker-secrets`: `postgres_password`, `marketplace-public.pem`,
`marketplace-private.pem`. Restrict the private key's Windows ACL to the worker
identity; `chmod` alone does not establish Windows ACL isolation. Do not put the
private key in the API environment or package any secrets with application files.
Back up private wrapping keys securely or encrypted accounts become unrecoverable.
The development backend can load the generated public key from `.docker-secrets`
without another API server or an environment change. `MARKETPLACE_PUBLIC_KEY_FILE`
remains available for an explicit path; test/production do not use the development fallback.

Open Marketplace and add an account; saving automatically queues a connection test.
The connector worker must be running for tests and syncs to leave `queued`. The
Marketplace page shows **Connector running/offline** from the worker heartbeat.

`Invoke-LocalBackend.py run` starts the API and the worker together (separate process
and `crm_worker` database role; pass `--no-worker` to skip). When the API is started
with uvicorn directly, run the worker in another terminal:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\Invoke-LocalBackend.py worker
```

Without `--organization` the worker serves every organization (it reads only
organization IDs from `crm.organization_directory`; tenant data stays behind RLS).
`--organization UUID` limits it to one tenant and `--once` runs a single pass.
Activate after a successful test; active connections sync automatically
(IndiaMART and TradeIndia every five minutes; the same spacing applies
between any two runs with one key, including tests). TradeIndia allows 5 requests
per 5 minutes and answers excess calls with HTTP 403 "Rate limit exceed", blocking
the key for 15 minutes: a run uses at most 5 pages, and a rate-limit response is
recorded as `provider_rate_limited`, keeps the connection verified/active and
pauses that key for 15 minutes before retrying automatically. Rate limits,
`provider_unavailable` and `provider_timeout` are transient; only rejected keys or
invalid payloads move a connection to `error`.

Queue guarantees: the worker only picks runs that may start now, so a throttled
key never blocks other accounts; up to 8 runs execute concurrently; provider work
is cut off after 5 minutes (`provider_timeout`) while the lease lasts 10 minutes,
so an expired lease only means a crashed worker and the run is re-queued; any
unexpected error fails the run (`connector_internal_error`) instead of stopping
the worker; the worker waits for the database instead of exiting on startup.

The API never returns stored keys. Connections show a masked hint (last four
characters of keys of 12+ characters) saved at entry time. Repeated test/sync
requests while a run is pending are ignored instead of failing.

Production file-based encryption is intentionally disabled. A managed wrapping-key
service, workload identity, key rotation, provider-authorized smoke tests and the
remaining operational controls are release prerequisites, not insecure fallbacks.

## Verification

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\Run-PostgresTests.py --marketplace --browser
```

This creates/removes only a uniquely named test database, uses temporary wrapping
keys and fake credentials, exercises worker ingestion with an HTTP mock, and runs
desktop/mobile Playwright workflows. It does not call real providers. Browser
installation is required. Complete results are retained in frontend test logs;
screenshots use Playwright's per-test output directory. Run the full runner
without `--marketplace` for the existing broader backend/browser suite.

## Evidence

- [Cronberry integration guide](https://www.cronberry.com/integration.html): written setup flows and screenshot references; no current authenticated UI session was reviewed.
- [IndiaMART pull contract](https://help.indiamart.com/knowledge-base/lms-crm-integration-v2/).
- [IndiaMART push contract](https://help.indiamart.com/knowledge-base/integration-of-indiamarts-lead-manager-crm-push-api-with-third-party-crms-real-time-push-of-leads/).
- [Meta lead retrieval](https://developers.facebook.com/docs/marketing-api/guides/lead-ads/retrieving/).
- [Meta webhook verification](https://developers.facebook.com/docs/graph-api/webhooks/getting-started).
- [Shopify authorization](https://shopify.dev/docs/apps/build/authentication-authorization) and [webhook verification](https://shopify.dev/docs/apps/build/webhooks/verify-deliveries).
- [Google submission triggers](https://developers.google.com/apps-script/guides/triggers/installable) and [submission event data](https://developers.google.com/apps-script/guides/triggers/events).

Provider tests use synthetic documented-envelope fixtures. Sanitized authorized
real payloads and account constraints are still needed for adapter certification.
