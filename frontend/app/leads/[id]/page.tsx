"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import DOMPurify from "isomorphic-dompurify";
import LeadForm from "@/components/LeadForm";
import { Guard, useSession } from "@/components/Session";
import Icon from "@/components/Icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorNotice, Loading } from "@/components/Ui";
import { useNotify } from "@/components/Notifications";
import { crm, errorMessage, formatDate, type Lead, type Status } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

type StatusHistoryEntry = {
  id: string;
  from_status: string;
  to_status: string;
  note: string | null;
  actor_name: string;
  created_at: string;
};

type StatusOption = Status & { required_fields?: string[] };

function localDateTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function LeadPage() { return <Guard permission="leads.view"><Detail /></Guard>; }
function Detail() {
  const { id } = useParams<{ id: string }>();
  const resource = useResource<Lead>(`/leads/${encodeURIComponent(id)}`);
  const { can } = useSession();
  const statusOptions = useResource<{ statuses: StatusOption[] }>(can("leads.edit") ? "/leads/options" : null);
  const statusHistory = useResource<{ data: StatusHistoryEntry[] }>(`/leads/${encodeURIComponent(id)}/status-history`);
  const [editing, setEditing] = useState(false);
  const [activeTab, setActiveTab] = useState("details");
  const [detailSection, setDetailSection] = useState("lead");
  const [selectedStatusId, setSelectedStatusId] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [nextFollowUpAt, setNextFollowUpAt] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const notify = useNotify();
  const lead = resource.data;
  useEffect(() => {
    if (lead) {
      setSelectedStatusId(lead.status_id);
      setNextFollowUpAt(localDateTime(lead.next_follow_up_at));
    }
  }, [lead?.status_id, lead?.next_follow_up_at]);
  const targetStatus = statusOptions.data?.statuses.find(status => status.id === selectedStatusId);
  const needsFollowUpTime = targetStatus?.type === "pending" || targetStatus?.required_fields?.includes("next_follow_up_at") === true;
  const sanitizedEnquiry = lead && !lead.pii_redacted
    ? DOMPurify.sanitize(lead.enquiry || "", {
      ALLOWED_TAGS: ["a", "b", "blockquote", "br", "caption", "code", "dd", "div", "dl", "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "li", "ol", "p", "pre", "s", "span", "strong", "sub", "sup", "table", "tbody", "td", "th", "thead", "tr", "u", "ul"],
      ALLOWED_ATTR: ["href", "title", "colspan", "rowspan"],
    })
    : "";

  async function archive() {
    if (!lead) return;
    const action = lead.archived_at ? "restore" : "archive";
    if (!window.confirm(`${action === "archive" ? "Archive" : "Restore"} this lead?`)) return;
    setBusy(true);
    try { await crm(`/leads/${id}/${action}`, { method: "POST", body: JSON.stringify({ row_version: lead.row_version }) }); resource.reload(); notify.success(`${lead.name} ${action === "archive" ? "archived" : "restored"}.`); }
    catch (error) { notify.error(errorMessage(error), { title: `Lead could not be ${action === "archive" ? "archived" : "restored"}` }); }
    finally { setBusy(false); }
  }

  async function saveStatus(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!lead || !selectedStatusId || !statusNote.trim()) return;
    setStatusBusy(true);
    try {
      await crm(`/leads/${id}/status`, {
        method: "POST",
        body: JSON.stringify({
          status_id: selectedStatusId,
          note: statusNote.trim(),
          next_follow_up_at: nextFollowUpAt ? new Date(nextFollowUpAt).toISOString() : null,
          row_version: lead.row_version,
        }),
      });
      setStatusNote("");
      notify.success("Lead status updated.");
      resource.reload();
      statusHistory.reload();
    } catch (error) {
      notify.error(errorMessage(error), { title: "Status could not be updated" });
    } finally {
      setStatusBusy(false);
    }
  }

  return <div className="lead-detail-page">
    <Button variant="outline" size="icon" asChild className="lead-back-link"><Link href="/leads" aria-label="Back to leads" title="Back to leads"><Icon name="chevronLeft" /></Link></Button>
    <ErrorNotice error={resource.error} />
    {resource.loading && <Loading />}
    {resource.error && <Button variant="outline" onClick={() => { setEditing(false); resource.reload(); }}>Reload lead</Button>}
    {lead && <>
      <div className="lead-detail-heading">
        <Card className="lead-identity-card">
          <div className="lead-identity-title">
            <span className="lead-avatar" aria-hidden="true">{lead.name.trim().charAt(0).toUpperCase() || "L"}</span>
            <div className="lead-identity-copy">
              <span className="eyebrow">{lead.source_provider.toUpperCase()} LEAD</span>
              <h1>{lead.name}</h1>
              {lead.is_repeat_customer && <span className="repeat-customer-badge">Repeat customer</span>}
              <p>{lead.company || "No company"}</p>
            </div>
          </div>
          <div className="lead-identity-contact">
            <div><span>Email</span><strong>{lead.pii_redacted ? "Restricted" : lead.email || "Not provided"}</strong></div>
            <div><span>Phone</span><strong>{lead.pii_redacted ? "Restricted" : lead.phone || "Not provided"}</strong></div>
          </div>
          <div className="lead-identity-meta">
            <span>Received <strong>{formatDate(lead.received_at)}</strong></span>
            <span>Updated <strong>{formatDate(lead.updated_at)}</strong></span>
          </div>
        </Card>
        <Card className="lead-overview-card">
          <div className="lead-overview-item"><span>Lead status</span><Badge dot className="lead-status-pill" style={{ "--lead-status-color": lead.status_color } as CSSProperties}>{lead.status}</Badge></div>
          <div className="lead-overview-item"><span>Lead owner</span><strong>{lead.assignee || "Unassigned"}</strong></div>
          <div className="lead-overview-item"><span>Next follow-up</span><strong>{formatDate(lead.next_follow_up_at)}</strong></div>
          <div className="lead-overview-item"><span>Lead source</span><strong>{lead.source_account_name || lead.source_provider}</strong></div>
          <div className="lead-overview-product">
            <div><span className="field-label">Product enquiry</span><strong>{lead.product || "Product not specified"}</strong></div>
            <Button variant="link" size="sm" onClick={() => setActiveTab("enquiry")}>View enquiry</Button>
          </div>
          {lead.archived_at && <Badge variant="outline" className="lead-archived-label">Archived</Badge>}
          <div className="lead-detail-actions">
            <Button variant="outline" size="sm" onClick={() => { setEditing(false); resource.reload(); }}>Reload</Button>
            {can("leads.edit") && !lead.archived_at && <Button size="sm" onClick={() => setEditing(value => !value)}>{editing ? "Cancel editing" : "Edit lead"}</Button>}
            {can(lead.archived_at ? "leads.restore" : "leads.archive") && <Button variant="outline" size="sm" disabled={busy} onClick={archive}>{lead.archived_at ? "Restore" : "Archive"}</Button>}
          </div>
        </Card>
      </div>
      {editing ? <LeadForm key={lead.row_version} lead={lead} /> : <>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="lead-detail-tabs-root">
          <TabsList aria-label="Lead information" className="lead-detail-tabs">
            <TabsTrigger value="details">Lead Details</TabsTrigger>
            <TabsTrigger value="activity">Timeline</TabsTrigger>
            <TabsTrigger value="follow-up">Follow up &amp; Notes</TabsTrigger>
            <TabsTrigger value="enquiry">Enquiry</TabsTrigger>
            <TabsTrigger value="custom">Custom Fields</TabsTrigger>
          </TabsList>
          <TabsContent value="details" className="lead-detail-content">
            <Tabs value={detailSection} onValueChange={setDetailSection} className="lead-detail-subtabs-root">
              <TabsList aria-label="Lead detail sections" className="lead-detail-subtabs">
                <TabsTrigger value="lead">Lead Details</TabsTrigger>
                <TabsTrigger value="additional">Additional Details</TabsTrigger>
              </TabsList>
              <TabsContent value="lead" className="lead-detail-subcontent"><div className="lead-attribute-columns">
              <LeadAttributeTable title="Contact details" items={[
                ["Company", lead.company],
                ["Email", lead.pii_redacted ? "Restricted" : lead.email || "-"],
                ["Phone", lead.pii_redacted ? "Restricted" : lead.phone || "-"],
                ["City", lead.city || "-"],
                ["State", lead.state || "-"],
                ["Address", lead.pii_redacted ? "Restricted" : lead.address || "-"],
              ]} />
              <LeadAttributeTable title="Lead details" items={[
                ["Status", lead.status],
                ["Lead owner", lead.assignee || "Unassigned"],
                ["Team", lead.team_name || "-"],
                ["Next follow-up", formatDate(lead.next_follow_up_at)],
                ["Received", formatDate(lead.received_at)],
                ["Last updated", formatDate(lead.updated_at)],
              ]} />
              </div></TabsContent>
              <TabsContent value="additional" className="lead-detail-subcontent"><div className="lead-attribute-columns">
              <LeadAttributeTable title="Additional details" items={[
                ["Product", lead.product || "-"],
                ["Lead source", lead.source_provider],
                ["Source account", lead.source_account_name || "-"],
                ["Source record", lead.source_record_id || "-"],
                ["Tags", lead.tags.join(", ") || "-"],
              ]} />
              <LeadAttributeTable title="Custom fields" items={lead.pii_redacted ? [] : Object.entries(lead.custom_fields).map(([key, value]) => [key, String(value ?? "-")])} emptyMessage={lead.pii_redacted ? "Restricted by contact permission." : "No custom fields."} />
              </div></TabsContent>
            </Tabs>
          </TabsContent>
          <TabsContent value="activity" className="lead-detail-content"><div className="lead-event-list">
            <LeadEvent title="Lead received" date={formatDate(lead.received_at)} />
            {statusHistory.data?.data.length ? [...statusHistory.data.data].reverse().map(entry => <LeadEvent key={entry.id} title={`Status changed: ${entry.from_status} to ${entry.to_status}`} date={formatDate(entry.created_at)} note={entry.note} actor={entry.actor_name} />) : <LeadEvent title={`Status: ${lead.status}`} date={formatDate(lead.status_changed_at)} />}
            <LeadEvent title="Lead updated" date={formatDate(lead.updated_at)} />
            {statusHistory.error && <ErrorNotice error={statusHistory.error} />}
          </div></TabsContent>
          <TabsContent value="follow-up" className="lead-detail-content"><div className="lead-followup-panel">
            <div><span className="field-label">Next follow-up</span><strong>{formatDate(lead.next_follow_up_at)}</strong></div>
            <div><span className="field-label">Tags</span><div className="tag-list">{lead.tags.length ? lead.tags.map(tag => <span className="tag" key={tag}>{tag}</span>) : <span className="muted">No tags</span>}</div></div>
            <p className="muted">No follow-up notes are recorded for this lead.</p>
          </div></TabsContent>
          <TabsContent value="enquiry" className="lead-detail-content"><div className="lead-enquiry-panel">
            <div className="lead-enquiry-heading"><span className="eyebrow">PRODUCT ENQUIRED</span><h2>{lead.product || "Product not specified"}</h2></div>
            <div className="lead-enquiry-message"><span className="field-label">Enquiry details</span>{lead.pii_redacted ? <p className="message">Restricted by contact permission.</p> : sanitizedEnquiry ? <div className="message lead-enquiry-html" dangerouslySetInnerHTML={{ __html: sanitizedEnquiry }} /> : <p className="message">No enquiry recorded.</p>}</div>
          </div></TabsContent>
          <TabsContent value="custom" className="lead-detail-content"><div className="lead-custom-panel"><LeadAttributeTable title="Custom fields" items={lead.pii_redacted ? [] : Object.entries(lead.custom_fields).map(([key, value]) => [key, String(value ?? "-")])} emptyMessage={lead.pii_redacted ? "Restricted by contact permission." : "No custom fields."} /></div></TabsContent>
        </Tabs>
        {can("leads.edit") && !lead.archived_at ? <form className="lead-status-editor" onSubmit={saveStatus}>
          <div className="lead-status-editor-heading">
            <div className="lead-status-editor-title"><span className="eyebrow">LEAD WORKFLOW</span><h2>Update status</h2></div>
            <div className="lead-current-status"><span className="field-label">Current status</span><Badge dot className="lead-status-pill" style={{ "--lead-status-color": lead.status_color } as CSSProperties}>{lead.status}</Badge></div>
          </div>
          {statusOptions.error ? <ErrorNotice error={statusOptions.error} /> : statusOptions.loading ? <Loading /> : <>
            <label className="lead-status-select-label" htmlFor="lead-status-select-trigger">New status</label>
            {statusOptions.data?.statuses.length ? <Select value={selectedStatusId} onValueChange={setSelectedStatusId} disabled={statusBusy}>
              <SelectTrigger id="lead-status-select-trigger" className="lead-status-select-trigger" aria-label="New status"><SelectValue placeholder="Choose a status" /></SelectTrigger>
              <SelectContent>
                {statusOptions.data.statuses.map(status => <SelectItem key={status.id} value={status.id}>
                  <span className="lead-status-select-option"><span className="lead-status-choice-dot" style={{ "--status-color": status.color } as CSSProperties} />{status.name}</span>
                </SelectItem>)}
              </SelectContent>
            </Select> : <p className="muted">No active statuses are available.</p>}
            {needsFollowUpTime && <label className="lead-status-note lead-status-followup" htmlFor="lead-status-followup"><span className="lead-status-note-title">Next contact date &amp; time <span aria-hidden="true">*</span></span>
              <span className="lead-status-datetime">
                <input id="lead-status-followup" className="input" type="datetime-local" value={nextFollowUpAt} onChange={event => setNextFollowUpAt(event.target.value)} required={targetStatus?.type === "pending" || targetStatus?.required_fields?.includes("next_follow_up_at")} disabled={statusBusy} />
                {!nextFollowUpAt && <span className="lead-status-datetime-placeholder" aria-hidden="true">Select date and time</span>}
              </span>
              <small className="hint">Choose when to try contacting this lead again.</small>
            </label>}
            <label className="lead-status-note" htmlFor="lead-status-note"><span className="lead-status-note-title">Note <span aria-hidden="true">*</span></span>
              <textarea id="lead-status-note" className="input" value={statusNote} onChange={event => setStatusNote(event.target.value)} maxLength={2000} rows={3} required disabled={statusBusy} />
            </label>
            <div className="lead-status-editor-footer">
              <span className="small muted">Changing to <strong>{statusOptions.data?.statuses.find(status => status.id === selectedStatusId)?.name || lead.status}</strong></span>
              <Button type="submit" disabled={statusBusy || !statusNote.trim() || !selectedStatusId || selectedStatusId === lead.status_id}>{statusBusy ? "Updating..." : "Update status"}</Button>
            </div>
          </>}
        </form> : <div className="lead-status-footer"><span>Current lead status</span><Badge dot className="lead-status-pill" style={{ "--lead-status-color": lead.status_color } as CSSProperties}>{lead.status}</Badge></div>}
      </>}
    </>}
  </div>;
}

function LeadAttributeTable({ title, items, emptyMessage = "No details available." }: { title: string; items: [string, string][]; emptyMessage?: string }) {
  return <div className="lead-attribute-table-wrap">
    <table className="lead-attribute-table">
      <thead>
        <tr><th className="lead-attribute-title" colSpan={2}>{title}</th></tr>
        <tr className="lead-attribute-columns-head"><th scope="col">Parameter</th><th scope="col">Value</th></tr>
      </thead>
      <tbody>{items.length ? items.map(([label, value]) => <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>) : <tr><td className="lead-attribute-empty" colSpan={2}>{emptyMessage}</td></tr>}</tbody>
    </table>
  </div>;
}

function LeadEvent({ title, date, note, actor }: { title: string; date: string; note?: string | null; actor?: string }) {
  return <div className="lead-event"><span className="lead-event-marker" /><div><strong>{title}</strong><time>{date}</time>{actor && <span className="small muted">By {actor}</span>}{note !== undefined && <div className="lead-event-message"><span className="lead-event-message-label">Note</span><p className="lead-event-note">{note || "Note restricted by contact permission."}</p></div>}</div></div>;
}
