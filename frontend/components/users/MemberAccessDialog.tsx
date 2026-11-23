"use client";

import { useState } from "react";
import Icon from "@/components/Icon";
import LandingPagePicker from "@/components/LandingPagePicker";
import { useNotify } from "@/components/Notifications";
import { useSession } from "@/components/Session";
import { ErrorNotice, Field } from "@/components/Ui";
import PermissionOverrides from "@/components/users/PermissionOverrides";
import RolePicker from "@/components/users/RolePicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { crm, errorMessage, type Member, type Permission, type Scope } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

// Large two-part dialog: tabs scroll inside, the footer with Save stays visible at all times.
export default function MemberAccessDialog({ member, onClose }: { member: Member; onClose: () => void }) {
  const { identity } = useSession();
  const notify = useNotify();
  const catalog = useResource<{ data: Permission[] }>("/permissions");
  const [tab, setTab] = useState("account");
  const [roles, setRoles] = useState(member.role_ids);
  const [overrides, setOverrides] = useState<Record<string, boolean>>(member.permission_overrides);
  const [scope, setScope] = useState<Scope | "">(member.visibility_override || "");
  const [busy, setBusy] = useState(false);
  const overrideCount = Object.keys(overrides).length;
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
  const initials = member.display_name.split(/\s+/).filter(Boolean).map(word => word[0]).join("").slice(0, 2).toUpperCase();
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent size="xl" className="ui-dialog-split" hideClose>
      <form className="split-form" onSubmit={save}>
        <header className="split-head">
          <span className="org-avatar" aria-hidden="true">{initials}</span>
          <div><DialogTitle>{member.display_name}</DialogTitle><DialogDescription>{member.email} · manage roles, visibility and personal permissions</DialogDescription></div>
          <button type="button" className="ui-dialog-close" aria-label="Close" onClick={onClose}><Icon name="close" /></button>
        </header>
        <Tabs value={tab} onValueChange={setTab} className="split-tabs">
          <TabsList className="split-tablist">
            <TabsTrigger value="account"><Icon name="user" size={16} />Account</TabsTrigger>
            <TabsTrigger value="roles"><Icon name="leads" size={16} />Roles <Badge variant={roles.length ? "default" : "outline"}>{roles.length}</Badge></TabsTrigger>
            <TabsTrigger value="overrides"><Icon name="settings" size={16} />Permission overrides <Badge variant={overrideCount ? "default" : "outline"}>{overrideCount}</Badge></TabsTrigger>
          </TabsList>
          <div className="split-body">
            <ErrorNotice error={catalog.error} />
            <TabsContent value="account" forceMount className="split-pane">
              <div className="form-grid">
                <Field label="Display name"><input className="input" name="display_name" required maxLength={200} defaultValue={member.display_name} /></Field>
                <Field label="Login email" hint="Shared login identity; email cannot be changed here."><input className="input" type="email" value={member.email} readOnly /></Field>
                <Field label="Membership status"><select className="select" name="status" defaultValue={member.status}><option value="active">Active</option><option value="disabled">Disabled (revoke sessions)</option></select></Field>
                <Field label="Lead visibility override"><select className="select" value={scope} onChange={event => setScope(event.target.value as Scope | "")}><option value="">From roles</option><option value="own">Own leads</option><option value="team">Team leads</option><option value="all">All leads</option></select></Field>
                <LandingPagePicker value={member.landing_page} />
                {identity?.is_owner && <label className="check-row"><input name="is_owner" type="checkbox" defaultChecked={member.is_owner} />Organization Owner (full access)</label>}
              </div>
              <p className="small muted">The final active Owner cannot be demoted or disabled.</p>
            </TabsContent>
            <TabsContent value="roles" forceMount className="split-pane"><RolePicker values={roles} onChange={setRoles} /></TabsContent>
            <TabsContent value="overrides" forceMount className="split-pane">{catalog.loading ? <p className="muted">Loading permissions...</p> : <PermissionOverrides catalog={catalog.data?.data || []} overrides={overrides} onChange={setOverrides} />}</TabsContent>
          </div>
        </Tabs>
        <footer className="split-foot">
          <span className="small muted">{roles.length} {roles.length === 1 ? "role" : "roles"} · {overrideCount} personal {overrideCount === 1 ? "override" : "overrides"}</span>
          <div><Button type="button" variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" disabled={busy || catalog.loading || Boolean(catalog.error)}>{busy ? "Saving..." : "Save access"}</Button></div>
        </footer>
      </form>
    </DialogContent>
  </Dialog>;
}
