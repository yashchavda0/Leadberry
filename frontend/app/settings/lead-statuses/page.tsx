"use client";

import ScrollArea from "@/components/ScrollArea";
import { useState } from "react";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { crm, errorMessage, type LeadStatus } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

const REQUIRED_FIELDS = [
  ["name", "Name"], ["company", "Company"], ["phone", "Mobile"], ["email", "Email"],
  ["product", "Product"], ["city", "City"], ["state", "State"], ["address", "Address"],
  ["enquiry", "Enquiry"], ["tags", "Tag"], ["next_follow_up_at", "Next follow-up"],
] as const;

type Options = {
  members: { id: string; display_name: string }[];
  roles: { id: string; name: string }[];
  custom_fields: { field_key: string; label: string; field_type: string }[];
};

export default function LeadStatusesPage() {
  return <Guard permission="settings.view"><LeadStatuses /></Guard>;
}

function LeadStatuses() {
  const { can } = useSession();
  const statuses = useResource<{ data: LeadStatus[] }>("/lead-statuses");
  const options = useResource<Options>(can("assignment_rules.manage") ? "/lead-status-options" : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSaved(false);
    const values = new FormData(event.currentTarget);
    try {
      await crm("/lead-statuses", { method: "POST", body: JSON.stringify({
        name: values.get("name"), category: values.get("category"), color: values.get("color"),
        position: Number(values.get("position")), is_active: true,
      }) });
      event.currentTarget.reset();
      statuses.reload(); setSaved(true);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <><div className="page-header"><div><span className="eyebrow">PIPELINE CONFIGURATION</span><h1>Lead statuses</h1><p className="muted">Order and classify your organization’s lead stages. Status changes can tag and route leads automatically.</p></div></div>
    <ErrorNotice error={error || statuses.error || options.error} />{saved && <div className="alert alert-success" role="status">Status created.</div>}
    {can("settings.manage") && <form className="card status-create-form" onSubmit={create}><h2>Add a status</h2><div className="form-grid">
      <Field label="Name"><input className="input" name="name" required maxLength={100} /></Field>
      <Field label="Type"><select className="select" name="category"><option value="new">New</option><option value="pending">Pending</option><option value="working">In progress</option><option value="won">Won</option><option value="lost">Lost</option></select></Field>
      <Field label="Color"><input className="input color-input" name="color" type="color" defaultValue="#64748b" /></Field>
      <Field label="Display order"><input className="input" name="position" type="number" min="0" max="10000" defaultValue={statuses.data?.data.length || 0} required /></Field>
    </div><button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Add status"}</button></form>}
    {statuses.loading ? <Loading /> : <div className="status-list">{statuses.data?.data.map(status => <StatusEditor key={`${status.id}-${JSON.stringify(status)}`} status={status} options={options.data} canEdit={can("settings.manage")} canAssign={can("assignment_rules.manage")} onSaved={statuses.reload} />)}</div>}
  </>;
}

function StatusEditor({ status, options, canEdit, canAssign, onSaved }: {
  status: LeadStatus; options?: Options | null; canEdit: boolean; canAssign: boolean; onSaved: () => void;
}) {
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function saveStatus(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const values = new FormData(event.currentTarget);
    try {
      await crm(`/lead-statuses/${status.id}`, { method: "PUT", body: JSON.stringify({
        name: status.is_system ? status.name : values.get("name"),
        category: status.is_system ? status.type : values.get("category"),
        color: values.get("color"), position: Number(values.get("position")),
        is_active: status.is_system ? status.is_active : values.get("is_active") === "on",
      }) });
      setNotice("Status saved."); onSaved();
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  async function saveRules(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const values = new FormData(event.currentTarget);
    try {
      await crm(`/lead-statuses/${status.id}/rules`, { method: "PUT", body: JSON.stringify({
        tag_on_entry: String(values.get("tag_on_entry") || "").trim() || null,
        auto_assign: values.get("auto_assign") === "on",
        member_ids: values.getAll("member_id").map(String),
        role_ids: values.getAll("role_id").map(String),
        required_fields: values.getAll("required_field").map(String),
      }) });
      setNotice("Automation saved."); onSaved();
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  const requiredChoices = [...REQUIRED_FIELDS.map(([key, label]) => ({ key, label })), ...(options?.custom_fields || []).map(field => ({ key: field.field_key, label: field.label }))];
  return <details className="lead-status-config"><summary><span className="status-dot" style={{ background: status.color }} />{status.name}<span className="badge">{status.type}</span>{status.is_system && <span className="badge">System</span>}{status.is_default && <span className="badge">Default</span>}</summary>
    <div className="lead-status-config-body"><ErrorNotice error={error} />{notice && <p className="small muted" role="status">{notice}</p>}
      <form className="form-grid" onSubmit={saveStatus}><Field label="Name"><input className="input" name="name" defaultValue={status.name} required maxLength={100} disabled={!canEdit || status.is_system} /></Field>
        <Field label="Type"><select className="select" name="category" defaultValue={status.type} disabled={!canEdit || status.is_system}>{[["new", "New"], ["pending", "Pending"], ["working", "In progress"], ["won", "Won"], ["lost", "Lost"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        <Field label="Color"><input className="input color-input" name="color" type="color" defaultValue={status.color} disabled={!canEdit} /></Field>
        <Field label="Display order"><input className="input" name="position" type="number" min="0" max="10000" defaultValue={status.position} required disabled={!canEdit} /></Field>
        <label className="check-row"><input name="is_active" type="checkbox" defaultChecked={status.is_active} disabled={!canEdit || status.is_system || status.is_default} />Active</label>
        {canEdit && <button className="btn" disabled={busy}>Save status</button>}
      </form>
      {canAssign && <form className="status-rules-form" onSubmit={saveRules}><h3>Entry rules</h3>
        <Field label="Tag to add when a lead enters this status"><input className="input" name="tag_on_entry" maxLength={50} defaultValue={status.tag_on_entry || ""} /></Field>
        <label className="check-row"><input type="checkbox" name="auto_assign" defaultChecked={status.auto_assign} />Automatically assign by round robin</label>
        <fieldset className="status-choice-group"><legend>Eligible users</legend><ScrollArea maxHeight={250} label="Eligible users">{options?.members.map(member => <label className="check-row" key={member.id}><input type="checkbox" name="member_id" value={member.id} defaultChecked={status.member_ids.includes(member.id)} />{member.display_name}</label>)}</ScrollArea></fieldset>
        <fieldset className="status-choice-group"><legend>Allowed roles (empty means any role)</legend><ScrollArea maxHeight={250} label="Allowed roles">{options?.roles.map(role => <label className="check-row" key={role.id}><input type="checkbox" name="role_id" value={role.id} defaultChecked={status.role_ids.includes(role.id)} />{role.name}</label>)}</ScrollArea></fieldset>
        <fieldset className="status-choice-group"><legend>Required attributes</legend><ScrollArea maxHeight={250} label="Required attributes">{requiredChoices.map(field => <label className="check-row" key={field.key}><input type="checkbox" name="required_field" value={field.key} defaultChecked={status.required_fields.includes(field.key)} />{field.label}</label>)}</ScrollArea></fieldset>
        <button className="btn btn-primary" disabled={busy}>Save entry rules</button>
      </form>}
      {!canAssign && <p className="small muted">Assignment and required-field rules need assignment_rules.manage.</p>}
    </div>
  </details>;
}