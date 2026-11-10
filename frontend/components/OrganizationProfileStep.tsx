"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Ui";
import { useNotify } from "@/components/Notifications";
import { COMPANY_SIZES, COUNTRIES, INDUSTRIES } from "@/lib/organization";
import { crm, errorMessage } from "@/lib/crm";

// Optional step shown right after signup; skipping keeps the workspace as created.
export default function OrganizationProfileStep({ name, timezone, onDone }: { name: string; timezone: string; onDone: () => void }) {
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try { await crm("/organizations/me", { method: "PUT", body: JSON.stringify({ name, timezone, ...values }) }); notify.success("You can edit these any time in Organization settings.", { title: "Company details saved" }); onDone(); }
    catch (problem) { notify.error(errorMessage(problem), { title: "Details could not be saved" }); setBusy(false); }
  }
  return <form className="card auth-form" onSubmit={save}>
    <span className="eyebrow">WORKSPACE CREATED</span>
    <h1>Tell us about your company</h1>
    <p className="muted">Optional. You can add or change these any time in Organization settings.</p>
    <div className="form-grid">
      <Field label="Industry"><select className="select" name="industry" defaultValue=""><option value="">Select industry</option>{INDUSTRIES.map(item => <option key={item} value={item}>{item}</option>)}</select></Field>
      <Field label="Company size"><select className="select" name="company_size" defaultValue=""><option value="">Select size</option>{COMPANY_SIZES.map(item => <option key={item} value={item}>{item} people</option>)}</select></Field>
      <Field label="Website"><input className="input" name="website" type="url" maxLength={300} placeholder="https://" /></Field>
      <Field label="Business phone"><input className="input" name="business_phone" type="tel" maxLength={20} /></Field>
      <Field label="City"><input className="input" name="city" maxLength={100} /></Field>
      <Field label="Country"><select className="select" name="country" defaultValue="IN">{COUNTRIES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></Field>
    </div>
    <div className="form-actions"><Button type="button" variant="ghost" disabled={busy} onClick={onDone}>Skip for now</Button><Button type="submit" disabled={busy}>{busy ? "Saving..." : "Save and continue"}</Button></div>
  </form>;
}
