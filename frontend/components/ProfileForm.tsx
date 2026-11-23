"use client";

import { useState } from "react";
import { useNotify } from "@/components/Notifications";
import { useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { crm, errorMessage } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

export type Profile = {
  display_name: string; email: string; phone: string | null; job_title: string | null;
  date_of_birth: string | null; gender: string | null; address: string | null; city: string | null; state: string | null;
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const GENDERS: [string, string][] = [["female", "Female"], ["male", "Male"], ["non_binary", "Non-binary"], ["prefer_not_to_say", "Prefer not to say"]];

// Day / month / year selects avoid the awkward browser date input and make far-back dates easy to pick.
function BirthDate({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [year, month, day] = value ? value.split("-") : ["", "", ""];
  const thisYear = new Date().getFullYear();
  const years = Array.from({ length: thisYear - 1939 }, (_, index) => String(thisYear - index));
  const daysInMonth = year && month ? new Date(Number(year), Number(month), 0).getDate() : 31;
  const set = (next: { year?: string; month?: string; day?: string }) => {
    const y = next.year ?? year, m = next.month ?? month, d = next.day ?? day;
    onChange(y && m && d ? `${y}-${m}-${String(Math.min(Number(d), new Date(Number(y), Number(m), 0).getDate())).padStart(2, "0")}` : y || m || d ? `${y}-${m}-${d}` : "");
  };
  return <div className="dob-fields">
    <select className="select" aria-label="Day" value={day} onChange={event => set({ day: event.target.value })}><option value="">Day</option>{Array.from({ length: daysInMonth }, (_, index) => <option key={index} value={String(index + 1).padStart(2, "0")}>{index + 1}</option>)}</select>
    <select className="select" aria-label="Month" value={month} onChange={event => set({ month: event.target.value })}><option value="">Month</option>{MONTHS.map((name, index) => <option key={name} value={String(index + 1).padStart(2, "0")}>{name}</option>)}</select>
    <select className="select" aria-label="Year" value={year} onChange={event => set({ year: event.target.value })}><option value="">Year</option>{years.map(item => <option key={item} value={item}>{item}</option>)}</select>
  </div>;
}

export default function ProfileForm({ profile, onSaved, onDone }: { profile?: Profile | null; onSaved?: () => void; onDone?: () => void }) {
  const { reload } = useSession();
  const notify = useNotify();
  const own = useResource<Profile>(profile ? null : "/auth/profile");
  const data = profile ?? own.data;
  const [busy, setBusy] = useState(false);
  const [dob, setDob] = useState<string | null>(null);
  const birth = dob ?? data?.date_of_birth ?? "";

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const text = (key: string) => String(values.get(key) || "").trim() || null;
    if (birth && birth.split("-").some(part => !part)) { notify.warning("Choose the day, month and year, or clear all three.", { title: "Date of birth is incomplete" }); return; }
    setBusy(true);
    try {
      await crm("/auth/profile", { method: "PUT", body: JSON.stringify({
        display_name: String(values.get("display_name")).trim(), phone: text("phone"), job_title: text("job_title"),
        date_of_birth: birth || null, gender: text("gender"), address: text("address"), city: text("city"), state: text("state"),
      }) });
      await reload();
      notify.success("Your personal details were saved.", { title: "Profile updated" });
      onSaved?.();
      onDone?.();
    } catch (error) { notify.error(errorMessage(error), { title: "Profile could not be saved" }); }
    finally { setBusy(false); }
  }

  return <Card>
    <CardHeader><CardTitle>{onDone ? "Complete your profile" : "Personal information"}</CardTitle><CardDescription>Your colleagues see your name and job title. Everything else is visible only to you and your administrators.</CardDescription></CardHeader>
    <CardContent>
      <ErrorNotice error={own.error} />
      {data ? <form onSubmit={save} className="profile-form" key={data.display_name + (data.date_of_birth ?? "")}>
        <section><h3>Basic details</h3>
          <div className="form-grid">
            <Field label="Full name"><input className="input" name="display_name" autoComplete="name" defaultValue={data.display_name} required maxLength={200} /></Field>
            <Field label="Gender"><select className="select" name="gender" defaultValue={data.gender ?? ""}><option value="">Select</option>{GENDERS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
            <Field label="Date of birth"><BirthDate value={birth} onChange={setDob} /></Field>
            <Field label="Job title"><input className="input" name="job_title" autoComplete="organization-title" defaultValue={data.job_title ?? ""} maxLength={120} placeholder="e.g. Sales manager" /></Field>
          </div></section>
        <section><h3>Contact</h3>
          <div className="form-grid">
            <Field label="Email" hint="This is your sign-in email."><input className="input" type="email" value={data.email} readOnly /></Field>
            <Field label="Phone"><input className="input" name="phone" type="tel" autoComplete="tel" defaultValue={data.phone ?? ""} maxLength={40} placeholder="+91 98765 43210" /></Field>
          </div></section>
        <section><h3>Location</h3>
          <div className="form-grid">
            <div className="span-2"><Field label="Address"><input className="input" name="address" autoComplete="street-address" defaultValue={data.address ?? ""} maxLength={300} /></Field></div>
            <Field label="City"><input className="input" name="city" autoComplete="address-level2" defaultValue={data.city ?? ""} maxLength={100} /></Field>
            <Field label="State"><input className="input" name="state" autoComplete="address-level1" defaultValue={data.state ?? ""} maxLength={100} /></Field>
          </div></section>
        <div className="form-actions">
          {onDone && <Button type="button" variant="outline" disabled={busy} onClick={onDone}>Skip for now</Button>}
          <Button type="submit" disabled={busy}>{busy ? "Saving..." : onDone ? "Save and continue" : "Save changes"}</Button>
        </div>
      </form> : !own.error && <Loading />}
    </CardContent>
  </Card>;
}
