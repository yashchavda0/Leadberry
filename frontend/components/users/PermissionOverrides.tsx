"use client";

import { useMemo, useState } from "react";
import Icon from "@/components/Icon";
import SearchInput from "@/components/SearchInput";
import { useSession } from "@/components/Session";
import { Badge } from "@/components/ui/badge";
import { Tip } from "@/components/ui/tip";
import { type Permission } from "@/lib/crm";
import { cn } from "@/lib/utils";

type State = "inherit" | "allow" | "deny";

// All areas in one scrollable list, with bulk actions per area and for everything.
export default function PermissionOverrides({ catalog, overrides, onChange }: { catalog: Permission[]; overrides: Record<string, boolean>; onChange: (next: Record<string, boolean>) => void }) {
  const { identity } = useSession();
  const [query, setQuery] = useState("");
  const term = query.trim().toLowerCase();
  const grantable = (permission: Permission) => permission.is_delegable && Boolean(identity?.is_owner || identity?.permissions.includes(permission.code));
  const stateOf = (code: string): State => code in overrides ? (overrides[code] ? "allow" : "deny") : "inherit";
  const set = (codes: string[], state: State) => {
    const next = { ...overrides };
    for (const code of codes) { if (state === "inherit") delete next[code]; else next[code] = state === "allow"; }
    onChange(next);
  };
  const areas = useMemo(() => {
    const byModule = new Map<string, Permission[]>();
    for (const permission of catalog) byModule.set(permission.module, [...(byModule.get(permission.module) || []), permission]);
    return [...byModule]
      .map(([module, items]) => ({ module, items: term ? items.filter(item => item.code.toLowerCase().includes(term) || module.toLowerCase().includes(term)) : items }))
      .filter(area => area.items.length)
      .sort((a, b) => a.module.localeCompare(b.module));
  }, [catalog, term]);
  const grantableAll = catalog.filter(grantable).map(permission => permission.code);
  const allowed = Object.values(overrides).filter(Boolean).length;
  const denied = Object.values(overrides).length - allowed;

  return <div className="override-panel">
    <div className="override-toolbar">
      <SearchInput value={query} onChange={setQuery} placeholder="Search permissions, e.g. leads.export" />
      <div className="override-summary"><Badge variant="success">{allowed} allowed</Badge><Badge variant="destructive">{denied} denied</Badge></div>
      <button type="button" className="permission-group-action" disabled={!grantableAll.length} onClick={() => set(grantableAll, "allow")}>Allow all</button>
      <button type="button" className="permission-group-action" disabled={!allowed && !denied} onClick={() => onChange({})}>Reset all</button>
    </div>
    <div className="override-list ov-all">
      {areas.map(({ module, items }) => {
        const usable = items.filter(grantable).map(item => item.code);
        return <div key={module} className="override-group">
          <div className="override-list-head"><strong>{module.replaceAll("_", " ")}</strong>
            <span><button type="button" className="permission-group-action" disabled={!usable.length} onClick={() => set(usable, "allow")}>Allow all</button>
              <button type="button" className="permission-group-action" onClick={() => set(items.map(item => item.code), "inherit")}>Reset</button></span></div>
          {items.map(permission => { const state = stateOf(permission.code); const canAllow = grantable(permission); return <div key={permission.code} className={cn("override-row2", state !== "inherit" && `is-${state}`)}>
            <span className="override-name"><code>{permission.code}</code><small>{permission.action.replaceAll("_", " ")}</small></span>
            <span className="seg" role="group" aria-label={`${permission.code} access`}>
              <button type="button" aria-pressed={state === "inherit"} onClick={() => set([permission.code], "inherit")}>From roles</button>
              <Tip label="You can only allow permissions you hold yourself" disabled={canAllow}><span><button type="button" className="allow" aria-pressed={state === "allow"} disabled={!canAllow} onClick={() => set([permission.code], "allow")}><Icon name="check" size={13} />Allow</button></span></Tip>
              <button type="button" className="deny" aria-pressed={state === "deny"} onClick={() => set([permission.code], "deny")}><Icon name="close" size={13} />Deny</button>
            </span>
          </div>; })}
        </div>;
      })}
      {!areas.length && <p className="small muted override-empty">No permissions match.</p>}
    </div>
    <p className="small muted">"From roles" uses whatever the user's roles grant. Deny always wins over roles. Owners keep full access.</p>
  </div>;
}
