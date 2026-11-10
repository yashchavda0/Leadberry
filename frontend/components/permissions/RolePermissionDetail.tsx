"use client";

import { useMemo, useState } from "react";
import { useSession } from "@/components/Session";
import ScrollArea from "@/components/ScrollArea";
import SearchInput from "@/components/SearchInput";
import { type Permission, type Role } from "@/lib/crm";

export default function RolePermissionDetail({ role, catalog, onEdit }: { role: Role; catalog: Permission[]; onEdit: (role: Role) => void }) {
  const { can } = useSession();
  const [query, setQuery] = useState("");
  const [grantedOnly, setGrantedOnly] = useState(true);
  const granted = useMemo(() => new Set(role.permissions), [role.permissions]);
  const term = query.trim().toLowerCase();
  const modules = useMemo(() => {
    const groups = new Map<string, Permission[]>();
    for (const permission of catalog) groups.set(permission.module, [...(groups.get(permission.module) || []), permission]);
    return [...groups].map(([module, items]) => ({
      module, total: items.length, grantedCount: items.filter(item => granted.has(item.code)).length,
      visible: items.filter(item => (!grantedOnly || granted.has(item.code)) && (!term || `${item.code} ${item.module}`.toLowerCase().includes(term))),
    })).filter(group => group.visible.length);
  }, [catalog, granted, grantedOnly, term]);
  return <section className="perm-detail" aria-label={`Permissions for ${role.name}`}>
    <header className="perm-detail-head">
      <div><h3>{role.name}</h3><p className="small muted">Level {role.level} · {role.data_scope} scope · {role.is_active ? "Active" : "Inactive"} · {role.permissions.length} of {catalog.length} permissions</p></div>
      {can("roles.manage") && <button className="btn" type="button" onClick={() => onEdit(role)}>Edit permissions</button>}
    </header>
    <div className="perm-detail-tools">
      <SearchInput className="perm-search" placeholder="Search permissions (e.g. leads.assign)" label="Search permissions" value={query} onChange={setQuery} />
      <label className="check-row"><input type="checkbox" checked={grantedOnly} onChange={event => setGrantedOnly(event.target.checked)} />Granted only</label>
    </div>
    <ScrollArea maxHeight="60vh" label="Permissions"><div className="perm-modules">
      {modules.length ? modules.map(group => <details key={group.module} open>
        <summary><span>{group.module.replaceAll("_", " ")}</span><span className="small muted">{group.grantedCount}/{group.total}</span></summary>
        <ul>{group.visible.map(item => <li key={item.code} data-granted={granted.has(item.code)}><code>{item.code}</code><span className="small">{granted.has(item.code) ? "Granted" : "Not granted"}</span></li>)}</ul>
      </details>) : <p className="small muted">No permissions match.</p>}
    </div></ScrollArea>
  </section>;
}
