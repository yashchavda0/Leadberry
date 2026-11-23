"use client";

import Icon from "@/components/Icon";
import { useNotify } from "@/components/Notifications";
import ProfileForm, { type Profile } from "@/components/ProfileForm";
import { useSession } from "@/components/Session";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tip } from "@/components/ui/tip";
import { useResource } from "@/lib/hooks";

export default function AccountPage() {
  const { identity, organization } = useSession();
  const notify = useNotify();
  const profile = useResource<Profile>("/auth/profile", true);
  const person = profile.data;
  const name = person?.display_name || "";
  const initials = name.split(/\s+/).filter(Boolean).map(word => word[0]).join("").slice(0, 2).toUpperCase() || "?";
  async function copy(label: string, value: string) {
    try { await navigator.clipboard.writeText(value); notify.success(`${label} copied.`); }
    catch { notify.error("Copy is not available in this browser."); }
  }
  const detail = (label: string, value: string, copyable?: boolean) => <div className="account-detail" key={label}>
    <small>{label}</small>
    <span><strong className={copyable ? "account-id" : undefined}>{value}</strong>{copyable && <Tip label={`Copy ${label.toLowerCase()}`}><button type="button" className="account-copy" aria-label={`Copy ${label.toLowerCase()}`} onClick={() => void copy(label, value)}><Icon name="edit" size={14} /></button></Tip>}</span>
  </div>;
  return <>
    <Card className="account-hero">
      <div className="org-avatar" aria-hidden="true">{initials}</div>
      <div className="account-hero-text">
        <span className="eyebrow">MY ACCOUNT</span>
        <h1>{name || "Your profile"}</h1>
        <div className="org-hero-meta">
          {person?.job_title && <span className="small muted">{person.job_title}</span>}
          <span className="small muted">{person?.email}</span>
          <Badge variant="outline">{organization?.name}</Badge>
          {identity?.is_owner && <Badge>Owner</Badge>}
        </div>
      </div>
    </Card>

    <div className={`account-layout${identity?.is_owner ? "" : " single"}`}>
      <ProfileForm profile={person} onSaved={profile.reload} />
      {identity?.is_owner && <div className="account-side">
        <Card>
          <CardHeader><CardTitle>Account details</CardTitle><CardDescription>Reference information for support and integrations.</CardDescription></CardHeader>
          <CardContent className="account-details">
            {detail("Organization", organization?.name || "")}
            {detail("Workspace slug", organization?.slug || "")}
            {detail("Role", "Organization Owner")}
            {identity && detail("Membership ID", identity.membership_id, true)}
            {identity && detail("Organization ID", identity.organization_id, true)}
          </CardContent>
        </Card>
      </div>}
    </div>
  </>;
}
