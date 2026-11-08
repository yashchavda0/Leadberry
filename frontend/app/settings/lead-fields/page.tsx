"use client";

import { useState } from "react";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { crm, errorMessage, type LeadCustomField } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

export default function LeadFieldsPage() {
  return <Guard permission="settings.view"><LeadFields /></Guard>;
}

function LeadFields() {
  const { can } = useSession();
  const fields = useResource<{ data: LeadCustomField[] }>("/lead-custom-fields");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>, field?: LeadCustomField) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const values = new FormData(event.currentTarget);
    const type = String(values.get("field_type"));
    const options = type === "select" ? String(values.get("options") || "").split("\n").map(item => item.trim()).filter(Boolean) : [];
    const payload = {
      label: values.get("label"), field_type: type, options,
      position: Number(values.get("position")), is_active: values.get("is_active") === "on",
    };
    try {
      if (field) await crm(`/lead-custom-fields/${encodeURIComponent(field.field_key)}`, { method: "PUT", body: JSON.stringify(payload) });
      else await crm("/lead-custom-fields", { method: "POST", body: JSON.stringify({ ...payload, field_key: values.get("field_key") }) });
      fields.reload(); setNotice(field ? "Field saved." : "Field created.");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <><div className="page-header"><div><span className="eyebrow">PIPELINE CONFIGURATION</span><h1>Lead fields</h1><p className="muted">Define organization-specific fields used in lead forms and status requirements.</p></div></div>
    <ErrorNotice error={error || fields.error} />{notice && <div className="alert alert-success" role="status">{notice}</div>}
    {can("settings.manage") && <form className="card field-create-form" onSubmit={event => void save(event)}><h2>Add a field</h2><div className="form-grid">
      <Field label="Field key"><input className="input" name="field_key" required maxLength={100} pattern="[a-z][a-z0-9_]*" placeholder="budget_range" /></Field>
      <Field label="Label"><input className="input" name="label" required maxLength={100} /></Field>
      <Field label="Type"><select className="select" name="field_type"><option value="text">Text</option><option value="number">Number</option><option value="boolean">Yes / no</option><option value="select">Single select</option></select></Field>
      <Field label="Display order"><input className="input" type="number" name="position" min="0" max="10000" defaultValue={fields.data?.data.length || 0} required /></Field>
      <Field label="Options" hint="One option per line; used for single-select fields."><textarea className="input" name="options" rows={3} /></Field>
    </div><button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Add field"}</button></form>}
    {fields.loading ? <Loading /> : <div className="lead-custom-field-list">{fields.data?.data.map(field => <FieldEditor key={field.field_key} field={field} canEdit={can("settings.manage")} busy={busy} onSave={event => void save(event, field)} />)}</div>}
  </>;
}

function FieldEditor({ field, canEdit, busy, onSave }: {
  field: LeadCustomField; canEdit: boolean; busy: boolean; onSave: (event: React.FormEvent<HTMLFormElement>) => void;
}) {
  return <form className="lead-custom-field-row" onSubmit={onSave}><div className="field-key"><strong>{field.label}</strong><code>{field.field_key}</code></div>
    <div className="form-grid"><Field label="Label"><input className="input" name="label" defaultValue={field.label} required maxLength={100} disabled={!canEdit} /></Field>
      <Field label="Type"><select className="select" name="field_type" defaultValue={field.field_type} disabled={!canEdit}><option value="text">Text</option><option value="number">Number</option><option value="boolean">Yes / no</option><option value="select">Single select</option></select></Field>
      <Field label="Display order"><input className="input" type="number" name="position" min="0" max="10000" defaultValue={field.position} required disabled={!canEdit} /></Field>
      <Field label="Options" hint="One option per line; used for single-select fields."><textarea className="input" name="options" rows={3} defaultValue={field.options.join("\n")} disabled={!canEdit} /></Field>
      <label className="check-row"><input name="is_active" type="checkbox" defaultChecked={field.is_active} disabled={!canEdit} />Active</label>
    </div>{canEdit && <button className="btn" disabled={busy}>Save field</button>}
  </form>;
}