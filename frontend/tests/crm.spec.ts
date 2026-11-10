import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { homeFor, type Identity } from "../lib/crm";

test("marketplace provider-specific credentials, multiple accounts and responsive layout", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/onboarding");
  await page
    .getByLabel("Organization slug")
    .fill(`marketplace-${randomUUID()}`);
  await page.getByLabel("Organization name").fill("Marketplace browser test");
  await page.getByLabel("Your full name").fill("Marketplace owner");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`${randomUUID()}@example.com`);
  await page.getByLabel(/^Password/).fill(`test-password-${randomUUID()}`);
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Marketplace browser test" }),
  ).toBeVisible();
  await page.goto("/marketplace");
  await expect(
    page.getByRole("heading", { name: "Marketplace", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".marketplace-provider")).toHaveCount(12);
  const india = page.locator(".marketplace-provider").filter({
    has: page.getByRole("heading", { name: "IndiaMART", exact: true }),
  });
  await expect(
    india.getByRole("button", { name: "Add connection" }),
  ).toBeEnabled();
  await expect(
    page
      .locator(".marketplace-provider")
      .filter({ hasText: "Shopify" })
      .getByRole("button", { name: "Unavailable" }),
  ).toBeDisabled();
  await page.screenshot({
    path: testInfo.outputPath("marketplace-desktop.png"),
    fullPage: true,
  });
  for (const name of ["North sales", "South sales"]) {
    await page.getByRole("tab", { name: "Providers", exact: true }).click();
    await india.getByRole("button", { name: "Add connection" }).click();
    await page.getByLabel("Form name", { exact: true }).fill(name);
    await expect(
      page.getByLabel("Registered mobile number", { exact: true }),
    ).toHaveCount(0);
    const secret = `fake-marketplace-key-${randomUUID()}`;
    await page.getByLabel("API key", { exact: true }).fill(secret);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/marketplace/accounts") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Save account", exact: true })
      .click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    expect(await response.text()).not.toContain(secret);
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  }
  await expect(page.locator(".marketplace-account")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Settings for North sales", exact: true })
    .click();
  await expect(page.getByLabel("API key", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Form name", { exact: true })).toHaveValue(
    "North sales",
  );
  await expect(
    page.getByLabel("Registered mobile number", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  const north = page.locator(".marketplace-account").filter({
    has: page.getByRole("heading", { name: "North sales", exact: true }),
  });
  await expect(
    north.getByRole("link", { name: "View leads", exact: true }),
  ).toHaveAttribute("href", /integration_id=.+&connection=North\+sales/);
  await expect(
    north.getByRole("button", { name: "Activate", exact: true }),
  ).toHaveCount(0);
  await expect(north).toContainText("Checking");
  await expect(
    north.getByRole("button", { name: "Testing...", exact: true }),
  ).toBeDisabled();
  await expect(north.locator(".mono")).toContainText("••••");
  await north.getByRole("button", { name: "History", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Connection history", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".marketplace-run")).toContainText("queued");
  await page
    .getByRole("button", { name: "Close connection history", exact: true })
    .click();
  await expect(page.locator(".marketplace-account")).toHaveCount(2);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: testInfo.outputPath("marketplace-accounts-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("tab", { name: "Providers", exact: true }).click();
  const trade = page.locator(".marketplace-provider").filter({
    has: page.getByRole("heading", { name: "TradeIndia", exact: true }),
  });
  await trade.getByRole("button", { name: "Add connection" }).click();
  await expect(page.getByLabel("User ID", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Profile ID", { exact: true })).toBeVisible();
  await expect(page.getByLabel("API key", { exact: true })).toBeVisible();
  await expect(page.getByLabel("CRM key", { exact: true })).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("marketplace-setup-mobile.png"),
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("marketplace sync schedule and history import explain every hold", async ({
  page,
}) => {
  page.on("pageerror", (error) => {
    throw error;
  });
  const accountId = randomUUID();
  const backfillId = randomUUID();
  const now = Date.now();
  const at = (minutes: number) => new Date(now + minutes * 60000).toISOString();
  let interval = 900;
  let scheduleBody: unknown = null;
  const account = () => ({
    id: accountId,
    provider_code: "indiamart",
    name: "North sales",
    status: "active",
    config: {},
    credential_hint: { crm_key: "••••••••1234" },
    credential_version: 1,
    verified_version: 1,
    row_version: 4,
    last_success_at: at(-3),
    last_received_at: at(-60),
    safe_error_code: null,
    sync_interval_seconds: interval,
    last_run_kind: "sync",
    last_run_state: "completed",
    last_run_error: null,
    last_run_at: at(-3),
    created_at: at(-600),
    updated_at: at(-3),
    schedule_status: {
      live: {
        state: "held",
        reason: "provider_cooldown",
        until: at(12),
        next_request_at: at(12),
      },
      history: {
        id: backfillId,
        state: "active",
        range_start: at(-525600),
        range_end: at(-600),
        windows_total: 53,
        windows_done: 2,
        windows_failed: 0,
        windows_pending: 51,
        fetched_count: 9,
        accepted_count: 7,
        created_at: at(-600),
        finished_at: null,
        reason: "history_not_ready",
        until: at(600),
        eta: at(1000),
      },
    },
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.slice("/api/v1".length);
    const fulfill = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path === "/auth/me")
      return fulfill({
        organization_id: randomUUID(),
        membership_id: randomUUID(),
        user_id: randomUUID(),
        is_owner: true,
        permissions: ["marketplace.view", "marketplace.manage"],
        data_scope: "all",
        landing_page: "/marketplace",
      });
    if (path === "/organizations/me")
      return fulfill({
        id: randomUUID(),
        slug: "schedule-ui",
        name: "Schedule UI",
        timezone: "Asia/Kolkata",
        status: "active",
      });
    if (path === "/marketplace/providers")
      return fulfill({
        data: [
          {
            code: "indiamart",
            name: "IndiaMART",
            category: "marketplace",
            method: "CRM key / Pull API",
            setup: true,
            adapter: true,
            multiple_accounts: true,
            documentation_url: null,
            note: "",
            fields: [
              {
                key: "crm_key",
                label: "API key",
                secret: true,
                required: true,
              },
            ],
            allowed_intervals: [300, 600, 900, 1200, 1800, 3600],
            default_interval_seconds: 900,
            history_days: 365,
          },
        ],
        credential_storage_ready: true,
        worker_online: true,
        worker_last_seen_at: at(0),
      });
    if (path === "/marketplace/accounts")
      return fulfill({ data: [account()], next_cursor: null });
    if (path === `/marketplace/accounts/${accountId}/schedule`) {
      scheduleBody = request.postDataJSON();
      interval = 1800;
      return fulfill(account());
    }
    if (
      path ===
      `/marketplace/accounts/${accountId}/backfills/${backfillId}/windows`
    )
      return fulfill({
        data: [
          {
            id: randomUUID(),
            window_start: at(-10680),
            window_end: at(-600),
            state: "completed",
            attempts: 0,
            next_attempt_at: at(-600),
            next_page: 1,
            hold_reason: null,
            safe_error_code: null,
            fetched_count: 9,
            accepted_count: 7,
            updated_at: at(-500),
          },
          {
            id: randomUUID(),
            window_start: at(-20760),
            window_end: at(-10680),
            state: "pending",
            attempts: 0,
            next_attempt_at: at(600),
            next_page: 1,
            hold_reason: "history_not_ready",
            safe_error_code: "provider_history_not_ready",
            fetched_count: 0,
            accepted_count: 0,
            updated_at: at(-400),
          },
        ],
        next_cursor: null,
      });
    return fulfill({ code: "not_found" }, 404);
  });

  await page.goto("/marketplace");
  await page.getByRole("tab", { name: /Connected accounts/ }).click();
  const row = page
    .locator(".account-row")
    .filter({ has: page.getByRole("heading", { name: "North sales" }) });
  await expect(row).toContainText("every 15 min");
  await expect(row.locator('[data-reason="provider_cooldown"]')).toContainText(
    "IndiaMART temporarily blocked this key",
  );
  await expect(row.locator('[data-reason="provider_cooldown"]')).toContainText(
    /in 1[12] min/,
  );
  await expect(row.locator('[data-reason="history_not_ready"]')).toContainText(
    "24 hours after the key was generated",
  );
  await expect(
    row.getByRole("progressbar", { name: "History import progress" }),
  ).toHaveAttribute("aria-valuenow", "4");
  await expect(
    row.getByRole("button", { name: "Import past leads for North sales" }),
  ).toBeDisabled();

  await row.getByRole("button", { name: "Import details" }).click();
  const details = page.getByRole("dialog");
  await expect(details.getByText("Imported", { exact: true })).toBeVisible();
  await expect(
    details.locator('[data-reason="history_not_ready"]'),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Close history import details" })
    .click();

  await row
    .getByRole("button", { name: "Sync schedule for North sales" })
    .click();
  await page.getByLabel("Sync every").selectOption("300");
  await expect(page.getByRole("dialog")).toContainText(
    "history import pauses at this interval",
  );
  await page.getByLabel("Sync every").selectOption("1800");
  await page.getByRole("button", { name: "Save schedule" }).click();
  expect(scheduleBody).toEqual({ sync_interval_seconds: 1800 });
  await expect(
    page.getByText("North sales now syncs every 30 min."),
  ).toBeVisible();
  await expect(row).toContainText("every 30 min");
});

test("landing selection respects permission revocation and role-only management access", () => {
  const identity: Identity = {
    organization_id: "org",
    membership_id: "member",
    user_id: "user",
    is_owner: false,
    data_scope: "own",
    permissions: ["dashboard.view", "leads.view"],
    landing_page: "/leads",
  };
  expect(homeFor(identity)).toBe("/leads");
  expect(homeFor({ ...identity, permissions: ["dashboard.view"] })).toBe("/");
  expect(
    homeFor({ ...identity, permissions: [], landing_page: "/users" }),
  ).toBe("/account");
  expect(
    homeFor({
      ...identity,
      permissions: ["roles.view"],
      landing_page: "/users",
    }),
  ).toBe("/users");
  expect(
    homeFor({ ...identity, landing_page: "https://invalid.example" }),
  ).toBe("/");
});

test("lead table preferences and typed required fields work in the manual lead form", async ({
  page,
}, testInfo) => {
  const memberId = randomUUID();
  const leadId = randomUUID();
  let columns = [
    "name",
    "company",
    "email",
    "phone",
    "status_changed_at",
    "status",
    "source_name",
    "source_record_id",
  ];
  let created: Record<string, unknown> | null = null;
  let exportedQuery = "";
  let archiveBody: unknown = null;
  let statusChange: { status_id: string; note: string; next_follow_up_at?: string | null; row_version: number } | null = null;
  let currentStatusId = "status-new";
  let currentStatusName = "New";
  let currentFollowUp: string | null = null;
  let rowVersion = 1;
  let statusHistory: { id: string; from_status: string; to_status: string; note: string; actor_name: string; created_at: string }[] = [];
  page.on("pageerror", (error) => {
    throw error;
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.slice("/api/v1".length);
    const method = request.method();
    const fulfill = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path === "/auth/me")
      return fulfill({
        organization_id: randomUUID(),
        membership_id: memberId,
        user_id: randomUUID(),
        is_owner: true,
        permissions: [
          "dashboard.view",
          "leads.view",
          "leads.create",
          "leads.edit",
          "leads.assign",
          "leads.archive",
          "leads.restore",
          "leads.export",
          "leads.pii.view",
        ],
        data_scope: "all",
        landing_page: "/leads",
      });
    if (path === "/organizations/me")
      return fulfill({
        id: randomUUID(),
        slug: "lead-ui-test",
        name: "Lead UI test",
        timezone: "Asia/Kolkata",
        status: "active",
      });
    if (path === "/leads/options")
      return fulfill({
        statuses: [
          {
            id: "status-new",
            name: "New",
            color: "#15803d",
            type: "new",
            is_default: true,
            required_fields: ["phone", "budget", "consent", "segment"],
          },
          {
            id: "status-qualified",
            name: "Qualified",
            color: "#7c3aed",
            type: "working",
            required_fields: [],
          },
          {
            id: "status-follow-up",
            name: "Follow-up scheduled",
            color: "#d97706",
            type: "pending",
            required_fields: ["next_follow_up_at"],
          },
        ],
        custom_fields: [
          {
            field_key: "budget",
            label: "Budget",
            field_type: "number",
            options: [],
            position: 0,
            is_active: true,
          },
          {
            field_key: "consent",
            label: "Consent",
            field_type: "boolean",
            options: [],
            position: 1,
            is_active: true,
          },
          {
            field_key: "segment",
            label: "Segment",
            field_type: "select",
            options: ["Retail", "Wholesale"],
            position: 2,
            is_active: true,
          },
        ],
        sources: ["manual"],
        accounts: [],
      });
    if (path === "/leads/assignees")
      return fulfill({
        data: [{ id: memberId, display_name: "Owner" }],
        next_cursor: null,
      });
    if (path === "/teams")
      return fulfill({ data: [], next_cursor: null, total: 0 });
    if (path === "/leads/export") {
      exportedQuery = url.search;
      return route.fulfill({
        contentType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers: {
          "Content-Disposition": "attachment; filename=filtered-leads.xlsx",
        },
        body: Buffer.from("PK-test-download"),
      });
    }
    if (path === `/leads/${leadId}/archive`) {
      archiveBody = request.postDataJSON();
      return fulfill({ id: leadId });
    }
    if (path === `/leads/${leadId}/status-history` && method === "GET")
      return fulfill({ data: statusHistory });
    if (path === `/leads/${leadId}/status` && method === "POST") {
      statusChange = request.postDataJSON();
      const nextStatus = statusChange.status_id === "status-qualified" ? "Qualified" : statusChange.status_id === "status-follow-up" ? "Follow-up scheduled" : "New";
      statusHistory = [...statusHistory, {
        id: randomUUID(),
        from_status: currentStatusName,
        to_status: nextStatus,
        note: statusChange.note,
        actor_name: "Owner",
        created_at: new Date().toISOString(),
      }];
      currentStatusId = statusChange.status_id;
      currentStatusName = nextStatus;
      currentFollowUp = statusChange.next_follow_up_at || null;
      rowVersion += 1;
      return fulfill({ id: leadId, row_version: rowVersion });
    }
    if (path === "/lead-table-preferences" && method === "GET")
      return fulfill({ columns });
    if (path === "/lead-table-preferences" && method === "PUT") {
      columns = request.postDataJSON().columns;
      return fulfill({ columns });
    }
    if (path === "/leads" && method === "GET")
      return fulfill({
        data: [
          {
            id: leadId,
            name: "Example lead",
            company: "Example Co",
            phone: "123456",
            email: "buyer@example.com",
            city: "Pune",
            state: "Maharashtra",
            address: "",
            product: "Equipment",
            enquiry: "Quote request",
            source_provider: "manual",
            source_record_id: null,
            status_id: currentStatusId,
            status: currentStatusName,
            status_color: "#15803d",
            integration_id: null,
            source_account_name: null,
            status_changed_at: new Date().toISOString(),
            assigned_membership_id: memberId,
            assignee: "Owner",
            team_id: null,
            tags: [],
            custom_fields: {},
            next_follow_up_at: null,
            archived_at: null,
            row_version: rowVersion,
            received_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            pii_redacted: false,
          },
        ],
        next_cursor: url.searchParams.has("after") ? null : "lead-next",
        total: 26,
      });
    if (path === "/leads" && method === "POST") {
      created = request.postDataJSON();
      return fulfill({ id: leadId }, 201);
    }
    if (path === `/leads/${leadId}` && method === "GET")
      return fulfill({
        id: leadId,
        name: "Manual lead",
        company: "Example Co",
        phone: "123456",
        email: "buyer@example.com",
        city: "Pune",
        state: "Maharashtra",
        address: "",
        product: "Equipment",
        enquiry: "Quote request",
        source_provider: "manual",
        source_record_id: null,
        status_id: currentStatusId,
        status: currentStatusName,
        status_color: "#15803d",
        integration_id: null,
        source_account_name: null,
        status_changed_at: new Date().toISOString(),
        assigned_membership_id: memberId,
        assignee: "Owner",
        team_id: null,
        tags: [],
        custom_fields: { budget: 45.5, consent: false, segment: "Retail" },
        next_follow_up_at: currentFollowUp,
        archived_at: null,
        row_version: rowVersion,
        received_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        pii_redacted: false,
      });
    return fulfill({ code: "not_found" }, 404);
  });

  await page.goto(`/leads/${leadId}`);
  await expect(page.getByRole("heading", { name: "Manual lead", exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "New status", exact: true }).click();
  await page.getByRole("option", { name: "Follow-up scheduled", exact: true }).click();
  await expect(page.getByLabel("Follow-up time")).toBeVisible();
  await page.getByLabel("Follow-up time").fill("2026-11-12T10:30");
  const expectedFollowUp = await page.locator("#lead-status-followup").evaluate((element: HTMLInputElement) => new Date(element.value).toISOString());
  await page.locator("#lead-status-note").fill("Customer requested pricing.");
  await page.getByRole("button", { name: "Update status", exact: true }).click();
  await expect(page.getByText("Lead status updated.")).toBeVisible();
  expect(statusChange).toMatchObject({
    status_id: "status-follow-up",
    note: "Customer requested pricing.",
    next_follow_up_at: expectedFollowUp,
    row_version: 1,
  });
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(page.getByText("Customer requested pricing.", { exact: true })).toBeVisible();
  currentStatusId = "status-new";
  currentStatusName = "New";
  currentFollowUp = null;
  rowVersion = 1;
  statusHistory = [];

  await page.goto("/leads");
  await expect(
    page.getByRole("columnheader", { name: "Audience ID" }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Actions" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Archive Example lead" }),
  ).toBeVisible();
  await expect(page.getByLabel("Tag", { exact: true })).not.toBeVisible();
  await page.getByLabel("Search", { exact: true }).fill("Example");
  await page.getByRole("combobox", { name: "Status", exact: true }).selectOption("status-new");
  await page.getByRole("button", { name: "Assigned to", exact: true }).click();
  await page.getByLabel("Search assigned to").fill("Owner");
  await expect
    .poll(() =>
      page.getByRole("button", { name: "Owner", exact: true }).count(),
    )
    .toBe(1);
  await page.getByRole("button", { name: "Owner", exact: true }).click();
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(
    page.getByRole("button", { name: "Remove Search filter" }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export to Excel" }).click();
  const exported = await downloadPromise;
  expect(exported.suggestedFilename()).toBe("filtered-leads.xlsx");
  expect(new URLSearchParams(exportedQuery).get("q")).toBe("Example");
  expect(new URLSearchParams(exportedQuery).get("status_id")).toBe(
    "status-new",
  );
  expect(new URLSearchParams(exportedQuery).get("assignee")).toBe(memberId);
  expect(new URLSearchParams(exportedQuery).has("limit")).toBe(false);
  await page.getByRole("button", { name: "Remove Search filter" }).click();
  await expect(page.getByLabel("Search", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await page.locator(".lead-advanced-filters > summary").click();
  await page.getByLabel("Received from").fill("2026-11-08");
  await page.getByLabel("Received through").fill("2026-11-01");
  await page.getByRole("button", { name: "Apply filters" }).click();
  expect(
    await page
      .getByLabel("Received through")
      .evaluate((element: HTMLInputElement) => element.validity.valid),
  ).toBe(false);
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await page.locator(".lead-advanced-filters > summary").click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".lead-index").first()).toHaveText("26");
  await page.getByRole("button", { name: "Previous", exact: true }).click();
  await expect(page.locator(".lead-index").first()).toHaveText("1");
  await page.getByRole("button", { name: "Archive Example lead" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Archive lead", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  expect(archiveBody).toEqual({ row_version: 1 });
  await page.getByRole("button", { name: "Columns" }).click();
  await page
    .getByRole("menuitemcheckbox", { name: "Tags", exact: true })
    .click();
  await expect(page.getByRole("columnheader", { name: "Tags" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.getByRole("columnheader", { name: "Tags" })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("leads-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: testInfo.outputPath("leads-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();

  await page.getByRole("link", { name: "New lead", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Manual lead");
  await page.getByLabel("Company", { exact: true }).fill("Example Co");
  await page.getByLabel("Phone", { exact: true }).fill("123456");
  await page.getByLabel(/^Budget/).fill("45.5");
  await page.getByLabel(/^Consent/).selectOption("false");
  await page.getByLabel(/^Segment/).selectOption("Retail");
  await page
    .getByLabel("Tags", { exact: true })
    .fill("Priority, Retail, Priority");
  await page.screenshot({
    path: testInfo.outputPath("lead-entry-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Create & add another", exact: true })
    .click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("");
  expect(created).toMatchObject({
    name: "Manual lead",
    tags: ["Priority", "Retail"],
  });
  await page.getByLabel("Name", { exact: true }).fill("Manual lead");
  await page.getByLabel("Phone", { exact: true }).fill("123456");
  await page.getByLabel(/^Budget/).fill("45.5");
  await page.getByLabel(/^Consent/).selectOption("false");
  await page.getByLabel(/^Segment/).selectOption("Retail");
  await page.getByRole("button", { name: "Create lead", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Manual lead", exact: true }),
  ).toBeVisible();
  expect(created).toMatchObject({
    assigned_membership_id: memberId,
    custom_fields: { budget: 45.5, consent: false, segment: "Retail" },
  });
});

test("owner onboarding, roles, invitations, leads, restricted member and responsive navigation", async ({
  page,
  browser,
}) => {
  const password = `test-password-${randomUUID()}`;
  const slug = `browser-${randomUUID()}`;
  const memberEmail = `${randomUUID()}@example.com`;
  const consoleErrors: string[] = [];
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.goto("/leads");
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/onboarding");
  await page.getByLabel("Organization slug").fill(slug);
  await page.getByLabel("Organization name").fill("Browser Test CRM");
  await page.getByLabel("Your full name").fill("Browser Owner");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`${randomUUID()}@example.com`);
  await page.getByLabel(/^Password/).fill(password);
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Browser Test CRM" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "User management", exact: true })
    .click();
  const managementNavigation = page.getByRole("navigation", {
    name: "User management sections",
  });
  await expect(managementNavigation.getByRole("link")).toHaveCount(4);
  await expect(
    managementNavigation.getByRole("link", { name: "Users", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    managementNavigation.getByRole("link", { name: "Roles", exact: true }),
  ).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await page.getByRole("link", { name: "Roles", exact: true }).click();
  await expect(
    managementNavigation.getByRole("link", { name: "Roles", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    managementNavigation.getByRole("link", { name: "Roles", exact: true }),
  ).toHaveCSS("border-bottom-width", "2px");
  await page.getByRole("button", { name: "+ Create role" }).click();
  await page.getByLabel("Role name").fill("Director");
  await page.getByRole("button", { name: "Save role", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "Director" }),
  ).toContainText("Parent");
  await page.getByRole("button", { name: "+ Create role" }).click();
  await page.getByLabel("Role name").fill("Restricted agent");
  await page.getByLabel("Director", { exact: true }).check();
  const leadPermissions = page.locator("fieldset").filter({
    has: page.locator(".permission-group-title").filter({ hasText: /^leads$/ }),
  });
  const headingBounds = await leadPermissions.locator("legend").boundingBox();
  const actionBounds = await leadPermissions
    .locator(".permission-group-actions")
    .boundingBox();
  expect(headingBounds).not.toBeNull();
  expect(actionBounds).not.toBeNull();
  expect(
    Math.abs(
      actionBounds!.x +
        actionBounds!.width -
        headingBounds!.x -
        headingBounds!.width,
    ),
  ).toBeLessThanOrEqual(1);
  expect(
    Math.abs(
      actionBounds!.y +
        actionBounds!.height / 2 -
        headingBounds!.y -
        headingBounds!.height / 2,
    ),
  ).toBeLessThanOrEqual(1);
  await expect(
    leadPermissions.getByRole("button", { name: "Select all", exact: true }),
  ).toHaveCSS("min-height", "26px");
  await expect(leadPermissions.getByRole("button")).toHaveCount(1);
  await page.getByLabel("leads.view", { exact: true }).check();
  await expect(leadPermissions.getByRole("button")).toHaveText("Select all");
  await leadPermissions
    .getByRole("button", { name: "Select all", exact: true })
    .click();
  await expect(page.getByLabel("leads.edit", { exact: true })).toBeChecked();
  await expect(leadPermissions.getByRole("button")).toHaveText("Clear");
  await page.getByLabel("leads.edit", { exact: true }).uncheck();
  await expect(leadPermissions.getByRole("button")).toHaveText("Select all");
  await page.getByLabel("leads.edit", { exact: true }).check();
  await leadPermissions
    .getByRole("button", { name: "Clear", exact: true })
    .click();
  await expect(leadPermissions.getByRole("button")).toHaveText("Select all");
  await expect(
    page.getByLabel("leads.edit", { exact: true }),
  ).not.toBeChecked();
  await page.getByLabel("leads.view", { exact: true }).check();
  await page.getByLabel("dashboard.view", { exact: true }).check();
  await page.getByRole("button", { name: "Save role", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "Restricted agent" }),
  ).toBeVisible();
  const agentRow = page.getByRole("row").filter({
    has: page.getByRole("cell", { name: "Restricted agent", exact: true }),
  });
  await expect(agentRow).toContainText("Child");
  await expect(
    agentRow.getByRole("cell", { name: "2", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Permissions", exact: true }).click();
  const editPermissions = page
    .getByRole("button", { name: "Edit permissions" })
    .first();
  await expect(editPermissions).toBeVisible();
  await expect(editPermissions).toHaveCSS("border-top-width", "0px");
  await expect(editPermissions.locator("svg")).toBeVisible();
  await expect(editPermissions).toHaveText("");
  await editPermissions.click();
  await expect(
    page.getByRole("heading", { name: "Edit role", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("link", { name: "Users", exact: true }).click();
  await page.getByRole("button", { name: "+ Invite user" }).click();
  await page
    .getByLabel("Display name", { exact: true })
    .fill("Restricted Member");
  await page.getByLabel("Email", { exact: true }).fill(memberEmail);
  await page.getByLabel("Restricted agent", { exact: true }).check();
  await page.getByLabel("Landing page", { exact: true }).selectOption("/leads");
  await page
    .getByRole("button", { name: "Create invitation", exact: true })
    .click();
  const token = await page.getByLabel("Private invitation token").inputValue();
  expect(token.length).toBeGreaterThan(100);
  await page.getByRole("button", { name: "Done / hide token" }).click();

  const memberContext = await browser.newContext();
  const memberPage = await memberContext.newPage();
  memberPage.on("pageerror", (error) => consoleErrors.push(error.message));
  await memberPage.goto("http://127.0.0.1:3012/accept-invite");
  await memberPage.getByLabel("Invitation token", { exact: true }).fill(token);
  await memberPage.getByLabel(/^Your password/).fill(password);
  await memberPage
    .getByRole("button", { name: "Accept invitation", exact: true })
    .click();
  await expect(memberPage).toHaveURL(/\/leads$/);
  await expect(
    memberPage.getByRole("heading", { name: "Leads", exact: true }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Teams", exact: true }).click();
  await page.getByRole("button", { name: "+ Create team" }).click();
  await page.getByLabel("Team name").fill("Sales team");
  await page.getByLabel("Restricted Member", { exact: true }).check();
  await page.getByRole("button", { name: "Save team", exact: true }).click();
  const teamRow = page.locator(".source-row").filter({ hasText: "Sales team" });
  await expect(teamRow).toBeVisible();
  await teamRow.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(
    page.getByLabel("Restricted Member", { exact: true }),
  ).toBeChecked();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("link", { name: "Users", exact: true }).click();
  await page
    .getByRole("row")
    .filter({ hasText: "Restricted Member" })
    .getByRole("button", { name: "Edit access" })
    .click();
  await expect(page.getByLabel("Login email")).toHaveValue(memberEmail);
  await expect(page.getByLabel("Login email")).toHaveAttribute("readonly", "");
  await expect(page.getByLabel("leads.assign", { exact: true })).toBeVisible();
  const dashboardOverrides = page.locator("fieldset").filter({
    has: page
      .locator(".permission-group-title")
      .filter({ hasText: /^dashboard$/ }),
  });
  await expect(dashboardOverrides.getByRole("button")).toHaveCount(1);
  await dashboardOverrides
    .getByRole("button", { name: "Select all", exact: true })
    .click();
  await expect(page.getByLabel("dashboard.view", { exact: true })).toHaveValue(
    "allow",
  );
  await expect(dashboardOverrides.getByRole("button")).toHaveText("Clear");
  await page.getByLabel("dashboard.view", { exact: true }).selectOption("deny");
  await expect(dashboardOverrides.getByRole("button")).toHaveText("Select all");
  await dashboardOverrides
    .getByRole("button", { name: "Select all", exact: true })
    .click();
  await dashboardOverrides
    .getByRole("button", { name: "Clear", exact: true })
    .click();
  await expect(page.getByLabel("dashboard.view", { exact: true })).toHaveValue(
    "",
  );
  await expect(dashboardOverrides.getByRole("button")).toHaveText("Select all");
  await page
    .getByLabel("Landing page", { exact: true })
    .selectOption("/account");
  await page.getByRole("button", { name: "Save access", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Access: Restricted Member",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole("row")
    .filter({ hasText: "Restricted Member" })
    .getByRole("button", { name: "Edit access" })
    .click();
  await expect(page.getByLabel("Landing page", { exact: true })).toHaveValue(
    "/account",
  );
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await memberPage
    .getByRole("link", { name: "My account", exact: true })
    .click();
  await memberPage
    .getByRole("button", { name: "Sign out", exact: true })
    .click();
  await memberPage.getByLabel("Organization slug").fill(slug);
  await memberPage.getByLabel("Email", { exact: true }).fill(memberEmail);
  await memberPage.getByLabel(/^Password/).fill(password);
  await memberPage
    .getByRole("button", { name: "Sign in", exact: true })
    .click();
  await expect(memberPage).toHaveURL(/\/account$/);

  await page.getByRole("link", { name: "Leads", exact: true }).click();
  await page.getByRole("link", { name: "+ New lead" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Browser pump enquiry");
  await page
    .getByLabel("Company", { exact: true })
    .fill("Browser Manufacturing");
  await page.getByLabel("Phone", { exact: true }).fill("+919998887777");
  await page
    .getByLabel("Email", { exact: true })
    .fill("private-buyer@example.com");
  await page.getByLabel(/^Tags/).fill("urgent, browser");
  await page
    .getByLabel("Enquiry", { exact: true })
    .fill("Private quotation details");
  await page.getByLabel("Restricted Member", { exact: true }).check();
  await page.getByRole("button", { name: "Create lead", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Browser pump enquiry" }),
  ).toBeVisible();
  const leadUrl = page.url();
  const statusNote = "Customer requested a formal quote.";
  await page.getByRole("combobox", { name: "New status", exact: true }).click();
  await page.getByRole("option", { name: "Qualified", exact: true }).click();
  await page.locator("#lead-status-note").fill(statusNote);
  await page.getByRole("button", { name: "Update status", exact: true }).click();
  await expect(page.getByText("Lead status updated.")).toBeVisible();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(page.getByText("Status changed: New to Qualified")).toBeVisible();
  await expect(page.getByText(statusNote, { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Lead Details", exact: true }).click();
  await page.getByRole("button", { name: "Edit lead", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Updated browser lead");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Updated browser lead" }),
  ).toBeVisible();
  await page.getByLabel("Search", { exact: true }).fill("Updated");
  await page
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Updated browser lead" }),
  ).toBeVisible();

  await memberPage.goto(leadUrl);
  await expect(
    memberPage.getByRole("heading", { name: "Updated browser lead" }),
  ).toBeVisible();
  await expect(
    memberPage.getByText("private-buyer@example.com", { exact: true }),
  ).toHaveCount(0);
  await memberPage.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(
    memberPage.getByText("Note restricted by contact permission.", { exact: true }),
  ).toBeVisible();
  await expect(memberPage.getByText(statusNote, { exact: true })).toHaveCount(0);
  await expect(
    memberPage.getByRole("button", { name: "Edit lead", exact: true }),
  ).toHaveCount(0);
  await expect(
    memberPage.getByRole("button", { name: "Update status", exact: true }),
  ).toHaveCount(0);
  await memberPage.goto("http://127.0.0.1:3012/roles");
  await expect(
    memberPage.getByRole("heading", { name: "Access restricted" }),
  ).toBeVisible();
  await page.goto(leadUrl);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Restore", exact: true }),
  ).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Archive", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "User management", exact: true })
    .click();
  const memberRow = page.getByRole("row").filter({ hasText: memberEmail });
  await expect(memberRow).toContainText(memberEmail);
  await memberRow.getByRole("button", { name: "Edit access" }).click();
  await page.getByLabel("Display name", { exact: true }).fill("Updated Member");
  await page.getByRole("button", { name: "Save access" }).click();
  await expect(
    page.getByRole("heading", { name: "Access: Restricted Member" }),
  ).toHaveCount(0);
  await expect(memberRow).toContainText("Updated Member");
  await memberRow.getByRole("button", { name: "Delete", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm delete", exact: true })
    .click();
  await expect(memberRow).toContainText("disabled");
  await expect(memberRow).toContainText("1 roles");
  await memberPage.goto(leadUrl);
  await expect(memberPage).toHaveURL(/\/login$/);
  await page.goto(leadUrl);
  await expect(
    page.getByRole("heading", { name: "Updated browser lead" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "My account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await memberContext.close();
  expect(consoleErrors).toEqual([]);
});

test("mobile login is usable and invalid credentials are explained", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await page.getByLabel("Organization slug").fill("missing-organization");
  await page.getByLabel("Email", { exact: true }).fill("missing@example.com");
  await page.getByLabel(/^Password/).fill("incorrect-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "incorrect" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
});
