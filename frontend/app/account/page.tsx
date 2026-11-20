"use client";

import { useMemo, useState } from "react";
import Icon from "@/components/Icon";
import ProfileForm from "@/components/ProfileForm";
import { useNotify } from "@/components/Notifications";
import SearchInput from "@/components/SearchInput";
import { useSession } from "@/components/Session";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tip } from "@/components/ui/tip";
import { crm, errorMessage } from "@/lib/crm";

const SCOPES = { own: "Own leads", team: "Team leads", all: "All leads" } as const;

export default function AccountPage() {
  const { identity, organization, logout, reload } = useSession();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  async function action(refresh: boolean) {
    setBusy(true);
    try {
      if (refresh) { await crm("/auth/refresh", { method: "POST" }); await reload(); notify.success("The original session expiry is unchanged.", { title: "Session token rotated" }); }
      else { await logout(); notify.info("You have been signed out."); }
    } catch (error) { notify.error(errorMessage(error), { title: refresh ? "Token could not be rotated" : "Sign-out failed" }); }
    finally { setBusy(false); }
  }
  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); notify.success("Membership ID copied."); }
    catch { notify.error("Copy is not available in this browser."); }
  }
  const groups = useMemo(() => {
    const term = query.trim().toLowerCase();
    const map = new Map<string, string[]>();
    for (const code of identity?.permissions || []) {
      if (term && !code.toLowerCase().includes(term)) continue;
      const [module, ...rest] = code.split(".");
      map.set(module, [...(map.get(module) || []), rest.join(".") || code]);
    }
    return [...map].sort(([a], [b]) => a.localeCompare(b));
  }, [identity?.permissions, query]);
  const initials = (organization?.name || "?").split(/\s+/).map(word => word[0]).join("").slice(0, 2).toUpperCase();
  const total = identity?.permissions.length || 0;
  return <>
    <Card className="account-hero">
      <div className="org-avatar" aria-hidden="true">{initials}</div>
      <div className="account-hero-text">
        <span className="eyebrow">YOUR ACCESS</span>
        <h1>My account</h1>
        <div className="org-hero-meta">
          <span className="small muted">Signed in to <strong>{organization?.name}</strong></span>
          <Badge variant={identity?.is_owner ? "default" : "outline"}>{identity?.is_owner ? "Owner" : "Member"}</Badge>
          <Badge variant="info">{SCOPES[identity?.data_scope || "own"]}</Badge>
        </div>
      </div>
      <Button variant="outline" disabled={busy} onClick={() => void action(false)}><Icon name="close" />Sign out</Button>
    </Card>

    <ProfileForm />

    <div className="account-tiles">
      <div className="account-tile"><span className="org-tile-icon"><Icon name="check" size={18} /></span><span><small>Access type</small><strong>{identity?.is_owner ? "Full access (Owner)" : "Organization member"}</strong></span></div>
      <div className="account-tile"><span className="org-tile-icon"><Icon name="leads" size={18} /></span><span><small>Lead visibility</small><strong>{SCOPES[identity?.data_scope || "own"]}</strong></span></div>
      <div className="account-tile"><span className="org-tile-icon"><Icon name="settings" size={18} /></span><span><small>Permissions</small><strong>{identity?.is_owner ? "All" : total}</strong></span></div>
      <div className="account-tile"><span className="org-tile-icon"><Icon name="filter" size={18} /></span><span><small>Membership ID</small><strong className="account-id">{identity?.membership_id}</strong></span>
        {identity && <Tip label="Copy ID"><button type="button" className="account-copy" aria-label="Copy membership ID" onClick={() => void copy(identity.membership_id)}><Icon name="edit" size={14} /></button></Tip>}</div>
    </div>

    <Card>
      <CardHeader><CardTitle>Effective permissions</CardTitle><CardDescription>What you can do after combining your roles and any personal overrides.</CardDescription></CardHeader>
      <CardContent>
        {identity?.is_owner && <div className="alert alert-info">Owners always have full access, whatever is listed below.</div>}
        {total === 0 ? <p className="muted">No page permissions yet. Ask an Owner to assign you a role.</p> : <>
          <SearchInput value={query} onChange={setQuery} placeholder="Search your permissions" />
          <div className="account-perms">{groups.length ? groups.map(([module, actions]) => <details key={module} open>
            <summary><span>{module.replaceAll("_", " ")}</span><span className="small muted">{actions.length}</span></summary>
            <div className="perm-chips">{actions.map(action => <span key={action} className="perm-chip">{action.replaceAll("_", " ")}</span>)}</div>
          </details>) : <p className="small muted">No permissions match.</p>}</div>
        </>}
      </CardContent>
    </Card>

    <Card>
      <CardHeader><CardTitle>Session</CardTitle><CardDescription>How your sign-in is kept secure.</CardDescription></CardHeader>
      <CardContent className="account-session">
        <p className="muted">Your login lives in secure HttpOnly cookies, not in browser storage, and sessions have a fixed lifetime. Access changes are checked by the server on every request.</p>
        <div className="account-session-actions"><Button variant="outline" disabled={busy} onClick={() => void action(true)}><Icon name="refresh" />Rotate session token</Button></div>
        <p className="small muted">Don&apos;t rotate in several tabs at once, because replay protection may end the session. To switch workspaces, sign in with another organization slug.</p>
      </CardContent>
    </Card>
  </>;
}
