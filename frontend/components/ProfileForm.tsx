"use client";

import { useState } from "react";
import { useNotify } from "@/components/Notifications";
import { useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { crm, errorMessage } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

type Profile = { display_name: string; email: string; phone: string | null; job_title: string | null };

export default function ProfileForm({ onDone }: { onDone?: () => void }) {
  const { reload } = useSession();
  const notify = useNotify();
  const profile = useResource<Profile>("/auth/profile");
  const [busy, setBusy] = useState(false);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await crm("/auth/profile", { method: "PUT", body: JSON.stringify({
        display_name: String(values.get("display_name")).trim(),
        phone: String(values.get("phone")).trim() || null,
        job_title: String(values.get("job_title")).trim() || null,
      }) });
      await reload();
      notify.success("Your personal details were saved.", { title: "Profile updated" });
      onDone?.();
    } catch (error) { notify.error(errorMessage(error), { title: "Profile could not be saved" }); }
    finally { setBusy(false); }
  }

  return <Card>
    <CardHeader><CardTitle>{onDone ? "Complete your profile" : "Personal profile"}</CardTitle></CardHeader>
    <CardContent>
      <ErrorNotice error={profile.error} />
      {profile.data ? <form onSubmit={save}>
        <div className="form-grid">
          <Field label="Display name"><input className="input" name="display_name" autoComplete="name" defaultValue={profile.data.display_name} required maxLength={200} /></Field>
          <Field label="Sign-in email"><input className="input" type="email" value={profile.data.email} readOnly /></Field>
          <Field label="Phone (optional)"><input className="input" name="phone" type="tel" autoComplete="tel" defaultValue={profile.data.phone ?? ""} maxLength={40} /></Field>
          <Field label="Job title (optional)"><input className="input" name="job_title" autoComplete="organization-title" defaultValue={profile.data.job_title ?? ""} maxLength={120} /></Field>
        </div>
        <div className="form-actions">
          {onDone && <Button type="button" variant="outline" disabled={busy} onClick={onDone}>Skip optional details</Button>}
          <Button type="submit" disabled={busy}>{busy ? "Saving..." : onDone ? "Save and continue" : "Save profile"}</Button>
        </div>
      </form> : !profile.error && <Loading />}
    </CardContent>
  </Card>;
}