"use client";

import { useState } from "react";
import SelectionPicker from "@/components/SelectionPicker";
import PermissionGroups from "@/components/PermissionGroups";
import RolePermissionsView from "@/components/permissions/RolePermissionsView";
import { useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading, Pagination } from "@/components/Ui";
import { crm, errorMessage, type Permission, type Role, type Scope } from "@/lib/crm";
import { usePaged, useResource } from "@/lib/hooks";

export default function Roles({ permissionsOnly = false }: { permissionsOnly?: boolean }) {
  const list = usePaged<Role>(permissionsOnly ? null : "/roles");
  const catalog = useResource<{ data: Permission[] }>("/permissions");
  const { can } = useSession();
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const [revision, setRevision] = useState(0);
  return <><div className="page-header"><div><h2>{permissionsOnly ? "Permissions" : "Roles"}</h2><p className="muted">{permissionsOnly ? "Edit a role's grouped permissions here. Individual overrides are saved in the Users tab." : "Reporting determines levels, not access. Level 1 is the highest."}</p></div>{!permissionsOnly && can("roles.manage") && <button className="btn btn-primary" onClick={() => setEditing("new")}>+ Create role</button>}</div>
    <div className="alert alert-info">Owners always have full access. For other members, active roles combine permissions, direct deny overrides win, and the visibility override replaces role scope.</div>
    <ErrorNotice error={list.error || catalog.error} />
    {editing && catalog.data && <RoleEditor key={typeof editing === "string" ? "new" : editing.id} role={typeof editing === "string" ? undefined : editing} catalog={catalog.data.data} onDone={() => { setEditing(null); list.reload(); setRevision(value => value + 1); }} onCancel={() => setEditing(null)} />}
    {permissionsOnly && (catalog.data ? <RolePermissionsView key={revision} catalog={catalog.data.data} onEdit={setEditing} /> : <Loading />)}    {!permissionsOnly && <div className="card">{list.loading ? <Loading /> : list.data?.data.length ? <div className="table-wrap"><table><thead><tr><th>Role</th><th>Type</th><th>Level</th><th>Report to</th><th>Scope</th><th>Permissions</th><th>Status</th><th>Actions</th></tr></thead><tbody>{list.data.data.map(role => <tr key={role.id}><td><strong>{role.name}</strong><div className="small muted">{role.description}</div></td><td>{role.role_type}</td><td>{role.level}</td><td>{role.reports_to_name || "None (top level)"}</td><td><span className="badge">{role.data_scope}</span></td><td>{role.permissions.length} grants</td><td>{role.is_active ? "Active" : "Inactive"}</td><td>{can("roles.manage") && <button className="btn role-action-icon" type="button" aria-label={permissionsOnly ? "Edit permissions" : "Edit"} title={`${permissionsOnly ? "Edit permissions" : "Edit role"}: ${role.name}`} onClick={() => setEditing(role)}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m16 3 5 5M4 20l4-1L21 6a2.8 2.8 0 0 0-4-4L4 15l-1 6Z" /></svg>
    </button>}</td></tr>)}</tbody></table></div> : <div className="empty-state"><h3>No custom roles yet</h3><p className="muted">Create a role in the Roles tab before inviting your team.</p></div>}<Pagination page={list.page} previous={list.previous} next={list.next} hasPrevious={list.hasPrevious} hasNext={Boolean(list.data?.next_cursor)} loading={list.loading} /></div>}
  </>;
}
function RoleEditor({ role, catalog, onDone, onCancel }: { role?: Role; catalog: Permission[]; onDone: () => void; onCancel: () => void }) {
  const [parent, setParent] = useState<string[]>(role?.reports_to_role_id ? [role.reports_to_role_id] : []);
  const [selected, setSelected] = useState(role?.permissions || []);
  const [scope, setScope] = useState<Scope>(role?.data_scope || "own");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const values = new FormData(event.currentTarget);
    try {
      await crm(role ? `/roles/${role.id}` : "/roles", { method: role ? "PUT" : "POST", body: JSON.stringify({ name: values.get("name"), description: values.get("description") || null, data_scope: scope, permissions: selected, is_active: values.get("is_active") === "on", reports_to_role_id: parent[0] || null }) });
      onDone();
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <form className="card editor-card" onSubmit={save}><h2>{role ? "Edit role" : "New role"}</h2><ErrorNotice error={error} /><div className="form-grid"><Field label="Role name"><input className="input" name="name" defaultValue={role?.name || ""} required maxLength={100} /></Field><Field label="Description"><input className="input" name="description" defaultValue={role?.description || ""} maxLength={1000} /></Field><Field label="Lead visibility"><select className="select" value={scope} onChange={event => setScope(event.target.value as Scope)}><option value="own">Own assigned leads + own unassigned leads</option><option value="team">Own leads + leads assigned to your teams</option><option value="all">All organization leads</option></select></Field><label className="check-row"><input name="is_active" type="checkbox" defaultChecked={role?.is_active ?? true} />Active role</label></div>
    <SelectionPicker path="/roles" label="Report to role (none = top level)" values={parent} onChange={setParent} single excludeIds={role ? [role.id] : []} includeInactive />
    <p className="small muted">Type: {parent.length ? "Child" : "Parent"}. Level is calculated from the reporting chain on save; descendants update automatically. Reporting does not inherit permissions or lead visibility.</p>
    <PermissionGroups catalog={catalog} selected={selected} onSelect={setSelected} />
    <p className="small muted">Permission catalog includes future features. Only dashboard, leads, users/teams, roles and organization settings have working APIs in this phase. Non-Owners cannot grant beyond their own access.</p><div className="form-actions"><button className="btn" type="button" onClick={onCancel}>Cancel</button><button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Save role"}</button></div>
  </form>;
}
