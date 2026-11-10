"use client";

import ScrollArea from "@/components/ScrollArea";
import { useState } from "react";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { useNotify } from "@/components/Notifications";
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
  const notify = useNotify();
  const allStatuses = statuses.data?.data || [];
  const activeCount = allStatuses.filter(status => status.is_active).length;
  const defaultStatus = allStatuses.find(status => status.is_default);
  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    try {
      await crm("/lead-statuses", { method: "POST", body: JSON.stringify({
        name: values.get("name"), category: values.get("category"), color: values.get("color"),
        position: Number(values.get("position")), is_active: true,
      }) });
      event.currentTarget.reset();
      statuses.reload(); notify.success(`${values.get("name")} is now available.`, { title: "Status created" });
    } catch (failure) { notify.error(errorMessage(failure), { title: "Status could not be created" }); }
    finally { setBusy(false); }
  }
  return <><div className="page-header lead-status-page-header"><div><span className="eyebrow">PIPELINE CONFIGURATION</span><h1>Lead statuses</h1><p className="muted">Organize your sales stages and set rules for leads as they move through the pipeline.</p></div></div>
    {statuses.error || options.error ? <div className="status-load-error"><ErrorNotice error={statuses.error || options.error} /><button className="btn" type="button" onClick={() => { statuses.reload(); options.reload(); }}>Retry loading settings</button></div> : null}
    {!statuses.loading && statuses.data && <section className="status-overview" aria-label="Pipeline overview">
      <div className="status-overview-metrics"><div><span>Stages</span><strong>{allStatuses.length}</strong></div><div><span>Active</span><strong>{activeCount}</strong></div><div><span>Default stage</span><strong>{defaultStatus?.name || "Not set"}</strong></div></div>
      {allStatuses.length > 0 && <ol className="status-flow" aria-label="Stages in display order">{allStatuses.map(status => <li key={status.id} className={!status.is_active ? "inactive" : ""}><span className="status-flow-dot" style={{ background: status.color }} /><span className="status-flow-name">{status.name}</span>{status.is_default && <span className="small muted">Default</span>}</li>)}</ol>}
    </section>}
    {can("settings.manage") && <form className="card status-create-form" onSubmit={create}><div className="status-section-heading"><div><span className="eyebrow">CUSTOMIZE YOUR PIPELINE</span><h2>Add a status</h2><p className="muted">Create a stage for a distinct step in your lead workflow.</p></div></div><div className="form-grid">
      <Field label="Name"><input className="input" name="name" required maxLength={100} /></Field>
      <Field label="Type"><select className="select" name="category"><option value="new">New</option><option value="pending">Pending</option><option value="working">In progress</option><option value="won">Won</option><option value="lost">Lost</option></select></Field>
      <Field label="Color"><input className="input color-input" name="color" type="color" defaultValue="#64748b" /></Field>
      <Field label="Display order"><input className="input" name="position" type="number" min="0" max="10000" defaultValue={statuses.data?.data.length || 0} required /></Field>
    </div><button className="btn btn-primary" disabled={busy || statuses.loading}>{busy ? "Saving..." : "Add status"}</button></form>}
    <section className="status-management-section"><div className="status-section-heading"><div><span className="eyebrow">STAGE SETTINGS</span><h2>Workflow stages</h2><p className="muted">Expand a stage to edit its details, activation, and entry rules.</p></div>{!statuses.loading && statuses.data && <span className="badge">{allStatuses.length} {allStatuses.length === 1 ? "stage" : "stages"}</span>}</div>
      {statuses.loading ? <Loading /> : statuses.data?.data.length ? <div className="status-list">{statuses.data.data.map(status => <StatusEditor key={`${status.id}-${JSON.stringify(status)}`} status={status} options={options.data} canEdit={can("settings.manage")} canAssign={can("assignment_rules.manage")} onSaved={statuses.reload} />)}</div> : !statuses.error ? <div className="status-empty"><h3>No lead statuses yet</h3><p className="muted">Add your first status to define how leads move through your pipeline.</p></div> : null}
    </section>
  </>;
}

function StatusEditor({ status, options, canEdit, canAssign, onSaved }: {
  status: LeadStatus; options?: Options | null; canEdit: boolean; canAssign: boolean; onSaved: () => void;
}) {
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  async function saveStatus(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    try {
      await crm(`/lead-statuses/${status.id}`, { method: "PUT", body: JSON.stringify({
        name: status.is_system ? status.name : values.get("name"),
        category: status.is_system ? status.type : values.get("category"),
        color: values.get("color"), position: Number(values.get("position")),
        is_active: status.is_system ? status.is_active : values.get("is_active") === "on",
      }) });
      notify.success(`${status.name} was updated.`, { title: "Status saved" }); onSaved();
    } catch (failure) { notify.error(errorMessage(failure), { title: "Status could not be saved" }); }
    finally { setBusy(false); }
  }
  async function saveRules(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    try {
      await crm(`/lead-statuses/${status.id}/rules`, { method: "PUT", body: JSON.stringify({
        tag_on_entry: String(values.get("tag_on_entry") || "").trim() || null,
        auto_assign: values.get("auto_assign") === "on",
        member_ids: values.getAll("member_id").map(String),
        role_ids: values.getAll("role_id").map(String),
        required_fields: values.getAll("required_field").map(String),
      }) });
      notify.success(`Rules for ${status.name} were updated.`, { title: "Automation saved" }); onSaved();
    } catch (failure) { notify.error(errorMessage(failure), { title: "Automation could not be saved" }); }
    finally { setBusy(false); }
  }
  const requiredChoices = [...REQUIRED_FIELDS.map(([key, label]) => ({ key, label })), ...(options?.custom_fields || []).map(field => ({ key: field.field_key, label: field.label }))];
  return <details className="lead-status-config"><summary><span className="status-dot" style={{ background: status.color }} />{status.name}<span className="badge">{status.type}</span>{status.is_system && <span className="badge">System</span>}{status.is_default && <span className="badge">Default</span>}</summary>
    <div className="lead-status-config-body">
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