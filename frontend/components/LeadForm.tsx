"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { crm, errorMessage, type Lead, type LeadCustomField, type Status } from "@/lib/crm";
import { useResource } from "@/lib/hooks";
import { useSession } from "./Session";
import { ErrorNotice, Field, Loading } from "./Ui";
import LeadAssignmentPicker from "./LeadAssignmentPicker";
import Icon from "./Icon";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { useNotify } from "./Notifications";

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
  const [formKey, setFormKey] = useState(0);
  const notify = useNotify();
  const router = useRouter();
  const pii = can("leads.pii.view");
  const effectiveStatusId = statusId || lead?.status_id || options.data?.statuses.find(status => status.is_default)?.id || "";
  const selectedStatus = options.data?.statuses.find(status => status.id === effectiveStatusId);
  const statusRequired = selectedStatus?.required_fields || [];
  const isRequired = (key: string) => key === "next_follow_up_at"
    ? !(lead && lead.status_id === effectiveStatusId && !lead.next_follow_up_at) && (selectedStatus?.type === "pending" || statusRequired.includes(key))
    : statusRequired.includes(key);
  const fieldHint = (key: string, piiField = false) => {
    if (isRequired(key) && !pii) return "Required for selected status; contact-data permission required";
    if (isRequired(key)) return "Required for selected status";
    if (piiField && !pii) return "Read-only: contact-data permission required";
    return undefined;
  };
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      const addAnother = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "another";
      const formData = new FormData(event.currentTarget);
      const values = Object.fromEntries(formData);
      const tags = [...new Set(String(values.tags || "").split(",").map(tag => tag.trim()).filter(Boolean))];
      if (!String(values.name || "").trim()) throw new Error("Enter a lead name.");
      if (tags.length > 20 || tags.some(tag => tag.length > 50)) throw new Error("Use up to 20 tags, each no longer than 50 characters.");
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
        name: String(values.name).trim(), company: String(values.company || "").trim(), city: String(values.city || "").trim(),
        state: String(values.state || "").trim(), product: String(values.product || "").trim(),
        source_provider: String(values.source_provider || "manual").trim(),
        phone: pii ? String(values.phone || "").trim() : "", email: pii ? String(values.email || "").trim() || null : null,
        address: pii ? String(values.address || "").trim() : "", enquiry: pii ? String(values.enquiry || "").trim() : "",
        status_id: String(values.status_id || "") || null,
        assigned_membership_id: can("leads.assign") ? assignee[0] || null : lead ? lead.assigned_membership_id : identity?.membership_id || null,
        team_id: can("leads.assign") ? team[0] || null : lead?.team_id || null,
        tags,
        custom_fields: custom,
        next_follow_up_at: values.next_follow_up_at ? new Date(String(values.next_follow_up_at)).toISOString() : null,
        ...(lead ? { row_version: lead.row_version } : {}),
      };
      const result = await crm<{ id: string }>(lead ? `/leads/${lead.id}` : "/leads", { method: lead ? "PUT" : "POST", body: JSON.stringify(payload) });
      notify.success(lead ? "Lead updated." : "Lead created.");
      if (addAnother && !lead) {
        setFormKey(current => current + 1); setStatusId(""); setTeam([]);
        setAssignee(identity?.membership_id ? [identity.membership_id] : []);
      } else router.push(lead ? "/leads" : `/leads/${result.id}`);
    } catch (error) { setError(errorMessage(error)); notify.error(errorMessage(error), { title: "Lead could not be saved" }); }
    finally { setBusy(false); }
  }
  if (options.loading) return <Loading />;
  if (options.error) return <><ErrorNotice error={options.error} /><button className="btn" onClick={options.reload}>Retry</button></>;
  const basicField = (name: string, label: string, value?: string | null) => <Field label={label} hint={isRequired(name) ? "Required for selected status" : undefined}><input className="input" name={name} defaultValue={value || ""} required={name === "name" || isRequired(name)} maxLength={name === "city" || name === "state" ? 100 : 200} autoFocus={name === "name"} /></Field>;
  return <Card className="lead-edit-card"><div className="lead-edit-header"><div><span className="eyebrow">LEAD EDITOR</span><h2>{lead ? "Edit lead" : "Create lead"}</h2><p>{lead ? "Update the lead details and qualifications." : "Capture contact information and what they need."}</p></div></div><form onSubmit={save} className="lead-entry-form lead-edit-form"><fieldset disabled={busy} key={formKey} className="lead-entry-fields">
    <LeadFormSection title="Contact details">
      {basicField("name", "Name", lead?.name)}{basicField("company", "Company", lead?.company)}
      <Field label="Phone" hint={fieldHint("phone", true)}><input className="input" name="phone" type="tel" autoComplete="tel" maxLength={40} defaultValue={pii ? lead?.phone || "" : ""} required={pii && isRequired("phone")} disabled={!pii} /></Field>
      <Field label="Email" hint={fieldHint("email", true)}><input className="input" name="email" type="email" autoComplete="email" maxLength={320} defaultValue={pii ? lead?.email || "" : ""} required={pii && isRequired("email")} disabled={!pii} /></Field>
    </LeadFormSection>
    <LeadFormSection title="Qualification">
      {basicField("product", "Product / service", lead?.product)}{basicField("city", "City", lead?.city)}{basicField("state", "State", lead?.state)}
      <Field label="Address" hint={fieldHint("address", true)}><textarea className="input" name="address" rows={3} maxLength={1000} defaultValue={pii ? lead?.address || "" : ""} required={pii && isRequired("address")} disabled={!pii} /></Field>
      <Field label="Enquiry" hint={fieldHint("enquiry", true)}><textarea className="input" name="enquiry" rows={3} maxLength={10000} defaultValue={pii ? lead?.enquiry || "" : ""} required={pii && isRequired("enquiry")} disabled={!pii} /></Field>
    </LeadFormSection>
    <LeadFormSection title="Status & ownership">
      <Field label="Status"><Select name="status_id" value={effectiveStatusId} onValueChange={setStatusId} required><SelectTrigger className="lead-form-select" aria-label="Status"><SelectValue placeholder="Choose a status" /></SelectTrigger><SelectContent>{options.data?.statuses.map(status => <SelectItem key={status.id} value={status.id}>{status.name}</SelectItem>)}</SelectContent></Select></Field>
      <Field label="Next follow-up" hint={isRequired("next_follow_up_at") ? "Required for selected status" : undefined}><input className="input" type="datetime-local" name="next_follow_up_at" defaultValue={localDate(lead?.next_follow_up_at || null)} required={isRequired("next_follow_up_at")} /></Field>
      <Field label="Source"><input className="input" name="source_provider" defaultValue={lead?.source_provider || "manual"} required pattern="[a-z0-9_-]{1,100}" maxLength={100} /></Field>
      <Field label="Tags" hint={isRequired("tags") ? "Required for selected status" : undefined}><input className="input" name="tags" placeholder="e.g. Priority, Retail" defaultValue={lead?.tags.join(", ") || ""} required={isRequired("tags")} maxLength={1039} /></Field>
      {can("leads.assign") && <><LeadAssignmentPicker path="/leads/assignees" label="Assigned user" value={assignee[0] || ""} initialLabel={lead?.assignee || (assignee[0] === identity?.membership_id ? "Me" : undefined)} onChange={id => setAssignee(id ? [id] : [])} /><LeadAssignmentPicker path="/teams" label="Assigned team" value={team[0] || ""} emptyLabel="No team" onChange={id => setTeam(id ? [id] : [])} /></>}
    </LeadFormSection>
    {Boolean(options.data?.custom_fields.length) && <LeadFormSection title="Additional details">
      {options.data?.custom_fields.map(field => <Field key={field.field_key} label={field.label} hint={fieldHint(field.field_key, true)}>
        {field.field_type === "select" ? <Select name={`custom_${field.field_key}`} defaultValue={String(lead?.custom_fields[field.field_key] ?? "") || undefined} required={pii && isRequired(field.field_key)} disabled={!pii}><SelectTrigger className="lead-form-select" aria-label={field.label}><SelectValue placeholder="Choose..." /></SelectTrigger><SelectContent>{field.options.map(option => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent></Select> :
          field.field_type === "boolean" ? <Select name={`custom_${field.field_key}`} defaultValue={lead?.custom_fields[field.field_key] === true ? "true" : lead?.custom_fields[field.field_key] === false ? "false" : undefined} required={pii && isRequired(field.field_key)} disabled={!pii}><SelectTrigger className="lead-form-select" aria-label={field.label}><SelectValue placeholder="Choose..." /></SelectTrigger><SelectContent><SelectItem value="true">Yes</SelectItem><SelectItem value="false">No</SelectItem></SelectContent></Select> :
            <input className="input" name={`custom_${field.field_key}`} type={field.field_type === "number" ? "number" : "text"} step={field.field_type === "number" ? "any" : undefined} defaultValue={pii ? String(lead?.custom_fields[field.field_key] ?? "") : ""} required={pii && isRequired(field.field_key)} disabled={!pii} />}
      </Field>)}
    </LeadFormSection>}
    {!pii && <p className="small muted">Sensitive attributes are shown read-only because contact-data permission is required to edit them.</p>}
  </fieldset><div className="form-actions lead-entry-actions"><span className="small muted" role="status">{error ? "Lead not saved. Review the notification and try again." : ""}</span><Button type="button" variant="outline" disabled={busy} onClick={() => router.push("/leads")}>Cancel</Button>{!lead && <Button type="submit" name="intent" value="another" variant="outline" disabled={busy}>Create & add another</Button>}<Button type="submit" disabled={busy}><Icon name="check" />{busy ? "Saving..." : lead ? "Save changes" : "Create lead"}</Button></div></form></Card>;
}

function LeadFormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="lead-form-section"><h2>{title}</h2><div className="form-grid">{children}</div></section>;
}
