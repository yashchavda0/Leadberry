export type Scope = "own" | "team" | "all";
export type MarketplaceProvider = {
  code: string;
  name: string;
  category: string;
  method: string;
  setup: boolean;
  adapter: boolean;
  multiple_accounts: boolean | null;
  documentation_url: string | null;
  note: string;
  fields: { key: string; label: string; secret: boolean; required: boolean }[];
  allowed_intervals?: number[];
  default_interval_seconds?: number;
  history_days?: number;
  max_window_seconds?: number;
};
export type LiveStatus = {
  state: "off" | "held" | "running" | "waiting" | "scheduled";
  reason: string | null;
  until: string | null;
  next_request_at: string | null;
};
export type HistoryStatus = {
  id: string;
  kind: "import" | "gap";
  state: "active" | "completed" | "cancelled";
  range_start: string;
  range_end: string;
  windows_total: number;
  windows_done: number;
  windows_failed: number;
  windows_pending: number;
  fetched_count: number;
  accepted_count: number;
  created_at: string;
  finished_at: string | null;
  reason: string | null;
  until: string | null;
  eta: string | null;
};
export type ImportRequest = HistoryStatus & {
  account_id: string;
  account_name: string;
  provider_code: string;
  requested_by: string | null;
};
export type BackfillWindow = {
  id: string;
  window_start: string;
  window_end: string;
  state:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "expired"
    | "skipped"
    | "split"
    | "cancelled";
  attempts: number;
  next_attempt_at: string;
  next_page: number;
  hold_reason: string | null;
  safe_error_code: string | null;
  fetched_count: number;
  accepted_count: number;
  updated_at: string;
};
export type MarketplaceAccount = {
  id: string;
  provider_code: string;
  name: string;
  status: "draft" | "active" | "paused" | "error" | "retired";
  config: Record<string, string>;
  credential_hint: Record<string, string>;
  credential_version: number;
  verified_version: number | null;
  row_version: number;
  last_success_at: string | null;
  last_received_at: string | null;
  safe_error_code: string | null;
  sync_interval_seconds: number;
  schedule_status: { live: LiveStatus; history: HistoryStatus | null };
  last_run_kind: "test" | "sync" | "backfill" | null;
  last_run_state:
    | "queued"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | null;
  last_run_error: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
};
export type MarketplaceRun = {
  id: string;
  kind: string;
  state: string;
  fetched_count: number;
  accepted_count: number;
  safe_error_code: string | null;
  window_start: string | null;
  window_end: string | null;
  created_at: string;
  finished_at: string | null;
};
export type Identity = {
  organization_id: string;
  membership_id: string;
  user_id: string;
  is_owner: boolean;
  permissions: string[];
  data_scope: Scope;
  landing_page: string | null;
};
export type Organization = {
  id: string;
  slug: string;
  name: string;
  timezone: string;
  status: string;
};
export type Page<T> = {
  data: T[];
  next_cursor: string | null;
  total?: number | null;
};
export type Role = {
  id: string;
  name: string;
  description: string | null;
  data_scope: Scope;
  permissions: string[];
  is_active: boolean;
  reports_to_role_id: string | null;
  reports_to_name: string | null;
  role_type: "Parent" | "Child";
  level: number;
};
export type Member = {
  id: string;
  display_name: string;
  email: string;
  status: "active" | "invited" | "disabled";
  is_owner: boolean;
  visibility_override: Scope | null;
  role_ids: string[];
  permission_overrides: Record<string, boolean>;
  landing_page: string | null;
};
export type Permission = {
  code: string;
  module: string;
  page: string;
  action: string;
  is_delegable: boolean;
};
export type Team = {
  id: string;
  name: string;
  is_active: boolean;
  membership_ids: string[];
};
export type Status = {
  id: string;
  name: string;
  color: string;
  type?: "new" | "pending" | "working" | "won" | "lost";
};
export type LeadCustomField = {
  field_key: string;
  label: string;
  field_type: "text" | "number" | "boolean" | "select";
  options: string[];
  position: number;
  is_active: boolean;
};
export type LeadStatus = {
  id: string;
  name: string;
  type: "new" | "pending" | "working" | "won" | "lost";
  color: string;
  position: number;
  is_active: boolean;
  is_default: boolean;
  is_system: boolean;
  tag_on_entry: string | null;
  auto_assign: boolean;
  member_ids: string[];
  role_ids: string[];
  required_fields: string[];
};
export type Lead = {
  id: string;
  name: string;
  company: string;
  phone: string | null;
  email: string | null;
  city: string;
  state: string;
  address: string | null;
  product: string;
  enquiry: string | null;
  source_provider: string;
  source_record_id: string | null;
  status_id: string;
  status: string;
  status_color: string;
  integration_id?: string | null;
  source_account_name?: string | null;
  backfill_id?: string | null;
  status_changed_at: string;
  assigned_membership_id: string | null;
  assignee: string | null;
  team_id: string | null;
  team_name?: string | null;
  tags: string[];
  custom_fields: Record<string, string | number | boolean | null>;
  next_follow_up_at: string | null;
  archived_at: string | null;
  row_version: number;
  received_at: string;
  updated_at: string;
  pii_redacted: boolean;
};
export type Dashboard = {
  total: number;
  today: number;
  converted: number;
  overdue: number;
  statuses: { name: string; color: string; count: number }[];
  sources: { name: string; count: number }[];
  recent: Lead[];
};

