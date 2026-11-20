"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Roles from "@/components/Roles";
import { DataTable } from "@/components/ui/data-table";
import { useNotify } from "@/components/Notifications";
import { Badge } from "@/components/ui/badge";
import Icon from "@/components/Icon";
import { IconButton } from "@/components/ui/icon-button";
import type { ColumnDef } from "@tanstack/react-table";
import PermissionGroups from "@/components/PermissionGroups";
import InvitationTokenDialog from "@/components/InvitationTokenDialog";
import LandingPagePicker from "@/components/LandingPagePicker";
import SelectionPicker from "@/components/SelectionPicker";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading, Pagination } from "@/components/Ui";
import { crm, errorMessage, landingPages, type Member, type Permission, type Role, type Scope, type Team } from "@/lib/crm";
import { usePaged, useResource } from "@/lib/hooks";

export default function UsersPage() { return <Suspense fallback={<Loading />}><UserManagement /></Suspense>; }
function UserManagement() {
  const { can, identity } = useSession();
  const params = useSearchParams();
  const tabs = [
    { id: "users", label: "Users", allowed: can("users.view") },
    { id: "teams", label: "Teams", allowed: Boolean(identity?.is_owner && can("users.manage")) },
    { id: "roles", label: "Roles", allowed: can("roles.view") },
    { id: "permissions", label: "Permissions", allowed: can("roles.view") },
  ].filter(tab => tab.allowed);
  const active = params.get("tab") || tabs[0]?.id;
  if (!tabs.length) return <Guard permission="users.view"><></></Guard>;
  return <><div className="page-header"><div><span className="eyebrow">YOUR ORGANIZATION</span><h1>User management</h1><p className="muted">Manage users, teams, reporting roles and permissions in one place.</p></div></div>
    <nav className="management-tabs" aria-label="User management sections">{tabs.map(tab => <Link key={tab.id} href={`/users?tab=${tab.id}`} aria-current={active === tab.id ? "page" : undefined}>{tab.label}</Link>)}</nav>
    {!tabs.some(tab => tab.id === active) ? <div className="card"><h2>Access restricted</h2><p>This management section is unavailable for your access.</p></div> : active === "users" ? <Users /> : active === "teams" ? <Teams /> : <Roles key={active} permissionsOnly={active === "permissions"} />}
  </>;
}
function Users() {
  const list = usePaged<Member>("/memberships");
  const roleList = useResource<{ data: Role[] }>("/roles");
  const roleById = new Map((roleList.data?.data || []).map(role => [role.id, role]));
  const memberRoles = (member: Member) => member.role_ids.flatMap(id => roleById.get(id) ?? []);
  const { can, identity } = useSession();
  const [editing, setEditing] = useState<Member | null>(null);
  const [inviting, setInviting] = useState(false);
  const [invitationMember, setInvitationMember] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Member | null>(null);
  const [busy, setBusy] = useState(false);
  const notify = useNotify();
  async function deactivate() {
    if (!deleting) return;
    setBusy(true);
    try {
      await crm(`/memberships/${deleting.id}`, { method: "DELETE" });
      notify.error(`${deleting.display_name} no longer has access. Their leads and history are kept.`, { title: "User deleted" });
      setDeleting(null); setEditing(null); list.reload();
    } catch (error) { notify.error(errorMessage(error), { title: "User could not be deleted" }); }
    finally { setBusy(false); }
  }
  return <><div className="page-header"><div><h2>Users</h2><p className="muted">Invite colleagues, assign roles and select their landing pages.</p></div>{can("users.manage") && <button className="btn btn-primary" onClick={() => { setInviting(true); setEditing(null); }}>+ Invite user</button>}</div>
    <ErrorNotice error={list.error} />
    {deleting && <section className="card editor-card" aria-label="Confirm user deletion"><h2>Delete user: {deleting.display_name}?</h2><p>This disables workspace access and revokes sessions. Leads, team membership, role grants and history are preserved. Accepted users can be reactivated through Edit access.</p><div className="form-actions"><button className="btn" type="button" disabled={busy} onClick={() => { setDeleting(null); }}>Cancel</button><button className="btn btn-danger" type="button" disabled={busy} onClick={() => void deactivate()}>{busy ? "Deleting..." : "Confirm delete"}</button></div></section>}
    {inviting && <InviteEditor onClose={() => { setInviting(false); list.reload(); }} onCreated={identity?.is_owner ? memberId => { setInviting(false); setInvitationMember(memberId); list.reload(); } : undefined} />}
    {identity?.is_owner && invitationMember && <InvitationTokenDialog key={invitationMember} memberId={invitationMember} onClose={() => { setInvitationMember(null); list.reload(); }} />}
    {editing && <MemberEditor key={editing.id} member={editing} onClose={() => { setEditing(null); list.reload(); }} />}
    <DataTable data={list.data?.data} rowKey={member => member.id} list={list}
      columns={[
        { id: "name", meta: { width: "200px" }, header: "Name", accessorFn: member => member.display_name, enableSorting: true, cell: ({ row }) => <strong className="user-name-cell">{row.original.display_name}</strong> },
        { id: "email", meta: { width: "250px" }, header: "Email", accessorFn: member => member.email, enableSorting: true },
        { id: "role", meta: { width: "190px" }, header: "Role", enableSorting: false, cell: ({ row }) => { const member = row.original; return <div className="user-role-cell">{member.is_owner ? <Badge>Owner</Badge> : memberRoles(member).map(role => role.name).join(", ") || "—"}{member.id === identity?.membership_id && <Badge variant="info">You</Badge>}</div>; } },
        { id: "level", meta: { width: "70px", align: "center" }, header: "Level", enableSorting: false, cell: ({ row }) => row.original.is_owner ? "—" : memberRoles(row.original).length ? Math.min(...memberRoles(row.original).map(role => role.level)) : "—" },
        { id: "status", meta: { width: "116px" }, header: "Status", accessorFn: member => member.status, enableSorting: true, cell: ({ row }) => <Badge variant={row.original.status === "active" ? "success" : "outline"}>{row.original.status}</Badge> },
        { id: "rights", meta: { width: "190px" }, header: "Rights", enableSorting: false, cell: ({ row }) => row.original.is_owner ? "Full Owner access" : `${row.original.visibility_override || "From roles"} / ${Object.keys(row.original.permission_overrides).length} overrides` },
        { id: "reporting", meta: { width: "170px" }, header: "Reporting to", enableSorting: false, cell: ({ row }) => row.original.is_owner ? "—" : [...new Set(memberRoles(row.original).map(role => role.reports_to_name).filter((name): name is string => Boolean(name)))].join(", ") || "—" },
        { id: "actions", meta: { width: "120px", align: "right" }, header: "Actions", enableSorting: false, cell: ({ row }) => {
          const member = row.original;
          const invited = member.status === "invited";
          const canManage = can("users.manage") && (!member.is_owner || identity?.is_owner);
          return <div className="actions user-row-actions">
            {identity?.is_owner && invited && <IconButton variant="outline" label="View invitation token" onClick={() => setInvitationMember(member.id)}><Icon name="external" /></IconButton>}
            {canManage && !invited && <IconButton variant="outline" label="Edit access" onClick={() => { setEditing(member); setInviting(false); setDeleting(null); }}><Icon name="edit" /></IconButton>}
            {canManage && member.status !== "disabled" && member.id !== identity?.membership_id && <IconButton variant="destructive" label="Delete user" onClick={() => setDeleting(member)}><Icon name="trash" /></IconButton>}
          </div>;
        } },
      ] satisfies ColumnDef<Member, unknown>[]} />
  </>;
}
function InviteEditor({ onClose, onCreated }: { onClose: () => void; onCreated?: (memberId: string) => void }) {
  const [roles, setRoles] = useState<string[]>([]);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const notify = useNotify();
  async function invite(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    try {
      const result = await crm<{ membership_id: string; invitation_token: string }>("/invitations", { method: "POST", body: JSON.stringify({ email: values.get("email"), display_name: values.get("display_name"), role_ids: roles, visibility_override: values.get("visibility_override") || null, landing_page: values.get("landing_page") || null }) });
      if (onCreated) onCreated(result.membership_id);
      else setToken(result.invitation_token);
      notify.success("Deliver the token privately before it expires.", { title: "Invitation created" });
    } catch (error) { notify.error(errorMessage(error), { title: "Invitation could not be created" }); }
    finally { setBusy(false); }
  }
  if (token) return <div className="card editor-card"><h2>Invitation ready</h2><div className="alert alert-info" role="status">Deliver this token privately. It expires in 48 hours and is shown only here. Email delivery is not implemented.</div><Field label="Private invitation token"><textarea className="input mono" readOnly value={token} rows={4} autoComplete="off" /></Field><p>Ask the user to open <code>/accept-invite</code> and paste this token. Do not put it in a URL or public message.</p><button className="btn btn-primary" onClick={() => { setToken(""); onClose(); }}>Done / hide token</button></div>;
  return <form className="card editor-card" onSubmit={invite}><h2>Invite a team member</h2><div className="form-grid"><Field label="Display name"><input className="input" name="display_name" required maxLength={200} /></Field><Field label="Email"><input className="input" name="email" type="email" required /></Field><Field label="Visibility override"><select className="select" name="visibility_override"><option value="">Use role scope</option><option value="own">Own</option><option value="team">Team</option><option value="all">All organization</option></select></Field><LandingPagePicker /></div><SelectionPicker path="/roles" label="Assign active roles" values={roles} onChange={setRoles} /><p className="small muted">Submitting an existing invited email reissues its invitation and invalidates the previous token. Choose roles carefully.</p><div className="form-actions"><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy}>{busy ? "Creating..." : "Create invitation"}</button></div></form>;
}
function MemberEditor({ member, onClose }: { member: Member; onClose: () => void }) {
  const { identity } = useSession();
  const catalog = useResource<{ data: Permission[] }>("/permissions");
  const [roles, setRoles] = useState(member.role_ids);
  const [overrides, setOverrides] = useState<Record<string, boolean>>(member.permission_overrides);
  const [scope, setScope] = useState<Scope | "">(member.visibility_override || "");
  const [busy, setBusy] = useState(false);
  const notify = useNotify();
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    try {
      await crm(`/memberships/${member.id}`, { method: "PUT", body: JSON.stringify({ display_name: values.get("display_name"), status: values.get("status"), role_ids: roles, visibility_override: scope || null, permission_overrides: overrides, landing_page: values.get("landing_page") || null, ...(identity?.is_owner ? { is_owner: values.get("is_owner") === "on" } : {}) }) });
      notify.success(`${values.get("display_name")}'s access was saved.`, { title: "Access updated" });
      onClose();
    } catch (error) { notify.error(errorMessage(error), { title: "Access could not be saved" }); }
    finally { setBusy(false); }
  }
  return <form className="card editor-card" onSubmit={save}><h2>Access: {member.display_name}</h2><ErrorNotice error={catalog.error} /><div className="form-grid">
    <Field label="Display name"><input className="input" name="display_name" required maxLength={200} defaultValue={member.display_name} /></Field>
    <Field label="Login email"><input className="input" type="email" value={member.email} readOnly /><span className="small muted">Shared login identity; email cannot be changed here.</span></Field>
    <Field label="Membership status"><select className="select" name="status" defaultValue={member.status}><option value="active">Active</option><option value="disabled">Disabled (revoke sessions)</option></select></Field><Field label="Visibility override"><select className="select" value={scope} onChange={event => setScope(event.target.value as Scope | "")}><option value="">From roles</option><option value="own">Own</option><option value="team">Team</option><option value="all">All</option></select></Field><LandingPagePicker value={member.landing_page} />{identity?.is_owner && <label className="check-row"><input name="is_owner" type="checkbox" defaultChecked={member.is_owner} />Organization Owner (full access)</label>}</div><SelectionPicker label="Roles" path="/roles" values={roles} onChange={setRoles} /><h3>Direct permission overrides</h3><PermissionGroups catalog={catalog.data?.data || []} overrides={overrides} onOverride={setOverrides} /><p className="small muted">Select all adds direct allows within your grant ceiling; Clear resets a group to role defaults, not denies. Owners retain full access. The final active Owner cannot be demoted or disabled.</p><div className="form-actions"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy || catalog.loading || Boolean(catalog.error)}>{busy ? "Saving..." : "Save access"}</button></div></form>;
}
function Teams() {
  const list = usePaged<Team>("/teams");
  const [editing, setEditing] = useState<Team | "new" | null>(null);
  return <section className="card"><div className="page-header"><div><h2>Organization teams</h2><p className="small muted">Only Owners manage team membership. Team scope includes leads explicitly assigned to a member's active teams.</p></div><button className="btn" onClick={() => setEditing("new")}>+ Create team</button></div><ErrorNotice error={list.error} />{editing && <TeamEditor key={typeof editing === "string" ? "new" : editing.id} team={typeof editing === "string" ? undefined : editing} onClose={() => { setEditing(null); list.reload(); }} />}{list.loading ? <Loading /> : list.data?.data.map(team => <div className="source-row" key={team.id}><span>{team.name} <span className="badge">{team.is_active ? "Active" : "Inactive"}</span></span><span className="muted">{team.membership_ids.length} members</span><button className="btn" onClick={() => setEditing(team)}>Edit</button></div>)}<Pagination list={list} /></section>;
}
function TeamEditor({ team, onClose }: { team?: Team; onClose: () => void }) {
  const [members, setMembers] = useState(team?.membership_ids || []);
  const [busy, setBusy] = useState(false);
  const notify = useNotify();
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    try { await crm(team ? `/teams/${team.id}` : "/teams", { method: team ? "PUT" : "POST", body: JSON.stringify({ name: values.get("name"), is_active: values.get("is_active") === "on", membership_ids: members }) }); notify.success(`${values.get("name")} ${team ? "updated" : "created"}.`, { title: team ? "Team updated" : "Team created" }); onClose(); }
    catch (error) { notify.error(errorMessage(error), { title: "Team could not be saved" }); }
    finally { setBusy(false); }
  }
  return <form className="editor-card" onSubmit={save}><h3>{team ? "Edit team" : "Create team"}</h3><Field label="Team name"><input className="input" name="name" required maxLength={100} defaultValue={team?.name || ""} /></Field><label className="check-row"><input type="checkbox" name="is_active" defaultChecked={team?.is_active ?? true} />Active</label><SelectionPicker label="Active members (maximum 200)" path="/memberships" values={members} onChange={setMembers} /><div className="form-actions"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Save team"}</button></div></form>;
}
