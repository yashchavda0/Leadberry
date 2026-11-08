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
test does not ingest or advance that watermark. Backlog older than one window is
moved to the history ledger (gap recovery, below), never silently skipped.
Older history is imported through the history ledger described below.
Provider documentation states keys expire after seven unused days or regeneration;
reconnect/rotate then test again.

Response codes (official Pull API documentation, December 2025): `204` with
"no leads" is an empty success whatever its `STATUS`; `204` "Leads before X will
be available after 24 hours" (new key) is `provider_history_not_ready` and the
period is retried after X + 24 h; `400` "last 365 days" is `provider_history_expired`;
`429` (more than one hit in 5 minutes, or more than 5 hits a minute, which blocks the
key for 15 minutes) is `provider_rate_limited` with a 15-minute cooldown; `500` is
`provider_unavailable`; more than 10,000 records is `provider_payload_too_large`.

Leads are attributed to the configuring member and arrive unassigned in the default
lead status, visible to every user with lead access. Connections no longer have a
default assignee; saving a connection clears any legacy assignee.
Retries preserve manually edited lead fields rather than overwriting them.
The creator must remain active and retain `marketplace.manage`; otherwise work
is cancelled/not claimed. Custom mapping/assignment editors and replay are not part
of this slice.

## Sync schedule and history import

Each connection has a live sync interval: 5, 10, 15 (default, recommended by
IndiaMART), 20, 30 or 60 minutes, changed with `PUT /accounts/{id}/schedule`
without re-testing. Migration `0010_marketplace_schedule` moved existing
connections to 15 minutes.

Every API key gets one request slot per 5 minutes plus a 15-second guard (315 s),
shared across organizations through `marketplace_rate_limits`. Each free slot goes
to, in order: a queued connection test or manual sync, a due live sync
(`next_live_at`), then a history window, but only when the next live sync is at
least one slot minus 90 seconds away. Live sync therefore starts at most about
90 seconds late. Import runs are created directly as running, so they never sit in
the queue ahead of live sync.

| Interval | Import slots per cycle | Windows per hour | IndiaMART 365 days (53 windows) | TradeIndia 365 days (365 windows) |
| -------- | ---------------------- | ---------------- | ------------------------------- | --------------------------------- |
| 5 min    | 0 (import paused)      | 0                | -                               | -                                 |
| 10 min   | 1                      | 6                | about 9 h                       | about 61 h                        |
| 15 min   | 2                      | 8                | about 6.6 h                     | about 46 h                        |
| 20 min   | 3                      | 9                | about 5.9 h                     | about 41 h                        |
| 30 min   | 5                      | 10               | about 5.3 h                     | about 37 h                        |

History import (`marketplace_backfills` job + `marketplace_backfill_windows` ledger)
is started by the setup checkbox or `POST /accounts/{id}/backfills` with an optional
`from_date`/`to_date` (IST days). The range is clamped to the provider's history
(365 days for both) and split into provider windows: IndiaMART up to 7 days,
TradeIndia exactly one IST day, because TradeIndia answers ranges longer than one
day with HTTP 400 "greater than 24 hours not allowed for inquiries" (verified with a
real key on 8 November 2026, which also returned inquiries for a day 190 days back).
Windows are processed newest first. One active import
per connection. Each window keeps its state, attempts, next attempt time, hold reason
and, for TradeIndia, the next page, so a busy day continues in the next slot
instead of exceeding 5 requests. Too-large windows are split in halves. Transient
failures retry with backoff (5 min doubling to 2 h, five attempts) before the window
is marked failed; `.../backfills/{bid}/retry` re-queues failed windows and
`.../cancel` stops the import. TradeIndia imports stop after 30 empty days in
a row. Replacing the key or deleting the connection cancels the import; pausing
only holds it. Imported leads keep the provider enquiry time as `received_at` so
they do not count as today's leads; `created_at` records the import time. Imports
never move the live watermark.

Gap recovery: when a live sync finds its watermark more than one window behind
(IndiaMART 7 days; TradeIndia anything before yesterday), for example after a long
pause or worker outage, it fetches only the newest window and moves the watermark
forward. TradeIndia live requests never cross an IST midnight: yesterday's tail is
fetched first and today follows at the next slot. The older missed range, clamped to the
provider's history, is added to the active history job or to a new job of kind
`gap` (migration `0011_marketplace_gap_recovery`), shown as "Recovering missed
leads". Both happen in the live run's transaction, so a failed live run records
nothing and retries. At a 5-minute interval, recovery waits for a longer interval
like any import.

Every hold is visible. Account responses carry `schedule_status.live` and
`schedule_status.history` with `state`, `reason`, `until` (and `eta`/progress for
imports); windows expose their own reason through
`GET .../backfills/{bid}/windows`. Reason codes: `waiting_key_slot`,
`shared_key_slot`, `provider_cooldown`, `provider_unavailable_retry`,
`provider_timeout_retry`, `provider_error_retry`, `history_not_ready`,
`history_expired`, `window_split_large`, `window_continues_next_slot`,
`import_paused_interval_5min`, `import_paused_account_paused`,
`import_paused_needs_test`, `import_cancelled_*`, `import_stopped_no_older_data`,
`import_completed_with_failures`, `key_expiry_risk` (IndiaMART key unused for 5 of
its 7 days), `worker_offline` and `gap_recovery`. The Marketplace page shows
them with the resume time, and queued manual requests report when they will run.

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
Activate after a successful test; active connections sync automatically on their
configured interval (default 15 minutes; the 5-minute key spacing applies between
any two requests with one key, including tests and history imports). TradeIndia allows 5 requests
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
