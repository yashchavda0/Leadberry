"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ConfirmEmailDialog from "@/components/platform/ConfirmEmailDialog";
import GeneratedPasswordDialog from "@/components/platform/GeneratedPasswordDialog";
import { usePlatformSession } from "@/components/platform/PlatformLayout";
import Icon from "@/components/Icon";
import { useNotify } from "@/components/Notifications";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { crm, errorMessage, type Page, type PlatformOrganization, type PlatformUser } from "@/lib/crm";

type PendingAction = { user: PlatformUser; kind: "disable" | "enable" | "password" } | null;
type GeneratedPassword = { password: string; email: string } | null;

function dateInput(value: string | null) {
  return value ? new Date(value).toISOString().slice(0, 16) : "";
}
function dateValue(value: FormDataEntryValue | null) {
  return typeof value === "string" && value ? new Date(value).toISOString() : null;
}

export default function OrganizationDetailPage() {
  const { organizationId } = useParams<{ organizationId: string }>();
  const { operator } = usePlatformSession();
  const notify = useNotify();
  const [organization, setOrganization] = useState<PlatformOrganization | null>(null);
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([null]);
  const cursor = cursorHistory[cursorHistory.length - 1];
  const [search, setSearch] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [generatedPassword, setGeneratedPassword] = useState<GeneratedPassword>(null);

  if (!operator) return <Loading />;
  const isAdmin = operator.access_level === "administrator";

  async function loadOrganization() {
    setError("");
    try {
      setOrganization(await crm<PlatformOrganization>(`/platform/organizations/${organizationId}`));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }
  async function loadUsers(after: string | null = cursor) {
    const query = new URLSearchParams({ limit: "50" });
    if (after) query.set("after", after);
    if (search.trim()) query.set("search", search.trim());
    try {
      const result = await crm<Page<PlatformUser>>(`/platform/organizations/${organizationId}/users?${query}`);
      setUsers(result.data);
      setNextCursor(result.next_cursor);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all([
      crm<PlatformOrganization>(`/platform/organizations/${organizationId}`),
      crm<Page<PlatformUser>>(`/platform/organizations/${organizationId}/users?limit=50`),
    ]).then(([org, members]) => {
      if (active) {
        setOrganization(org);
        setUsers(members.data);
        setNextCursor(members.next_cursor);
      }
    }).catch(reason => {
      if (active) setError(errorMessage(reason));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [organizationId]);

  async function saveOrganization(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization) return;
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const updated = await crm<PlatformOrganization>(`/platform/organizations/${organizationId}`, {
        method: "PUT",
        body: JSON.stringify({
          status: form.get("status"),
          subscription_plan: form.get("subscription_plan"),
          subscription_status: form.get("subscription_status"),
          subscription_started_at: dateValue(form.get("subscription_started_at")),
          subscription_ends_at: dateValue(form.get("subscription_ends_at")),
          export_access_until: dateValue(form.get("export_access_until")),
          max_users: Number(form.get("max_users")),
        }),
      });
      setOrganization(updated);
      notify.success("Organization access and subscription updated.");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  async function confirmAction(email: string) {
    if (!pendingAction) return;
    if (pendingAction.kind === "password") {
      const result = await crm<{ temporary_password: string }>(
        `/platform/organizations/${organizationId}/users/${pendingAction.user.id}/generate-password`,
        { method: "POST", body: JSON.stringify({ confirm_email: email }) },
      );
      setGeneratedPassword({ password: result.temporary_password, email: pendingAction.user.email });
      notify.success("Temporary password generated. It will only be shown once.");
      return;
    }
    await crm(`/platform/organizations/${organizationId}/users/${pendingAction.user.id}`, {
      method: "PUT",
      body: JSON.stringify({ status: pendingAction.kind === "disable" ? "disabled" : "active", confirm_email: email }),
    });
    notify.success(pendingAction.kind === "disable" ? "User access revoked." : "User access restored.");
    await Promise.all([loadOrganization(), loadUsers()]);
  }

  if (loading) return <Loading />;
  if (!organization) return <><ErrorNotice error={error || "Organization not found."} onRetry={() => void loadOrganization()} what="organization" /><Button variant="outline" asChild><Link href="/platform">Back to organizations</Link></Button></>;

  return <>
    <header className="platform-page-header">
      <div><Link className="small muted" href="/platform"><Icon name="chevronLeft" size={14} /> Organizations</Link><h1>{organization.name}</h1><p>{organization.slug} · Created {new Date(organization.created_at).toLocaleDateString()}</p></div>
      <span className={`platform-state ${organization.status}`}>{organization.status}</span>
    </header>
    <ErrorNotice error={error} />
    <div className="platform-detail-grid">
      <section className="platform-section">
        <h2>Subscription and access</h2>
        {isAdmin ? <form onSubmit={saveOrganization}>
          <div className="platform-form-grid">
            <Field label="Organization access"><select className="select" name="status" defaultValue={organization.status}><option value="active">Active</option><option value="suspended">Suspended</option><option value="closed">Closed</option></select></Field>
            <Field label="Plan"><input className="input" name="subscription_plan" defaultValue={organization.subscription_plan} maxLength={80} required /></Field>
            <Field label="Subscription status"><select className="select" name="subscription_status" defaultValue={organization.subscription_status}><option value="trialing">Trialing</option><option value="active">Active</option><option value="past_due">Past due</option><option value="expired">Expired</option><option value="canceled">Canceled</option></select></Field>
            <Field label="Maximum users"><input className="input" name="max_users" type="number" min="1" max="100000" defaultValue={organization.max_users} required /></Field>
            <Field label="Subscription starts"><input className="input" name="subscription_started_at" type="datetime-local" defaultValue={dateInput(organization.subscription_started_at)} /></Field>
            <Field label="Subscription ends"><input className="input" name="subscription_ends_at" type="datetime-local" defaultValue={dateInput(organization.subscription_ends_at)} /></Field>
            <Field label="Export-only until" hint="After expiration, users can read and export data until this date."><input className="input" name="export_access_until" type="datetime-local" defaultValue={dateInput(organization.export_access_until)} /></Field>
          </div>
          <Button type="submit" disabled={saving}>{saving ? "Saving..." : "Save subscription"}</Button>
        </form> : <dl className="platform-readonly-list">
          <div><dt>Plan</dt><dd>{organization.subscription_plan}</dd></div><div><dt>Subscription</dt><dd>{organization.subscription_status}</dd></div><div><dt>User limit</dt><dd>{organization.max_users}</dd></div><div><dt>Subscription ends</dt><dd>{organization.subscription_ends_at ? new Date(organization.subscription_ends_at).toLocaleString() : "No end date"}</dd></div><div><dt>Export-only until</dt><dd>{organization.export_access_until ? new Date(organization.export_access_until).toLocaleString() : "Not set"}</dd></div>
        </dl>}
      </section>
      <section className="platform-section">
        <h2>Organization users <span className="small muted">{organization.user_count} / {organization.max_users}</span></h2>
        <div className="platform-toolbar"><label className="sr-only" htmlFor="user-search">Search users</label><input id="user-search" className="input" value={search} placeholder="Search name or email" onChange={event => { setSearch(event.target.value); setCursorHistory([null]); }} /><Button variant="outline" size="icon" aria-label="Search users" title="Search users" onClick={() => void loadUsers(null)}><Icon name="search" size={16} /></Button></div>
        <div className="platform-table"><table>
          <thead><tr><th>User</th><th>Status</th><th>Role</th>{isAdmin && <th>Actions</th>}</tr></thead>
          <tbody>{users.map(user => <tr key={user.id}>
            <td><span className="platform-row-title"><strong>{user.display_name}</strong><small>{user.email}</small></span></td>
            <td><span className={`platform-state ${user.status}`}>{user.status}</span></td>
            <td>{user.is_owner ? "Owner" : "Member"}</td>
            {isAdmin && <td><div className="platform-user-actions">
              {user.status !== "invited" && <Button variant="outline" size="sm" onClick={() => setPendingAction({ user, kind: user.status === "active" ? "disable" : "enable" })}>{user.status === "active" ? "Revoke" : "Restore"}</Button>}
              <Button variant="outline" size="sm" onClick={() => setPendingAction({ user, kind: "password" })}>Generate password</Button>
            </div></td>}
          </tr>)}</tbody>
        </table></div>
        <div className="platform-pagination"><span>{users.length} users on this page</span><div className="actions"><Button variant="outline" size="sm" disabled={cursorHistory.length < 2} onClick={() => { const history = cursorHistory.slice(0, -1); setCursorHistory(history); void loadUsers(history[history.length - 1]); }}><Icon name="chevronLeft" size={15} />Previous</Button><Button variant="outline" size="sm" disabled={!nextCursor} onClick={() => { setCursorHistory(history => [...history, nextCursor]); void loadUsers(nextCursor); }}>Next<Icon name="chevronRight" size={15} /></Button></div></div>
      </section>
    </div>
    {pendingAction && <ConfirmEmailDialog
      title={pendingAction.kind === "password" ? "Generate a temporary password?" : pendingAction.kind === "disable" ? "Revoke user access?" : "Restore user access?"}
      description={pendingAction.kind === "password" ? `This replaces the user's current password, signs out their sessions, and requires a password change at next sign-in.` : pendingAction.kind === "disable" ? "The user will be signed out and will no longer be able to access this organization." : "The user will regain access to this organization."}
      email={pendingAction.user.email}
      actionLabel={pendingAction.kind === "password" ? "Generate password" : pendingAction.kind === "disable" ? "Revoke access" : "Restore access"}
      onConfirm={confirmAction}
      onClose={() => setPendingAction(null)}
    />}
    {generatedPassword && <GeneratedPasswordDialog password={generatedPassword.password} onClose={() => setGeneratedPassword(null)} />}
  </>;
}