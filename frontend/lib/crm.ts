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
};
export type MarketplaceAccount = {
  id: string;
  provider_code: string;
  name: string;
  status: "draft" | "active" | "paused" | "error" | "retired";
  config: Record<string, string>;
  credential_version: number;
  verified_version: number | null;
  row_version: number;
  last_success_at: string | null;
  last_received_at: string | null;
  safe_error_code: string | null;
  default_assignee_membership_id: string | null;
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
export type Page<T> = { data: T[]; next_cursor: string | null };
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
  status_changed_at: string;
  assigned_membership_id: string | null;
  assignee: string | null;
  team_id: string | null;
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

export function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
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
