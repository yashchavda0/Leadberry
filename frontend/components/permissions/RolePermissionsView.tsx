"use client";

import { useMemo, useState } from "react";
import Icon from "@/components/Icon";
import { useNotify } from "@/components/Notifications";
import RoleList from "@/components/permissions/RoleList";
import { useSession } from "@/components/Session";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { crm, errorMessage, type Permission, type Role } from "@/lib/crm";

// One place to pick a role, toggle its permissions and save.
export default function RolePermissionsView({ catalog, onSaved }: { catalog: Permission[]; onSaved?: () => void }) {
  const { can, identity } = useSession();
  const notify = useNotify();
  const [role, setRole] = useState<Role | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const editable = can("roles.manage");
  const grantable = (permission: Permission) => editable && permission.is_delegable && Boolean(identity?.is_owner || identity?.permissions.includes(permission.code));
  const areas = useMemo(() => {
    const byModule = new Map<string, Permission[]>();
    for (const permission of catalog) byModule.set(permission.module, [...(byModule.get(permission.module) || []), permission]);
    return [...byModule].map(([module, items]) => ({ module, items })).sort((a, b) => a.module.localeCompare(b.module));
  }, [catalog]);
  const dirty = role !== null && (selected.length !== role.permissions.length || selected.some(code => !role.permissions.includes(code)));
  function choose(next: Role) { setRole(next); setSelected(next.permissions); setOpen(false); }
  function toggle(code: string) { setSelected(current => current.includes(code) ? current.filter(item => item !== code) : [...current, code]); }
  function setArea(items: Permission[], on: boolean) {
    const codes = items.filter(grantable).map(item => item.code);
    setSelected(current => on ? [...new Set([...current, ...codes])] : current.filter(code => !codes.includes(code)));
  }
  async function save() {
    if (!role) return;
    setBusy(true);
    try {
      await crm(`/roles/${role.id}`, { method: "PUT", body: JSON.stringify({ name: role.name, description: role.description || null, data_scope: role.data_scope, permissions: selected, is_active: role.is_active, reports_to_role_id: role.reports_to_role_id || null }) });
      notify.success(`${role.name} permissions saved.`, { title: "Permissions saved" });
      setRole({ ...role, permissions: selected });
      onSaved?.();
    } catch (error) { notify.error(errorMessage(error), { title: "Permissions could not be saved" }); }
    finally { setBusy(false); }
  }
  return <div className="perm-min">
    <div className="perm-min-bar">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild><button type="button" className="perm-min-select"><span>{role ? role.name : "Choose a role"}</span><Icon name="chevron" size={16} /></button></PopoverTrigger>
        <PopoverContent className="role-switcher-pop"><RoleList selectedId={role?.id} onSelect={choose} /></PopoverContent>
      </Popover>
      {role && <span className="small muted">Level {role.level} · {role.data_scope} leads · {selected.length} of {catalog.length} permissions</span>}
      {role && editable && <span className="perm-min-actions">
        {dirty && <Button variant="ghost" size="sm" disabled={busy} onClick={() => setSelected(role.permissions)}>Reset</Button>}
        <Button size="sm" disabled={!dirty || busy} onClick={save}>{busy ? "Saving..." : "Save changes"}</Button>
      </span>}
    </div>
    {!role ? <div className="perm-min-empty"><Icon name="settings" size={28} /><strong>Pick a role</strong><span className="small muted">Toggle its permissions and save, all on this tab.</span></div>
      : <div className="perm-min-grid">
        {areas.map(({ module, items }) => {
          const usable = items.filter(grantable);
          const all = usable.length > 0 && usable.every(item => selected.includes(item.code));
          return <section key={module} className="perm-min-card">
            <h4>{module.replaceAll("_", " ")}{usable.length > 0 && <button type="button" className="permission-group-action" onClick={() => setArea(items, !all)}>{all ? "Clear" : "All"}</button>}</h4>
            <div className="perm-chips">{items.map(item => <button key={item.code} type="button" className="perm-chip perm-toggle" aria-pressed={selected.includes(item.code)} disabled={!grantable(item)} onClick={() => toggle(item.code)}>{item.action.replaceAll("_", " ")}</button>)}</div>
          </section>;
        })}
      </div>}
  </div>;
}
