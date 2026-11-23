"use client";

import { useState } from "react";
import { useNotify } from "@/components/Notifications";
import RoleList from "@/components/permissions/RoleList";
import PermissionGroups from "@/components/PermissionGroups";
import { useSession } from "@/components/Session";
import { Button } from "@/components/ui/button";
import { crm, errorMessage, type Permission, type Role } from "@/lib/crm";

export default function RolePermissionsView({ catalog }: { catalog: Permission[] }) {
  const { can } = useSession();
  const notify = useNotify();
  const [role, setRole] = useState<Role | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [listRevision, setListRevision] = useState(0);
  const editable = can("roles.manage");
  const dirty = role !== null && (selected.length !== role.permissions.length || selected.some(code => !role.permissions.includes(code)));
  function choose(next: Role) { setRole(next); setSelected(next.permissions); }
  async function save() {
    if (!role) return;
    setBusy(true);
    try {
      await crm(`/roles/${role.id}`, { method: "PUT", body: JSON.stringify({ name: role.name, description: role.description || null, data_scope: role.data_scope, permissions: selected, is_active: role.is_active, reports_to_role_id: role.reports_to_role_id || null }) });
      notify.success(`${role.name} permissions saved.`, { title: "Permissions saved" });
      setRole({ ...role, permissions: selected });
      setListRevision(value => value + 1);
    } catch (error) { notify.error(errorMessage(error), { title: "Permissions could not be saved" }); }
    finally { setBusy(false); }
  }
  return <div className="perm-layout">
    <RoleList key={listRevision} selectedId={role?.id} onSelect={choose} />
    {role ? <section className="perm-detail">
      <div className="perm-detail-head">
        <div>
          <h3>{role.name}</h3>
          <p className="small muted">Level {role.level} · {role.data_scope} lead visibility · {selected.length} of {catalog.length} permissions</p>
        </div>
        {editable && <div className="perm-min-actions">
          {dirty && <Button variant="ghost" size="sm" disabled={busy} onClick={() => setSelected(role.permissions)}>Reset</Button>}
          <Button size="sm" disabled={!dirty || busy} onClick={save}>{busy ? "Saving..." : "Save changes"}</Button>
        </div>}
      </div>
      <PermissionGroups catalog={catalog} selected={selected} onSelect={setSelected} />
    </section> : <div className="perm-detail empty-state"><h3>Select a role</h3><p className="muted">Choose a role from the list to view or edit its page permissions.</p></div>}
  </div>;
}
