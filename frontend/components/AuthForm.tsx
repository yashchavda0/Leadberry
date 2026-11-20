"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { crm, errorMessage, homeFor, isServiceError } from "@/lib/crm";
import { useSession } from "./Session";
import Icon from "./Icon";
import OrganizationProfileStep from "./OrganizationProfileStep";
import { Button } from "./ui/button";
import { Field } from "./Ui";
import { useNotify } from "./Notifications";

export default function AuthForm({ mode }: { mode: "login" | "onboard" | "invite" }) {
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  const [profileStep, setProfileStep] = useState<{ name: string; timezone: string; home: string } | null>(null);
  const router = useRouter();
  const session = useSession();
  const title = mode === "login" ? "Welcome back" : mode === "onboard" ? "Create your workspace" : "Join your organization";
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const path = mode === "login" ? "/auth/login" : mode === "onboard" ? "/organizations/onboard" : "/auth/accept-invite";
    try {
      await crm(path, { method: "POST", body: JSON.stringify(values) });
      const identity = await session.reload();
      if (identity && mode === "onboard") { notify.success("Your workspace is ready.", { title: "Workspace created" }); setProfileStep({ name: String(values.organization_name), timezone: String(values.timezone), home: homeFor(identity) }); }
      else if (identity) { notify.success(mode === "login" ? "You are signed in." : "You have joined the organization.", { title: mode === "login" ? "Welcome back" : "Invitation accepted" }); router.replace(mode === "invite" ? "/account/setup" : homeFor(identity)); }
      else notify.warning("Sign-in succeeded but the workspace could not load. Retry sign-in or contact your administrator.", { title: "Workspace unavailable" });
    } catch (error) { notify.error(errorMessage(error), { title: isServiceError(error) ? "Service unavailable" : mode === "login" ? "Sign-in failed" : mode === "onboard" ? "Workspace could not be created" : "Invitation could not be accepted", duration: isServiceError(error) ? 10000 : undefined }); }
    finally { setBusy(false); }
  }
  return <div className="auth-container"><aside className="auth-story"><Link href="/login" className="auth-brand">LeadBerry</Link><h1>Every lead.<br />One workspace.</h1><p>Keep conversations organized, give your team the right access, and see your pipeline clearly.</p><div className="auth-points"><p>Organization-isolated lead data</p><p>Owner-controlled roles and permissions</p><p>One secure place for your team</p></div><span className="small">Application code runs locally. PostgreSQL powers your workspace.</span></aside><div className="auth-panel">{profileStep ? <OrganizationProfileStep name={profileStep.name} timezone={profileStep.timezone} onDone={async () => { await session.reload(); router.replace(profileStep.home); }} /> : <form className="card auth-form" onSubmit={submit}><span className="eyebrow">YOUR CRM WORKSPACE</span><h1>{title}</h1><p className="muted">{mode === "invite" ? "Paste the private invitation provided by your administrator." : "Use your organization's unique workspace slug."}</p>
    {mode !== "invite" && <Field label="Organization slug" hint="3–63 lowercase letters, numbers and hyphens."><input className="input" name="organization_slug" required pattern="[a-z0-9][a-z0-9-]{2,62}" placeholder="acme-sales" autoComplete="organization" /></Field>}
    {mode === "onboard" && <><Field label="Organization name"><input className="input" name="organization_name" required maxLength={200} /></Field><Field label="Your full name"><input className="input" name="full_name" required maxLength={200} autoComplete="name" /></Field><Field label="Timezone"><input className="input" name="timezone" defaultValue="Asia/Kolkata" required /></Field></>}
    {mode !== "invite" && <Field label="Email"><input className="input" name="email" type="email" required autoComplete="username" /></Field>}
    {mode === "invite" && <Field label="Invitation token"><textarea className="input" name="invitation_token" required minLength={100} maxLength={250} autoComplete="off" rows={4} /></Field>}
    <Field label={mode === "invite" ? "Your password" : "Password"} hint={mode === "invite" ? "Existing users must use their current password. New users choose a password of 12–128 characters." : "12–128 characters."}><input className="input" name="password" type="password" required minLength={12} maxLength={128} autoComplete={mode === "login" ? "current-password" : "new-password"} /></Field>
    <button className="btn btn-primary full-width" disabled={busy || session.pending}>{busy || session.pending ? "Please wait..." : mode === "login" ? "Sign in" : mode === "onboard" ? "Create organization" : "Accept invitation"}</button>
    <div className="auth-alt"><span className="auth-alt-title">{mode === "login" ? "New here?" : "Other options"}</span>
      <div className="auth-alt-grid">
        {mode !== "login" && <Button variant="outline" asChild><Link href="/login"><Icon name="chevronRight" />Sign in</Link></Button>}
        {mode !== "onboard" && <Button variant="outline" asChild><Link href="/onboarding"><Icon name="plus" />Create workspace</Link></Button>}
        {mode !== "invite" && <Button variant="outline" asChild><Link href="/accept-invite"><Icon name="leads" />Accept invitation</Link></Button>}
      </div>
    </div>
    <p className="small muted">Password recovery and MFA setup are not available yet. Contact your administrator if you cannot sign in.</p>
  </form>}</div></div>;
}