const messages: Record<string, string> = {
  authentication_required: "Please sign in to continue.",
  invalid_credentials: "The organization, email or password is incorrect.",
  invalid_session: "Your session has expired. Please sign in again.",
  membership_inactive: "Your organization membership is no longer active.",
  permission_denied: "You do not have permission for this action.",
  csrf_required:
    "Your browser session is missing its security token. Sign in again.",
  invalid_csrf:
    "Your security token has changed. Reload this page and try again.",
  invalid_invitation:
    "This invitation is invalid, expired or already accepted.",
  mfa_required_not_available:
    "This organization requires MFA, which is not available yet. Contact its administrator.",
  grant_exceeds_access:
    "You cannot grant permissions or scope beyond your own access.",
  owner_required: "Only an organization Owner can perform this action.",
  lead_version_conflict:
    "This lead changed since you opened it. Reload it before saving again.",
  lead_not_found:
    "This lead is unavailable or outside your current data scope.",
  lead_archived: "Restore this lead before editing it.",
  conflicting_state:
    "This change conflicts with existing data or the last-Owner protection.",
  lead_required_fields_missing:
    "Complete the required fields for this lead status before saving.",
  status_tag_limit_reached:
    "This lead already has the maximum number of tags for the status tag to be added.",
  reserved_custom_field_key:
    "Choose a field key that does not match a built-in lead field.",
  status_assignment_pool_required:
    "Select at least one active user for automatic assignment.",
  status_assignment_pool_empty:
    "No active eligible users are available for this status assignment.",
  invalid_custom_field_value:
    "One or more custom-field values do not match their configured type or options.",
  unknown_custom_field: "A custom field is not defined for this organization.",
  system_status_protected:
    "System status names, types, and active state cannot be changed.",
  default_status_required:
    "The organization must keep one active default lead status.",
  lead_status_in_use:
    "This status is used by existing leads and cannot be deactivated.",
  invalid_required_field:
    "Choose an existing active lead field for this status requirement.",
  custom_field_required_by_status:
    "This field is required by a status and cannot be deactivated.",
  database_unavailable: "The database is unavailable. Please retry shortly.",
  identity_database_not_configured:
    "The identity backend is not configured. Contact your administrator.",
  rate_limited: "Too many attempts. Please wait before trying again.",
  assignment_permission_required:
    "You need lead assignment permission for this change.",
  assignment_exceeds_scope: "That assignment is outside your data scope.",
  pii_permission_required:
    "Contact details require the leads.pii.view permission.",
  origin_not_allowed:
    "This website origin is not permitted by the backend configuration.",
  invalid_reporting_role: "Choose a reporting role in this organization.",
  role_hierarchy_cycle:
    "A role cannot report to itself or one of its descendants.",
  landing_page_not_allowed:
    "The selected landing page requires access from the user's active roles or direct permissions.",
  marketplace_name_in_use: "Another connection already uses this name.",
  marketplace_credentials_in_use:
    "This API key is already connected in your organization.",
  marketplace_version_conflict:
    "This connection changed in the meantime. Refresh and try again.",
  marketplace_test_required:
    "Run a successful connection test before activating or syncing.",
  marketplace_account_not_active:
    "Activate this connection before syncing leads.",
  marketplace_account_unavailable: "This connection is no longer available.",
  provider_account_limit_unverified:
    "Only one account of this provider can be connected for now.",
  provider_adapter_unavailable: "This provider cannot be connected yet.",
  invalid_provider_configuration: "Fill in every required provider field.",
  invalid_provider_credentials: "Enter the API key for this provider.",
  marketplace_key_unavailable:
    "Secure credential storage is not configured on the server.",
  invalid_sync_interval: "Choose one of the offered sync intervals.",
  marketplace_backfill_active:
    "A history import is already running for this connection. Cancel it or wait for it to finish.",
  marketplace_backfill_range_empty:
    "There is nothing to import in that range: it is outside the provider's history limit or already covered by live sync.",
  marketplace_backfill_range_invalid:
    "The start date must be on or before the end date.",
  marketplace_backfill_closed:
    "This import has already finished or was cancelled.",
  marketplace_backfill_nothing_to_retry: "No failed periods to retry.",
  marketplace_backfill_not_found: "This import is no longer available.",
  lead_export_too_large:
    "More than 50,000 leads match. Narrow the filters (for example a date range) and export again.",
};

