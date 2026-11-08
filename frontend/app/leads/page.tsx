"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import LeadsTable, { LEAD_COLUMNS } from "@/components/LeadsTable";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Loading, Pagination } from "@/components/Ui";
import { crm, errorMessage, type Lead, type LeadCustomField, type Status } from "@/lib/crm";
import { usePaged, useResource } from "@/lib/hooks";

export default function LeadsPage() { return <Guard permission="leads.view"><Suspense fallback={<Loading />}><Leads /></Suspense></Guard>; }
function Leads() {
  const { can, identity } = useSession();
  const searchParams = useSearchParams();
  const integrationId = searchParams.get("integration_id");
  const [filters, setFilters] = useState("");
  const [columns, setColumns] = useState<string[]>(LEAD_COLUMNS.map(column => column.key));
  const [preferenceError, setPreferenceError] = useState("");
  const [preferenceBusy, setPreferenceBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const options = useResource<{ statuses: Status[]; custom_fields: LeadCustomField[]; sources: string[]; accounts: { id: string; name: string }[] }>("/leads/options");
  const assignees = useResource<{ data: { id: string; display_name: string }[] }>(can("leads.assign") ? "/leads/assignees?limit=100" : null);
  const preferences = useResource<{ columns: string[] }>("/lead-table-preferences");
  const query = new URLSearchParams(filters);
  if (integrationId) query.set("integration_id", integrationId);
  const list = usePaged<Lead>(`/leads?${query}`);
  useEffect(() => { if (preferences.data) setColumns(preferences.data.columns); }, [preferences.data]);
  function filter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    for (const [key, value] of values) {
      if (typeof value === "string" && value.trim() && !(key === "archived" && value === "false")) params.set(key, value.trim());
    }
    setFilters(params.toString());
  }
  async function saveColumns(next: string[]) {
    setPreferenceBusy(true); setPreferenceError("");
    try { const result = await crm<{ columns: string[] }>("/lead-table-preferences", { method: "PUT", body: JSON.stringify({ columns: next }) }); setColumns(result.columns); }
    catch (error) { setPreferenceError(errorMessage(error)); }
    finally { setPreferenceBusy(false); }
  }
  async function changeArchive(lead: Lead, restore: boolean) {
    const action = restore ? "restore" : "archive";
    if (!window.confirm(`${restore ? "Restore" : "Archive"} ${lead.name}?`)) return;
    setBusyId(lead.id); setActionError("");
    try { await crm(`/leads/${lead.id}/${action}`, { method: "POST", body: JSON.stringify({ row_version: lead.row_version }) }); list.reload(); }
    catch (error) { setActionError(errorMessage(error)); }
    finally { setBusyId(null); }
  }
  return <><div className="page-header"><div><span className="eyebrow">LEAD MANAGEMENT</span><h1>Leads</h1><p className="muted">Organized contacts, clear ownership. Current visibility: {identity?.data_scope}.</p></div>{can("leads.create") && <Link href="/leads/new" className="btn btn-primary">+ New lead</Link>}</div>
    {integrationId && <div className="toolbar"><span className="badge">{searchParams.get("connection") || "Selected connection"}</span><Link className="btn" href="/leads">All connections</Link></div>}
    <div className="card"><form className="filters" onSubmit={filter}>
      <label>Search<input className="input" name="q" placeholder="Name, company, product or city" maxLength={200} /></label>
      <label>Status<select className="select" name="status_id"><option value="">All statuses</option>{options.data?.statuses.map(status => <option key={status.id} value={status.id}>{status.name}</option>)}</select></label>
      <label>Assignee<select className="select" name="assignee"><option value="">Anyone</option>{assignees.data?.data.map(member => <option key={member.id} value={member.id}>{member.display_name}</option>)}</select></label>
      <label>Source<select className="select" name="source"><option value="">All sources</option>{options.data?.sources.map(source => <option key={source} value={source}>{source}</option>)}</select></label>
      <label>Source account<select className="select" name="integration_id"><option value="">All accounts</option>{options.data?.accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
      <label>Audience ID<input className="input" name="source_record_id" maxLength={200} /></label>
      <label>Tag<input className="input" name="tag" maxLength={50} /></label>
      <label>Received from<input className="input" name="start" type="date" /></label>
      <label>Received through<input className="input" name="end" type="date" /></label>
      <label>Status updated from<input className="input" name="status_start" type="date" /></label>
      <label>Status updated through<input className="input" name="status_end" type="date" /></label>
      {(can("leads.archive") || can("leads.restore")) && <label>View<select className="select" name="archived"><option value="false">Active</option><option value="true">Archived</option></select></label>}
      <button className="btn btn-primary" disabled={list.loading}>Apply filters</button><button className="btn" type="reset" onClick={() => setFilters("")}>Reset</button>
    </form>
      <div className="lead-table-tools"><details className="column-picker"><summary className="btn">Columns</summary><div className="column-picker-menu">{LEAD_COLUMNS.map(column => <label key={column.key}><input type="checkbox" checked={columns.includes(column.key)} disabled={preferenceBusy || column.key === "name" || (["email", "phone"].includes(column.key) && !can("leads.pii.view"))} onChange={event => void saveColumns(event.target.checked ? [...columns, column.key] : columns.filter(value => value !== column.key))} /><span>{column.label}</span></label>)}</div></details><ErrorNotice error={preferenceError} /></div>
      <ErrorNotice error={options.error || list.error || preferences.error || actionError} />{list.loading ? <Loading /> : list.data && <LeadsTable leads={list.data.data} columns={columns} onArchive={lead => void changeArchive(lead, false)} onRestore={lead => void changeArchive(lead, true)} busyId={busyId} canArchive={can("leads.archive")} canRestore={can("leads.restore")} />}
      <Pagination page={list.page} previous={list.previous} next={list.next} hasPrevious={list.hasPrevious} hasNext={Boolean(list.data?.next_cursor)} loading={list.loading} />
    </div><p className="small muted">Search uses indexed whole words; contact data is not searched. Dates use UTC. Sr. No. is numbered on the current page.</p>
  </>;
}
