"use client";

import { useSession } from "./Session";
import { type Permission } from "@/lib/crm";

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
  return <div className="permission-grid">{modules.map(module => {
    const group = catalog.filter(permission => permission.module === module);
    const selectable = group.filter(grantable);
    const allSelected = selectable.length > 0 && selectable.every(permission =>
      onSelect ? selected?.includes(permission.code) : overrides?.[permission.code] === true);
    return <fieldset key={module}><legend className="permission-group-heading"><span className="permission-group-title">{module.replaceAll("_", " ")}</span>
      <span className="permission-group-actions"><button className="btn permission-group-action" type="button" disabled={!selectable.length} onClick={() => bulk(group, !allSelected)}>{allSelected ? "Clear" : "Select all"}</button></span>
    </legend>
      {group.map(permission => onSelect ? <label className="check-row" key={permission.code}><input type="checkbox" aria-label={permission.code} checked={selected?.includes(permission.code) || false} disabled={!grantable(permission)} onChange={event => onSelect(event.target.checked ? [...(selected || []), permission.code] : (selected || []).filter(code => code !== permission.code))} /><span><code>{permission.code}</code>{permission.code === "leads.assign" && <span className="small muted"> (Assign / reassign leads)</span>}</span></label> :
        <label className="override-row" key={permission.code}><span><code>{permission.code}</code>{permission.code === "leads.assign" && <span className="small muted"> (Assign / reassign leads)</span>}</span><select className="select" aria-label={permission.code} value={overrides && permission.code in overrides ? overrides[permission.code] ? "allow" : "deny" : ""} onChange={event => {
          const next = { ...overrides };
          if (!event.target.value) delete next[permission.code]; else next[permission.code] = event.target.value === "allow";
          onOverride?.(next);
        }}><option value="">From roles</option><option value="allow" disabled={!grantable(permission)}>Allow</option><option value="deny">Deny</option></select></label>)}
    </fieldset>;
  })}</div>;
}