export const marketplaceErrors: Record<string, string> = {
  provider_credentials_rejected:
    "The provider rejected the API key. Check or regenerate it, then save and test again.",
  provider_rate_limited:
    "The provider's request limit was reached (TradeIndia blocks the key for 15 minutes). The connector waits and retries.",
  provider_unavailable:
    "The provider could not be reached. Try the connection test again.",
  provider_timeout:
    "The provider took too long to respond. Try the connection test again.",
  connector_internal_error:
    "The connector hit an unexpected error. Try again; check the worker terminal if it repeats.",
  provider_response_rejected:
    "The provider refused the request. Confirm API access is enabled for this account.",
  provider_payload_invalid: "The provider returned an unexpected response.",
  provider_payload_too_large:
    "The provider returned too much data in one window.",
  provider_history_expired:
    "That period is older than the provider keeps (IndiaMART: 365 days), so it can no longer be fetched.",
  provider_history_not_ready:
    "IndiaMART releases leads older than a new API key 24 hours after the key was generated. Retried automatically.",
  worker_lease_expired:
    "The connector stopped while working on this request. The period goes back in the queue.",
  marketplace_key_unavailable:
    "The connector worker could not decrypt this key. Re-enter the API key.",
  integration_actor_inactive:
    "The member who created this connection lost marketplace access. Disconnect it and connect it again.",
  integration_default_status_missing:
    "Set a default lead status, then sync again.",
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function crm<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const cookie = document.cookie
      .split("; ")
      .find((value) => value.startsWith("crm_csrf="));
    if (cookie)
      headers.set(
        "X-CSRF-Token",
        decodeURIComponent(cookie.slice("crm_csrf=".length)),
      );
  }
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: {
    code?: string;
    errors?: { loc: (string | number)[]; msg: string }[];
  };
  try {
    data = JSON.parse(text);
  } catch {
    throw new ApiError(
      response.status,
      "invalid_response",
      "The API returned an unexpected response. Check backend availability.",
    );
  }
  if (!response.ok) {
    const code = data.code || "request_failed";
    if (
      response.status === 401 &&
      ![
        "/auth/login",
        "/auth/accept-invite",
        "/organizations/onboard",
        "/auth/me",
      ].includes(path)
    ) {
      window.dispatchEvent(new Event("crm-session-expired"));
    }
    const validation = data.errors
      ?.map((item) => `${item.loc.slice(1).join(".")}: ${item.msg}`)
      .join("; ");
    throw new ApiError(
      response.status,
      code,
      validation ||
        messages[code] ||
        `Request rejected: ${code.replaceAll("_", " ")} (${response.status}).`,
    );
  }
  return data as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred.";
}

/** Downloads a file response (such as an Excel export) and returns the saved file name. */
export async function download(
  path: string,
  fallbackName: string,
): Promise<string> {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    let code = "request_failed";
    try {
      code = (await response.json()).code || code;
    } catch {
      /* non-JSON error body */
    }
    if (response.status === 401)
      window.dispatchEvent(new Event("crm-session-expired"));
    throw new ApiError(
      response.status,
      code,
      messages[code] ||
        `Download failed: ${code.replaceAll("_", " ")} (${response.status}).`,
    );
  }
  const name =
    /filename="([^"]+)"/.exec(
      response.headers.get("content-disposition") || "",
    )?.[1] || fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
  return name;
}

