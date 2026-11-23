"use client";

import { useSession } from "./Session";
import { type Permission } from "@/lib/crm";

const MODULE_LABELS: Record<string, string> = {
  api_integrations: "API Integrations",
  api_keys: "API Keys",
  assignment_rules: "Assignment Rules",
  dashboard: "Dashboard",
  leads: "Leads",
  marketplace: "Marketplace",
  reports: "Reports",
  roles: "Roles",
  settings: "Settings",
  users: "Users",
  audit: "Audit Log",
};

const PERMISSION_LABELS: Record<string, string> = {
  "api_integrations.manage": "Manage API integrations",
  "api_integrations.view": "View API integrations",
  "api_keys.manage": "Manage API keys",
  "assignment_rules.manage": "Manage assignment rules",
  "audit.export": "Export audit log",
  "audit.view": "View audit log",
  "dashboard.view": "View dashboard",
  "leads.archive": "Archive leads",
  "leads.assign": "Assign or reassign leads",
  "leads.create": "Create leads",
  "leads.delete": "Delete leads",
  "leads.edit": "Edit leads",
  "leads.export": "Export leads",
  "leads.import": "Import leads",
  "leads.pii.view": "View sensitive lead details",
  "leads.restore": "Restore archived leads",
  "leads.share": "Share leads",
  "leads.view": "View leads",
  "marketplace.manage": "Manage marketplace connections",
  "marketplace.replay": "Replay marketplace syncs",
  "marketplace.view": "View marketplace connections",
  "reports.export": "Export reports",
  "reports.view": "View reports",
  "roles.manage": "Manage roles",
  "roles.view": "View roles and permissions",
  "settings.manage": "Manage organization settings",
  "settings.view": "View organization settings",
  "users.manage": "Manage users and invitations",
  "users.view": "View users and teams",
};

function moduleLabel(module: string): string {
  return MODULE_LABELS[module] || module.replaceAll("_", " ");
}

function permissionLabel(permission: Permission): string {
  return PERMISSION_LABELS[permission.code] || `${moduleLabel(permission.module)}: ${permission.action.replaceAll("_", " ")}`;
}

export default function PermissionGroups({ catalog, selected, overrides, onSelect, onOverride }: {
  catalog: Permission[]; selected?: string[]; overrides?: Record<string, boolean>;
  onSelect?: (codes: string[]) => void; onOverride?: (values: Record<string, boolean>) => void;
}) {
  const { identity } = useSession();
  const grantable = (permission: Permission) => permission.is_delegable && Boolean(identity?.is_owner || identity?.permissions.includes(permission.code));
  const modules = [...new Set(catalog.map(permission => permission.module))];
  function bulk(group: Permission[], allow: boolean) {
    if (onSelect) {
      const codes = group.filter(grantable).map(permission => permission.code);
      onSelect(allow ? [...new Set([...(selected || []), ...codes])] : (selected || []).filter(code => !group.some(permission => permission.code === code)));
    } else if (onOverride) {
      const next = { ...overrides };
      for (const permission of group) {
        if (allow && grantable(permission)) next[permission.code] = true;
        else if (!allow) delete next[permission.code];
      }
      onOverride(next);
    }
  }
  const allGrantable = catalog.filter(grantable);
  const everythingSelected = allGrantable.length > 0 && allGrantable.every(permission =>
    onSelect ? selected?.includes(permission.code) : overrides?.[permission.code] === true);
  const chosen = onSelect ? (selected || []).length : Object.keys(overrides || {}).length;
  return <><div className="permission-toolbar"><span className="small muted">{chosen} of {catalog.length} {onSelect ? "permissions granted" : "permission overrides"}</span>
    <button className="permission-select-all" type="button" disabled={!allGrantable.length} onClick={() => bulk(catalog, !everythingSelected)}>{everythingSelected ? "Clear all grants" : "Grant all permissions"}</button></div>
  <div className="permission-grid">{modules.map(module => {
    const group = catalog.filter(permission => permission.module === module);
    const selectable = group.filter(grantable);
    const allSelected = selectable.length > 0 && selectable.every(permission =>
      onSelect ? selected?.includes(permission.code) : overrides?.[permission.code] === true);
    return <fieldset key={module}><legend className="permission-group-heading"><span className="permission-group-title">{moduleLabel(module)}</span>
      <span className="permission-group-actions"><button className="permission-group-action" type="button" disabled={!selectable.length} onClick={() => bulk(group, !allSelected)}>{allSelected ? "Clear grants" : "Grant all"}</button></span>
    </legend>
      {group.map(permission => onSelect ? <label className="check-row" key={permission.code}><input type="checkbox" aria-label={permission.code} checked={selected?.includes(permission.code) || false} disabled={!grantable(permission)} onChange={event => onSelect(event.target.checked ? [...(selected || []), permission.code] : (selected || []).filter(code => code !== permission.code))} /><span className="permission-label" title={permission.code}>{permissionLabel(permission)}</span></label> :
        <label className="override-row" key={permission.code}><span className="permission-label" title={permission.code}>{permissionLabel(permission)}</span><select className="select" aria-label={permission.code} value={overrides && permission.code in overrides ? overrides[permission.code] ? "allow" : "deny" : ""} onChange={event => {
          const next = { ...overrides };
          if (!event.target.value) delete next[permission.code]; else next[permission.code] = event.target.value === "allow";
          onOverride?.(next);
        }}><option value="">From roles</option><option value="allow" disabled={!grantable(permission)}>Allow</option><option value="deny">Deny</option></select></label>)}
    </fieldset>;
  })}</div></>;
}
