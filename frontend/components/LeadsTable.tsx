import Link from "next/link";
import { formatDate, type Lead } from "@/lib/crm";

export const LEAD_COLUMNS = [
  { key: "name", label: "Name" },
  { key: "company", label: "Company" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Mobile" },
  { key: "status_changed_at", label: "Status updated" },
  { key: "status", label: "Lead status" },
  { key: "source_name", label: "Source name" },
  { key: "source_record_id", label: "Audience ID" },
  { key: "received_at", label: "Received" },
  { key: "assignee", label: "Assigned to" },
  { key: "tags", label: "Tags" },
] as const;

export type LeadColumn = typeof LEAD_COLUMNS[number]["key"];

export default function LeadsTable({ leads, columns, onArchive, onRestore, busyId, canArchive = false, canRestore = false }: {
  leads: Lead[]; columns?: string[]; onArchive?: (lead: Lead) => void; onRestore?: (lead: Lead) => void;
  busyId?: string | null; canArchive?: boolean; canRestore?: boolean;
}) {
  if (!leads.length) return <div className="empty-state"><h3>No leads to display</h3><p className="muted">Create a lead or adjust your filters. Only leads within your data scope are shown.</p></div>;
  const selectedColumns = columns || ["name", "status", "assignee", "received_at"];
  const visible = LEAD_COLUMNS.filter(column => column.key === "name" || selectedColumns.includes(column.key));
  const hasActions = Boolean(onArchive || onRestore);
  return <div className="table-wrap"><table><thead><tr><th>Sr. No.</th>{visible.map(column => <th key={column.key}>{column.label}</th>)}{hasActions && <th>Actions</th>}</tr></thead><tbody>
    {leads.map((lead, index) => <tr key={lead.id}><td>{index + 1}</td>{visible.map(column => <td key={column.key}>{renderCell(column.key, lead)}</td>)}{hasActions && <td><div className="actions lead-row-actions">
      <Link className="btn" href={`/leads/${lead.id}`}>View</Link>
      {!lead.archived_at && canArchive && onArchive && <button className="btn" disabled={busyId === lead.id} onClick={() => onArchive(lead)}>Archive</button>}
      {lead.archived_at && canRestore && onRestore && <button className="btn" disabled={busyId === lead.id} onClick={() => onRestore(lead)}>Restore</button>}
    </div></td>}</tr>)}
  </tbody></table></div>;
}

function renderCell(column: LeadColumn, lead: Lead) {
  switch (column) {
    case "name": return <Link className="lead-name" href={`/leads/${lead.id}`}>{lead.name}</Link>;
    case "company": return lead.company || "-";
    case "email": return lead.pii_redacted ? <span className="muted">Restricted</span> : lead.email || "-";
    case "phone": return lead.pii_redacted ? <span className="muted">Restricted</span> : lead.phone || "-";
    case "status_changed_at": return <span className="small muted">{formatDate(lead.status_changed_at)}</span>;
    case "status": return <><span className="status-dot" style={{ background: lead.status_color }} />{lead.status}{lead.archived_at && <div className="badge">Archived</div>}</>;
    case "source_name": return lead.source_account_name || lead.source_provider || "-";
    case "source_record_id": return lead.source_record_id || "-";
    case "received_at": return <span className="small muted">{formatDate(lead.received_at)}</span>;
    case "assignee": return lead.assignee || <span className="muted">Unassigned</span>;
    case "tags": return lead.tags.length ? <div className="tag-list">{lead.tags.map(tag => <span key={tag} className="tag">{tag}</span>)}</div> : "-";
  }
}
