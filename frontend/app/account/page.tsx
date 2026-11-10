"use client";

import { useState } from "react";
import { useSession } from "@/components/Session";
import { useNotify } from "@/components/Notifications";
import { crm, errorMessage } from "@/lib/crm";

export default function AccountPage() {
  const { identity, organization, logout, reload } = useSession();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  async function action(refresh: boolean) {
    setBusy(true);
    try {
      if (refresh) { await crm("/auth/refresh", { method: "POST" }); await reload(); notify.success("The original session expiry is unchanged.", { title: "Session token rotated" }); }
      else { await logout(); notify.info("You have been signed out."); }
    } catch (error) { notify.error(errorMessage(error), { title: refresh ? "Token could not be rotated" : "Sign-out failed" }); }
    finally { setBusy(false); }
  }
  return <><div className="page-header"><div><span className="eyebrow">YOUR ACCESS</span><h1>My account</h1></div><button className="btn btn-danger" disabled={busy} onClick={() => void action(false)}>Sign out</button></div><div className="card"><div className="detail-grid"><div><div className="field-label">Organization</div>{organization?.name}</div><div><div className="field-label">Access type</div>{identity?.is_owner ? "Protected Owner / full access" : "Organization member"}</div><div><div className="field-label">Lead scope</div>{identity?.data_scope}</div><div><div className="field-label">Membership ID</div><code>{identity?.membership_id}</code></div></div><h2>Effective permissions</h2><div className="tag-list">{identity?.permissions.length ? identity.permissions.map(permission => <span key={permission} className="tag mono">{permission}</span>) : <p className="muted">No page permissions. Ask an Owner to assign a role.</p>}</div><h2>Session</h2><p className="muted">Credentials are kept in HttpOnly cookies, not browser storage. Sessions have a fixed lifetime. Access changes are enforced by the API on every request.</p><button className="btn" disabled={busy} onClick={() => void action(true)}>Rotate session token</button><p className="small muted">Do not rotate simultaneously in multiple tabs: replay protection may revoke the session. Sign in with another organization slug to switch workspaces.</p></div></>;
}
