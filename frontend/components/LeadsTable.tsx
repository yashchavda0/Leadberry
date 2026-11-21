import { useState } from "react";
import Link from "next/link";
import Icon from "./Icon";
import ScrollArea from "./ScrollArea";
import { Tip } from "./ui/tip";
import { formatDate, type Lead, type LeadCustomField } from "@/lib/crm";

export const LEAD_COLUMNS = [
  { key: "name", label: "Name" },
  { key: "company", label: "Company" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Mobile" },
  { key: "city", label: "City" },
  { key: "state", label: "State" },
  { key: "address", label: "Address" },
  { key: "product", label: "Product / service" },
  { key: "enquiry", label: "Enquiry" },
  { key: "status_changed_at", label: "Status updated" },
  { key: "status", label: "Lead status" },
  { key: "source_name", label: "Source connection" },
  { key: "source_provider", label: "Source provider" },
  { key: "source_record_id", label: "Audience ID" },
  { key: "received_at", label: "Received" },
  { key: "assignee", label: "Assigned to" },
  { key: "team_name", label: "Assigned team" },
  { key: "tags", label: "Tags" },
  { key: "next_follow_up_at", label: "Next follow-up" },
  { key: "updated_at", label: "Last updated" },
  { key: "archived_at", label: "Archived at" },
] as const;

export type LeadColumn = typeof LEAD_COLUMNS[number]["key"] | `custom:${string}`;
type SortState = { key: LeadColumn; direction: "asc" | "desc" };
const dateColumns = new Set<LeadColumn>(["status_changed_at", "received_at", "next_follow_up_at", "updated_at", "archived_at"]);
const textCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

export function isPiiLeadColumn(key: string) {
  return ["email", "phone", "address", "enquiry"].includes(key) || key.startsWith("custom:");
}
export function getLeadColumns(customFields: LeadCustomField[] = []): { key: LeadColumn; label: string }[] {
  return [...LEAD_COLUMNS, ...customFields.filter(field => field.is_active).map(field => ({ key: `custom:${field.field_key}` as const, label: field.label }))];
}

export default function LeadsTable({ leads, columns, customFields, onArchive, onRestore, busyId, offset = 0, canArchive = false, canRestore = false }: {
  customFields?: LeadCustomField[];
  leads: Lead[]; columns?: string[]; onArchive?: (lead: Lead) => void; onRestore?: (lead: Lead) => void;
  busyId?: string | null; offset?: number; canArchive?: boolean; canRestore?: boolean;
}) {
  const [sort, setSort] = useState<SortState | null>(null);
  if (!leads.length) return <div className="empty-state"><h3>No leads to display</h3><p className="muted">Create a lead or adjust your filters. Only leads within your data scope are shown.</p></div>;
  const selectedColumns = columns || ["name", "status", "assignee", "received_at"];
  const visible = getLeadColumns(customFields).filter(column => selectedColumns.includes(column.key));
  const hasActions = Boolean(onArchive || onRestore);
  const sortedLeads = sort ? [...leads].sort((first, second) => {
    const result = compareLeadValues(sort.key, leadSortValue(sort.key, first), leadSortValue(sort.key, second));
    return (sort.direction === "asc" ? result : -result) || first.id.localeCompare(second.id);
  }) : leads;
  function toggleSort(key: LeadColumn) {
    setSort(current => current?.key === key
      ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
      : { key, direction: "asc" });
  }
  return <ScrollArea className="leads-table-area" direction="both" label="Leads table"><table className="leads-table"><thead><tr><th scope="col">Sr. No.</th>{visible.map(column => {
    const direction = sort?.key === column.key ? sort.direction : undefined;
    return <th scope="col" key={column.key} aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}>
      <button type="button" className="lead-sort-button" aria-label={`Sort by ${column.label}`} onClick={() => toggleSort(column.key)}>
        {column.label}<span className={`lead-sort-indicator${direction ? ` ${direction}` : ""}`} aria-hidden="true"><Icon name="chevron" size={12} /></span>
      </button>
    </th>;
  })}{hasActions && <th scope="col" className="lead-actions-col">Actions</th>}</tr></thead><tbody>
    {sortedLeads.map((lead, index) => <tr key={lead.id}><td className="lead-index">{offset + index + 1}</td>{visible.map(column => <td className={`lead-cell-${column.key}`} key={column.key}>{renderCell(column.key, lead)}</td>)}{hasActions && <td className="lead-actions-col"><div className="actions lead-row-actions">
      <Tip label={`View ${lead.name}`}><Link className="btn lead-icon-button" href={`/leads/${lead.id}`} aria-label={`View ${lead.name}`}><Icon name="external" /></Link></Tip>
      {!lead.archived_at && canArchive && onArchive && <Tip label={`Archive ${lead.name}`} disabled={busyId === lead.id}><button className="btn lead-icon-button" aria-label={`Archive ${lead.name}`} disabled={busyId === lead.id} onClick={() => onArchive(lead)}><Icon name="history" /></button></Tip>}
      {lead.archived_at && canRestore && onRestore && <Tip label={`Restore ${lead.name}`} disabled={busyId === lead.id}><button className="btn lead-icon-button" aria-label={`Restore ${lead.name}`} disabled={busyId === lead.id} onClick={() => onRestore(lead)}><Icon name="refresh" /></button></Tip>}
    </div></td>}</tr>)}
  </tbody></table></ScrollArea>;
}

