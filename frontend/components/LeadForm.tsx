"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { crm, errorMessage, type Lead, type LeadCustomField, type Status } from "@/lib/crm";
import { useResource } from "@/lib/hooks";
import { useSession } from "./Session";
import { ErrorNotice, Field, Loading } from "./Ui";
import SelectionPicker from "./SelectionPicker";

function localDate(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function LeadForm({ lead }: { lead?: Lead }) {
  const { can, identity } = useSession();
  const options = useResource<{ statuses: (Status & { required_fields?: string[]; is_default?: boolean })[]; custom_fields: LeadCustomField[] }>("/leads/options");
  const [assignee, setAssignee] = useState(lead?.assigned_membership_id ? [lead.assigned_membership_id] : identity?.membership_id ? [identity.membership_id] : []);
  const [statusId, setStatusId] = useState(lead?.status_id || "");
  const [team, setTeam] = useState(lead?.team_id ? [lead.team_id] : []);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  const pii = can("leads.pii.view");
  const effectiveStatusId = statusId || lead?.status_id || options.data?.statuses.find(status => status.is_default)?.id || "";
  const statusRequired = options.data?.statuses.find(status => status.id === effectiveStatusId)?.required_fields || [];
  const isRequired = (key: string) => statusRequired.includes(key);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      const formData = new FormData(event.currentTarget);
      const values = Object.fromEntries(formData);
      const custom: Record<string, string | number | boolean | null> = pii ? { ...(lead?.custom_fields || {}) } : {};
      if (pii) for (const field of options.data?.custom_fields || []) {
        const key = `custom_${field.field_key}`;
        const value = formData.get(key);
        if (field.field_type === "boolean") {
          if (value === null || value === "") delete custom[field.field_key];
          else custom[field.field_key] = value === "true";
        }
        else if (value === null || String(value).trim() === "") delete custom[field.field_key];
        else if (field.field_type === "number") {
          const number = Number(value);
          if (!Number.isFinite(number)) throw new Error(`${field.label} must be a valid number.`);
          custom[field.field_key] = number;
        } else custom[field.field_key] = String(value).trim();
      }
      const payload = {
        name: String(values.name), company: String(values.company || ""), city: String(values.city || ""),
        state: String(values.state || ""), product: String(values.product || ""),
        source_provider: String(values.source_provider || "manual"),
        phone: pii ? String(values.phone || "") : "", email: pii ? String(values.email || "") || null : null,
        address: pii ? String(values.address || "") : "", enquiry: pii ? String(values.enquiry || "") : "",
        status_id: String(values.status_id || "") || null,
        assigned_membership_id: can("leads.assign") ? assignee[0] || null : lead ? lead.assigned_membership_id : identity?.membership_id || null,
        team_id: can("leads.assign") ? team[0] || null : lead?.team_id || null,
        tags: String(values.tags || "").split(",").map(tag => tag.trim()).filter(Boolean),
        custom_fields: custom,
        next_follow_up_at: values.next_follow_up_at ? new Date(String(values.next_follow_up_at)).toISOString() : null,
        ...(lead ? { row_version: lead.row_version } : {}),
      };
      const result = await crm<{ id: string }>(lead ? `/leads/${lead.id}` : "/leads", { method: lead ? "PUT" : "POST", body: JSON.stringify(payload) });
      router.push(lead ? "/leads" : `/leads/${result.id}`);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  if (options.loading) return <Loading />;
  if (options.error) return <><ErrorNotice error={options.error} /><button className="btn" onClick={options.reload}>Retry</button></>;
  return <form onSubmit={save} className="card"><ErrorNotice error={error} /><div className="form-grid">
    {([ ["name", "Name", lead?.name], ["company", "Company", lead?.company], ["product", "Product / service", lead?.product], ["city", "City", lead?.city], ["state", "State", lead?.state]] as const).map(([name, label, value]) => <Field key={name} label={label} hint={isRequired(name) ? "Required on this status" : undefined}><input className="input" name={name} defaultValue={value || ""} required={name === "name" || isRequired(name)} maxLength={name === "city" || name === "state" ? 100 : 200} /></Field>)}
    <Field label="Source" hint="Labels only; this does not connect a provider."><input className="input" name="source_provider" defaultValue={lead?.source_provider || "manual"} required pattern="[a-z0-9_-]{1,100}" /></Field>
    <Field label="Status"><select className="select" name="status_id" value={effectiveStatusId} onChange={event => setStatusId(event.target.value)}><option value="">Default status</option>{options.data?.statuses.map(status => <option key={status.id} value={status.id}>{status.name}</option>)}</select></Field>
    <Field label="Tags" hint={isRequired("tags") ? "Required on this status" : "Comma-separated; up to 20 tags, 50 characters each."}><input className="input" name="tags" defaultValue={lead?.tags.join(", ") || ""} required={isRequired("tags")} /></Field>
    <Field label="Next follow-up" hint={isRequired("next_follow_up_at") ? "Required on this status" : "Entered in your browser's local timezone."}><input className="input" type="datetime-local" name="next_follow_up_at" defaultValue={localDate(lead?.next_follow_up_at || null)} required={isRequired("next_follow_up_at")} /></Field>
    {can("leads.assign") && <><SelectionPicker path="/leads/assignees" label="Assigned user (one; clear for unassigned)" values={assignee} onChange={setAssignee} single /><SelectionPicker path="/teams" label="Assigned team (one; clear for no team)" values={team} onChange={setTeam} single /></>}
    {pii ? <><Field label="Phone" hint={isRequired("phone") ? "Required on this status" : undefined}><input className="input" name="phone" type="tel" maxLength={40} defaultValue={lead?.phone || ""} required={isRequired("phone")} /></Field><Field label="Email" hint={isRequired("email") ? "Required on this status" : undefined}><input className="input" name="email" type="email" maxLength={320} defaultValue={lead?.email || ""} required={isRequired("email")} /></Field><Field label="Address" hint={isRequired("address") ? "Required on this status" : undefined}><textarea className="input" name="address" rows={3} maxLength={1000} defaultValue={lead?.address || ""} required={isRequired("address")} /></Field><Field label="Enquiry" hint={isRequired("enquiry") ? "Required on this status" : undefined}><textarea className="input" name="enquiry" rows={3} maxLength={10000} defaultValue={lead?.enquiry || ""} required={isRequired("enquiry")} /></Field>
      {options.data?.custom_fields.map(field => <Field key={field.field_key} label={field.label} hint={isRequired(field.field_key) ? "Required on this status" : undefined}>
        {field.field_type === "select" ? <select className="select" name={`custom_${field.field_key}`} defaultValue={String(lead?.custom_fields[field.field_key] ?? "")} required={isRequired(field.field_key)}><option value="">Choose...</option>{field.options.map(option => <option key={option} value={option}>{option}</option>)}</select> :
          field.field_type === "boolean" ? <select className="select" name={`custom_${field.field_key}`} defaultValue={lead?.custom_fields[field.field_key] === true ? "true" : lead?.custom_fields[field.field_key] === false ? "false" : ""} required={isRequired(field.field_key)}><option value="">Choose...</option><option value="true">Yes</option><option value="false">No</option></select> :
            <input className="input" name={`custom_${field.field_key}`} type={field.field_type === "number" ? "number" : "text"} step={field.field_type === "number" ? "any" : undefined} defaultValue={String(lead?.custom_fields[field.field_key] ?? "")} required={isRequired(field.field_key)} />}
      </Field>)}</> : <div className="alert alert-info">Contact, enquiry and custom fields are restricted. Existing hidden values are preserved when you save.</div>}
    {statusRequired.length > 0 && <p className="small muted">This status requires: {statusRequired.map(key => options.data?.custom_fields.find(field => field.field_key === key)?.label || key).join(", ")}.</p>}
  </div><div className="form-actions"><button type="button" className="btn" onClick={() => router.push("/leads")}>Cancel</button><button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : lead ? "Save changes" : "Create lead"}</button></div></form>;
}
