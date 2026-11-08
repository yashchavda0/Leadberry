"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import LeadForm from "@/components/LeadForm";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Loading } from "@/components/Ui";
import { crm, errorMessage, formatDate, type Lead } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

export default function LeadPage() { return <Guard permission="leads.view"><Detail /></Guard>; }
function Detail() {
  const { id } = useParams<{ id: string }>();
  const resource = useResource<Lead>(`/leads/${encodeURIComponent(id)}`);
  const { can } = useSession();
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function archive() {
    if (!resource.data) return;
    const action = resource.data.archived_at ? "restore" : "archive";
    if (!window.confirm(`${action === "archive" ? "Archive" : "Restore"} this lead?`)) return;
    setBusy(true); setError("");
    try { await crm(`/leads/${id}/${action}`, { method: "POST", body: JSON.stringify({ row_version: resource.data.row_version }) }); resource.reload(); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  const lead = resource.data;
  return <><Link href="/leads" className="small">Back to leads</Link><ErrorNotice error={error || resource.error} />{resource.loading && <Loading />}{resource.error && <button className="btn" onClick={() => { setEditing(false); resource.reload(); }}>Reload lead</button>}
    {lead && <><div className="page-header"><div><span className="eyebrow">{lead.source_provider.toUpperCase()} LEAD</span><h1>{lead.name}</h1><p className="muted">{lead.company || "No company"} / Received {formatDate(lead.received_at)}</p></div><div className="actions"><button className="btn" onClick={() => { setEditing(false); resource.reload(); }}>Reload</button>{can("leads.edit") && !lead.archived_at && <button className="btn btn-primary" onClick={() => setEditing(value => !value)}>{editing ? "Cancel editing" : "Edit lead"}</button>}{can(lead.archived_at ? "leads.restore" : "leads.archive") && <button className="btn" disabled={busy} onClick={archive}>{lead.archived_at ? "Restore" : "Archive"}</button>}</div></div>
      {editing ? <LeadForm key={lead.row_version} lead={lead} /> : <><div className="card lead-summary"><span className="badge">{lead.status}</span><span>Assigned: {lead.assignee || "Unassigned"}</span><span>Follow-up: {formatDate(lead.next_follow_up_at)}</span>{lead.archived_at && <span className="badge">Archived</span>}<div className="tag-list">{lead.tags.map(tag => <span className="tag" key={tag}>{tag}</span>)}</div></div><div className="card detail-grid">{[["Phone", lead.phone], ["Email", lead.email], ["Product", lead.product], ["City", lead.city], ["State", lead.state], ["Address", lead.address], ["Source", lead.source_provider], ["Last updated", formatDate(lead.updated_at)]].map(([label, value]) => <div key={label}><div className="field-label">{label}</div><div>{value || (lead.pii_redacted && ["Phone", "Email", "Address"].includes(label || "") ? "Restricted" : "-")}</div></div>)}</div><div className="card"><h2>Enquiry</h2><p className="message">{lead.pii_redacted ? "Restricted by contact permission." : lead.enquiry || "No enquiry recorded."}</p><h2>Custom fields</h2>{lead.pii_redacted ? <p className="muted">Restricted by contact permission.</p> : Object.keys(lead.custom_fields).length ? <dl className="detail-grid">{Object.entries(lead.custom_fields).map(([key, value]) => <div key={key}><dt className="field-label">{key}</dt><dd>{String(value ?? "-")}</dd></div>)}</dl> : <p className="muted">No custom fields.</p>}</div></>}
    </>}
  </>;
}