export function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatDay(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatInterval(seconds: number): string {
  return seconds % 3600 === 0
    ? `${seconds / 3600} hour${seconds === 3600 ? "" : "s"}`
    : `${seconds / 60} min`;
}

// Mirrors backend schedule.backfill_slots_per_cycle: 315 s request slot, live may slip 90 s.
export function importSlotsPerCycle(interval: number): number {
  return Math.max(0, Math.floor((interval - 315 + 90) / 315));
}

/** "in 4 min · 10:35": relative and exact, so the user knows both how long and when. */
export function formatWhen(value: string | null, now = Date.now()): string {
  if (!value) return "";
  const target = new Date(value);
  const minutes = Math.round((target.getTime() - now) / 60000);
  const sameDay = target.toDateString() === new Date(now).toDateString();
  const exact = target.toLocaleString(
    undefined,
    sameDay
      ? { timeStyle: "short" }
      : { dateStyle: "medium", timeStyle: "short" },
  );
  if (minutes <= 0) return exact;
  const relative =
    minutes < 60
      ? `${minutes} min`
      : minutes < 2880
        ? `${Math.round(minutes / 60)} h`
        : `${Math.round(minutes / 1440)} days`;
  return `in ${relative} · ${exact}`;
}

export function holdReasonText(
  reason: string,
  provider: string,
  until: string | null,
): string {
  const when = formatWhen(until);
  const at = when ? ` (${when})` : "";
  const texts: Record<string, string> = {
    waiting_key_slot: `${provider} allows one request every 5 minutes per API key. Next request${at}.`,
    shared_key_slot: `This API key is also used by another connection, so requests take turns. Next turn${at}.`,
    provider_cooldown: `${provider} temporarily blocked this key for too many requests. Resuming${at}.`,
    provider_unavailable_retry: `${provider} is not responding. Retrying automatically${at}.`,
    provider_timeout_retry: `${provider} took too long to respond. Retrying automatically${at}.`,
    provider_error_retry: `The last import request failed. Retrying automatically${at}.`,
    history_not_ready: `${provider} releases leads older than a new API key only 24 hours after the key was generated. Older leads will be fetched${at}.`,
    history_expired: `Older than ${provider}'s history limit, so this period can no longer be fetched.`,
    window_split_large:
      "This period had too many leads for one request, so it was split into smaller parts.",
    window_continues_next_slot:
      "This period has more pages; the rest is fetched in the next request slot.",
    import_paused_interval_5min: `History import is paused: syncing every 5 minutes uses every request ${provider} allows. Choose 10 minutes or more to free slots.`,
    import_paused_account_paused:
      "History import resumes when the connection is active again.",
    import_paused_needs_test:
      "History import waits until the connection is tested and active.",
    import_cancelled_credentials_changed:
      "Import cancelled because the API key changed. Start a new import for the new key.",
    import_cancelled_connection_removed:
      "Import cancelled because the connection was deleted.",
    import_cancelled_by_user: "Import cancelled.",
    import_cancelled_actor_inactive:
      "Import cancelled because the member who created this connection lost marketplace access.",
    import_stopped_no_older_data: `Stopped early: ${provider} returned no older enquiries for several weeks in a row.`,
    import_completed_with_failures:
      "Import finished, but some periods failed. Open the import details to retry them.",
    key_expiry_risk:
      until && new Date(until).getTime() > Date.now()
        ? `${provider} expires API keys that are unused for 7 days. Resume before ${formatDate(until)} to keep this key.`
        : `This key has not been used for over 7 days and may have expired at ${provider}. Generate a new key if the test fails.`,
    worker_offline:
      "The connector is offline. Requests run as soon as it starts again.",
    gap_recovery: `Live sync resumed with the most recent period. Leads missed before that are fetched from ${provider} in the free request slots, newest first.`,
  };
  return texts[reason] || reason.replaceAll("_", " ");
}

export const landingPages = [
  { path: "/", label: "Overview", permissions: ["dashboard.view"] },
  { path: "/leads", label: "Leads", permissions: ["leads.view"] },
  {
    path: "/users",
    label: "User management",
    permissions: ["users.view", "roles.view"],
  },
  { path: "/settings", label: "Organization", permissions: ["settings.view"] },
  {
    path: "/marketplace",
    label: "Marketplace",
    permissions: ["marketplace.view"],
  },
  { path: "/account", label: "My account", permissions: [] },
];

export function homeFor(identity: Identity): string {
  const allowed = landingPages.filter(
    (page) =>
      !page.permissions.length ||
      page.permissions.some((code) => identity.permissions.includes(code)),
  );
  return (
    allowed.find((page) => page.path === identity.landing_page)?.path ||
    allowed[0].path
  );
}