function leadSortValue(column: LeadColumn, lead: Lead): string | number | boolean | null {
  if (column.startsWith("custom:")) return lead.pii_redacted ? null : lead.custom_fields[column.slice(7)] ?? null;
  switch (column) {
    case "name": return lead.name;
    case "company": return lead.company;
    case "email": return lead.pii_redacted ? null : lead.email;
    case "phone": return lead.pii_redacted ? null : lead.phone;
    case "city": return lead.city;
    case "state": return lead.state;
    case "address": return lead.pii_redacted ? null : lead.address;
    case "product": return lead.product;
    case "enquiry": return lead.pii_redacted ? null : lead.enquiry;
    case "status_changed_at": return lead.status_changed_at;
    case "status": return lead.status;
    case "source_name": return lead.source_account_name ?? null;
    case "source_provider": return lead.source_provider;
    case "source_record_id": return lead.source_record_id;
    case "received_at": return lead.received_at;
    case "assignee": return lead.assignee;
    case "team_name": return lead.team_name || null;
    case "tags": return lead.tags.join(", ");
    case "next_follow_up_at": return lead.next_follow_up_at;
    case "updated_at": return lead.updated_at;
    case "archived_at": return lead.archived_at;
  }
  return null;
}

function compareLeadValues(column: LeadColumn, first: string | number | boolean | null, second: string | number | boolean | null) {
  if (first == null || first === "") return second == null || second === "" ? 0 : 1;
  if (second == null || second === "") return -1;
  if (dateColumns.has(column)) return new Date(String(first)).getTime() - new Date(String(second)).getTime();
  if (typeof first === "number" || typeof second === "number") return Number(first) - Number(second);
  if (typeof first === "boolean" || typeof second === "boolean") return Number(first) - Number(second);
  return textCollator.compare(String(first), String(second));
}

function renderCell(column: LeadColumn, lead: Lead) {
  if (column.startsWith("custom:")) {
    if (lead.pii_redacted) return <span className="muted">Restricted</span>;
    const value = lead.custom_fields[column.slice(7)];
    return value === null || value === undefined || value === "" ? "-" : typeof value === "boolean" ? value ? "Yes" : "No" : String(value);
  }
  switch (column) {
    case "name": return <Link className="lead-name" href={`/leads/${lead.id}`}>{lead.name}</Link>;
    case "company": return lead.company || "-";
    case "city": return lead.city || "-";
    case "state": return lead.state || "-";
    case "product": return lead.product || "-";
    case "address": return lead.pii_redacted ? <span className="muted">Restricted</span> : lead.address || "-";
    case "enquiry": return lead.pii_redacted ? <span className="muted">Restricted</span> : lead.enquiry || "-";
    case "email": return lead.pii_redacted ? <span className="muted">Restricted</span> : lead.email || "-";
    case "phone": return lead.pii_redacted ? <span className="muted">Restricted</span> : lead.phone || "-";
    case "status_changed_at": return <span className="small muted">{formatDate(lead.status_changed_at)}</span>;
    case "status": return <span className="lead-status"><span className="status-dot" style={{ background: lead.status_color }} />{lead.status}</span>;
    case "source_name": return lead.source_account_name || "-";
    case "source_provider": return lead.source_provider || "-";
    case "source_record_id": return lead.source_record_id || "-";
    case "received_at": return <span className="small muted">{formatDate(lead.received_at)}</span>;
    case "assignee": return lead.assignee || <span className="muted">Unassigned</span>;
    case "team_name": return lead.team_name || "-";
    case "next_follow_up_at": return lead.next_follow_up_at ? formatDate(lead.next_follow_up_at) : "-";
    case "updated_at": return formatDate(lead.updated_at);
    case "archived_at": return lead.archived_at ? formatDate(lead.archived_at) : "-";
    case "tags": return lead.tags.length ? <div className="tag-list">{lead.tags.map(tag => <span key={tag} className="tag">{tag}</span>)}</div> : "-";
  }
}
